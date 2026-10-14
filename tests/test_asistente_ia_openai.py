import asyncio
import json
import logging
from datetime import UTC, datetime

import httpx
import pytest
import respx
from pydantic import BaseModel

from buscador_vacantes.asistente.datos import BaseAsistente
from buscador_vacantes.asistente.ia import (
    ClaveInvalida,
    ClienteIA,
    CuotaAgotada,
    ErrorIA,
    Parte,
    datos,
)
from buscador_vacantes.config import cargar_configuracion

BASE = "https://api.openai.com/v1/"
URL = BASE + "chat/completions"
CLAVE = "sk-proj-ClaveDePrueba1234567890"
AHORA = datetime(2026, 10, 4, 15, 0, tzinfo=UTC)


class Salida(BaseModel):
    respuesta: str | None
    suficiente: bool


OK_SALIDA = {"respuesta": "Hola", "suficiente": True}


def ok(contenido, uso=(10, 5)):
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"role": "assistant", "content": json.dumps(contenido)}}],
            "usage": {"prompt_tokens": uso[0], "completion_tokens": uso[1]},
        },
    )


@pytest.fixture
def entorno(tmp_path):
    base = BaseAsistente.abrir(tmp_path / "a.db")
    with base.transaccion() as cx:
        cx.execute(
            "INSERT INTO usuarios(id, telegram_id, directorio, creado) VALUES (1, 1, 'u', 'x')"
        )
    esperas = []

    async def dormir(s):
        esperas.append(s)

    proveedor = cargar_configuracion().asistente.ia.proveedores["openai"]
    cliente = ClienteIA(proveedor, base, 10, reloj=lambda: AHORA, dormir=dormir)
    yield cliente, esperas
    asyncio.run(cliente.cerrar())
    base.cerrar()


def generar(cliente, partes=None):
    return asyncio.run(
        cliente.generar(
            "carta",
            CLAVE,
            1,
            "Redacta la respuesta.",
            partes or [Parte(datos("vacante", "Practicante de Python"))],
            Salida,
        )
    )


@respx.mock
def test_exito_con_json_schema_clave_en_cabecera_y_tokens(entorno):
    cliente, _ = entorno
    ruta = respx.post(URL).mock(return_value=ok(OK_SALIDA, uso=(120, 30)))
    assert generar(cliente).respuesta == "Hola"
    peticion = ruta.calls.last.request
    assert peticion.headers["authorization"] == f"Bearer {CLAVE}"
    assert CLAVE not in str(peticion.url)
    cuerpo = json.loads(peticion.content)
    assert cuerpo["model"] == "gpt-4.1-mini"
    assert cuerpo["response_format"]["type"] == "json_schema"
    assert cuerpo["response_format"]["json_schema"]["name"] == "Salida"
    assert "respuesta" in cuerpo["response_format"]["json_schema"]["schema"]["properties"]
    assert cuerpo["messages"][0]["role"] == "system"
    assert "ignora" in cuerpo["messages"][0]["content"]
    assert "<<<DATOS vacante" in cuerpo["messages"][1]["content"][0]["text"]
    fila = cliente.base.cx.execute("SELECT ok, tokens_in, tokens_out FROM ia_uso").fetchone()
    assert tuple(fila) == (1, 120, 30)


@respx.mock
def test_json_invalido_reintenta_una_vez_y_luego_falla(entorno):
    cliente, _ = entorno
    ruta = respx.post(URL).mock(
        side_effect=[ok({"otra": 1}), ok({"respuesta": "bien", "suficiente": True})]
    )
    assert generar(cliente).respuesta == "bien"
    assert ruta.call_count == 2
    respx.post(URL).mock(return_value=ok({"otra": 1}))
    with pytest.raises(ErrorIA, match="no devolvió una respuesta válida"):
        generar(cliente)


@respx.mock
def test_contenido_vacio_cuenta_como_json_invalido(entorno):
    cliente, _ = entorno
    vacio = httpx.Response(200, json={"choices": [{"message": {"content": None}}]})
    respx.post(URL).mock(return_value=vacio)
    with pytest.raises(ErrorIA, match="no devolvió una respuesta válida"):
        generar(cliente)


@respx.mock
def test_400_por_response_format_cae_a_json_object_y_lo_recuerda(entorno):
    cliente, _ = entorno
    rechazo = httpx.Response(400, json={"error": {"message": "response_format no soportado"}})
    ruta = respx.post(URL).mock(side_effect=[rechazo, ok(OK_SALIDA), ok(OK_SALIDA)])
    assert generar(cliente).respuesta == "Hola"
    segundo = json.loads(ruta.calls[1].request.content)
    assert segundo["response_format"] == {"type": "json_object"}
    # El esquema se describe en la instrucción porque json_object no lo impone
    assert '"suficiente"' in segundo["messages"][0]["content"]
    # La siguiente llamada con el mismo modelo ya no pierde una petición en el 400
    assert generar(cliente).respuesta == "Hola"
    assert ruta.call_count == 3
    assert json.loads(ruta.calls[2].request.content)["response_format"] == {"type": "json_object"}


@respx.mock
def test_400_que_no_era_de_response_format_no_marca_el_modelo(entorno):
    cliente, _ = entorno
    ruta = respx.post(URL).mock(
        side_effect=[httpx.Response(400, json={}), httpx.Response(400, json={}), ok(OK_SALIDA)]
    )
    with pytest.raises(ErrorIA, match="OpenAI respondió HTTP 400"):
        generar(cliente)
    assert ruta.call_count == 2
    assert generar(cliente).respuesta == "Hola"
    assert json.loads(ruta.calls.last.request.content)["response_format"]["type"] == "json_schema"


@respx.mock
def test_429_con_retry_after_corto_reintenta(entorno):
    cliente, esperas = entorno
    limite = httpx.Response(429, headers={"Retry-After": "7"}, json={})
    respx.post(URL).mock(side_effect=[limite, ok(OK_SALIDA)])
    assert generar(cliente).respuesta == "Hola"
    assert esperas == [7]


@respx.mock
def test_429_largo_es_cuota_agotada_y_nombra_al_proveedor_sin_decir_gratuita(entorno):
    cliente, esperas = entorno
    respx.post(url__startswith=BASE).mock(
        return_value=httpx.Response(429, headers={"Retry-After": "3600"}, json={})
    )
    with pytest.raises(CuotaAgotada, match="OpenAI") as info:
        generar(cliente)
    assert "gratuita" not in str(info.value)
    assert esperas == []


@respx.mock
def test_429_sin_retry_after_es_cuota_agotada(entorno):
    cliente, _ = entorno
    respx.post(url__startswith=BASE).mock(return_value=httpx.Response(429, json={}))
    with pytest.raises(CuotaAgotada):
        generar(cliente)


@respx.mock
def test_503_reintenta_con_espera_y_luego_usa_el_respaldo(entorno):
    cliente, esperas = entorno
    principal = respx.post(URL).mock(
        side_effect=lambda r: (
            httpx.Response(503, json={})
            if json.loads(r.content)["model"] == "gpt-4.1-mini"
            else ok({"respuesta": "respaldo", "suficiente": True})
        )
    )
    assert generar(cliente).respuesta == "respaldo"
    assert esperas == [3, 8]
    modelos = [json.loads(c.request.content)["model"] for c in principal.calls]
    assert modelos == ["gpt-4.1-mini"] * 3 + ["gpt-4o-mini"]


@respx.mock
def test_todos_los_modelos_saturados_falla(entorno):
    cliente, _ = entorno
    respx.post(URL).mock(return_value=httpx.Response(503, json={}))
    with pytest.raises(ErrorIA, match="OpenAI está saturado"):
        generar(cliente)


@respx.mock
@pytest.mark.parametrize("estado", [401, 403])
def test_clave_rechazada(entorno, estado):
    cliente, _ = entorno
    respx.post(URL).mock(return_value=httpx.Response(estado, json={"error": {"message": "x"}}))
    with pytest.raises(ClaveInvalida, match="clave de OpenAI"):
        generar(cliente)


@respx.mock
def test_validar_clave_con_la_lista_de_modelos(entorno):
    cliente, _ = entorno
    ruta = respx.get(BASE + "models").mock(
        side_effect=[
            httpx.Response(200, json={"data": []}),
            httpx.Response(401, json={}),
            httpx.Response(500, json={}),
        ]
    )
    assert asyncio.run(cliente.validar_clave(CLAVE)) is True
    assert ruta.calls[0].request.headers["authorization"] == f"Bearer {CLAVE}"
    assert asyncio.run(cliente.validar_clave("mala")) is False
    with pytest.raises(ErrorIA, match="500"):
        asyncio.run(cliente.validar_clave(CLAVE))


@respx.mock
def test_validar_clave_sin_conexion(entorno):
    cliente, _ = entorno
    respx.get(BASE + "models").mock(side_effect=httpx.ConnectError("sin red"))
    with pytest.raises(ErrorIA, match="No se pudo contactar a OpenAI"):
        asyncio.run(cliente.validar_clave(CLAVE))


@respx.mock
def test_pdf_va_como_archivo_en_linea(entorno):
    cliente, _ = entorno
    ruta = respx.post(URL).mock(return_value=ok(OK_SALIDA))
    generar(cliente, [Parte(pdf=b"%PDF-1.4")])
    parte = json.loads(ruta.calls.last.request.content)["messages"][1]["content"][0]
    assert parte["type"] == "file"
    assert parte["file"]["file_data"].startswith("data:application/pdf;base64,")


@respx.mock
def test_los_fallos_no_gastan_el_tope_ni_filtran_la_clave(entorno, caplog):
    cliente, _ = entorno
    caplog.set_level(logging.DEBUG)
    respx.post(URL).mock(side_effect=[httpx.Response(503, json={}), ok(OK_SALIDA)])
    generar(cliente)
    assert cliente.llamadas_hoy(1) == 1
    assert CLAVE not in caplog.text
    motivos = [f[0] for f in cliente.base.cx.execute("SELECT motivo FROM ia_uso ORDER BY id")]
    assert motivos == ["HTTP 503", None]
