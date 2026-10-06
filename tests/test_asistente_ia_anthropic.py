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

BASE = "https://api.anthropic.com/v1/"
URL = BASE + "messages"
CLAVE = "sk-ant-api03-ClaveDePrueba1234567890"
AHORA = datetime(2026, 10, 4, 15, 0, tzinfo=UTC)
PRINCIPAL = "claude-sonnet-5-5"
RESPALDO = "claude-haiku-4-5-20251001"


class Salida(BaseModel):
    respuesta: str | None
    suficiente: bool


OK_SALIDA = {"respuesta": "Hola", "suficiente": True}


def ok(contenido, uso=(10, 5)):
    return httpx.Response(
        200,
        json={
            "content": [
                {"type": "text", "text": "Voy a entregar el resultado."},
                {"type": "tool_use", "id": "t1", "name": "entregar_resultado", "input": contenido},
            ],
            "usage": {"input_tokens": uso[0], "output_tokens": uso[1]},
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

    proveedor = cargar_configuracion().asistente.ia.proveedores["anthropic"]
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
def test_exito_con_herramienta_forzada_clave_en_cabecera_y_tokens(entorno):
    cliente, _ = entorno
    ruta = respx.post(URL).mock(return_value=ok(OK_SALIDA, uso=(120, 30)))
    assert generar(cliente).respuesta == "Hola"
    peticion = ruta.calls.last.request
    assert peticion.headers["x-api-key"] == CLAVE
    assert peticion.headers["anthropic-version"] == "2023-06-01"
    assert CLAVE not in str(peticion.url)
    cuerpo = json.loads(peticion.content)
    assert cuerpo["model"] == PRINCIPAL
    assert cuerpo["tool_choice"] == {"type": "tool", "name": "entregar_resultado"}
    herramienta = cuerpo["tools"][0]
    assert herramienta["name"] == "entregar_resultado"
    assert "respuesta" in herramienta["input_schema"]["properties"]
    assert "ignora" in cuerpo["system"]
    assert "<<<DATOS vacante" in cuerpo["messages"][0]["content"][0]["text"]
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
def test_respuesta_sin_herramienta_cuenta_como_json_invalido(entorno):
    cliente, _ = entorno
    solo_texto = httpx.Response(200, json={"content": [{"type": "text", "text": "hola"}]})
    respx.post(URL).mock(return_value=solo_texto)
    with pytest.raises(ErrorIA, match="no devolvió una respuesta válida"):
        generar(cliente)


@respx.mock
def test_429_con_retry_after_corto_reintenta(entorno):
    cliente, esperas = entorno
    limite = httpx.Response(429, headers={"retry-after": "5"}, json={})
    respx.post(URL).mock(side_effect=[limite, ok(OK_SALIDA)])
    assert generar(cliente).respuesta == "Hola"
    assert esperas == [5]


@respx.mock
def test_429_largo_es_cuota_agotada_y_nombra_al_proveedor_sin_decir_gratuita(entorno):
    cliente, esperas = entorno
    respx.post(URL).mock(return_value=httpx.Response(429, headers={"retry-after": "3600"}, json={}))
    with pytest.raises(CuotaAgotada, match="Anthropic") as info:
        generar(cliente)
    assert "gratuita" not in str(info.value)
    assert esperas == []


@respx.mock
def test_529_sobrecargado_reintenta_y_luego_usa_el_respaldo(entorno):
    cliente, esperas = entorno
    ruta = respx.post(URL).mock(
        side_effect=lambda r: (
            httpx.Response(529, json={"error": {"type": "overloaded_error"}})
            if json.loads(r.content)["model"] == PRINCIPAL
            else ok({"respuesta": "respaldo", "suficiente": True})
        )
    )
    assert generar(cliente).respuesta == "respaldo"
    assert esperas == [3, 8]
    modelos = [json.loads(c.request.content)["model"] for c in ruta.calls]
    assert modelos == [PRINCIPAL] * 3 + [RESPALDO]


@respx.mock
def test_todos_los_modelos_saturados_falla(entorno):
    cliente, _ = entorno
    respx.post(URL).mock(return_value=httpx.Response(503, json={}))
    with pytest.raises(ErrorIA, match="Anthropic.*saturado"):
        generar(cliente)


@respx.mock
def test_modelo_retirado_usa_el_respaldo(entorno):
    cliente, _ = entorno
    respx.post(URL).mock(
        side_effect=lambda r: (
            httpx.Response(404, json={"error": {"type": "not_found_error"}})
            if json.loads(r.content)["model"] == PRINCIPAL
            else ok(OK_SALIDA)
        )
    )
    assert generar(cliente).respuesta == "Hola"


@respx.mock
@pytest.mark.parametrize("estado", [401, 403])
def test_clave_rechazada(entorno, estado):
    cliente, _ = entorno
    respx.post(URL).mock(
        return_value=httpx.Response(estado, json={"error": {"type": "authentication_error"}})
    )
    with pytest.raises(ClaveInvalida, match="clave de Anthropic"):
        generar(cliente)


@respx.mock
def test_validar_clave(entorno):
    cliente, _ = entorno
    ruta = respx.get(BASE + "models").mock(
        side_effect=[
            httpx.Response(200, json={"data": []}),
            httpx.Response(401, json={}),
            httpx.Response(500, json={}),
        ]
    )
    assert asyncio.run(cliente.validar_clave(CLAVE)) is True
    assert ruta.calls[0].request.headers["x-api-key"] == CLAVE
    assert asyncio.run(cliente.validar_clave("mala")) is False
    with pytest.raises(ErrorIA, match="500"):
        asyncio.run(cliente.validar_clave(CLAVE))


@respx.mock
def test_validar_clave_sin_conexion(entorno):
    cliente, _ = entorno
    respx.get(BASE + "models").mock(side_effect=httpx.ConnectError("sin red"))
    with pytest.raises(ErrorIA, match="No se pudo contactar a Anthropic"):
        asyncio.run(cliente.validar_clave(CLAVE))


@respx.mock
def test_pdf_va_como_documento_en_linea(entorno):
    cliente, _ = entorno
    ruta = respx.post(URL).mock(return_value=ok(OK_SALIDA))
    generar(cliente, [Parte(pdf=b"%PDF-1.4")])
    parte = json.loads(ruta.calls.last.request.content)["messages"][0]["content"][0]
    assert parte["type"] == "document"
    assert parte["source"]["media_type"] == "application/pdf"
    assert parte["source"]["type"] == "base64"


@respx.mock
def test_los_fallos_no_gastan_el_tope_ni_filtran_la_clave(entorno, caplog):
    cliente, _ = entorno
    caplog.set_level(logging.DEBUG)
    respx.post(URL).mock(side_effect=[httpx.Response(529, json={}), ok(OK_SALIDA)])
    generar(cliente)
    assert cliente.llamadas_hoy(1) == 1
    assert CLAVE not in caplog.text
