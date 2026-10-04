import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx

from config import cargar_configuracion
from estado import Estado
from ia_cliente import ClienteIA

BASE = "https://api.deepseek.com"
CLAVE = "sk-clave-de-prueba-123456"
TOKEN = "123456789:AAFakeTokenFakeTokenFakeTokenFake12"
CHAT = "-1004429829042"


class Reloj:
    def __init__(self):
        self.momento = datetime(2026, 10, 3, 15, 0, tzinfo=UTC)

    def __call__(self):
        return self.momento


@pytest.fixture
def estado():
    e = Estado.abrir(":memory:")
    yield e
    e.cerrar()


@pytest.fixture
def reloj():
    return Reloj()


@pytest.fixture
def ia(estado, reloj):
    config = cargar_configuracion()
    cliente = ClienteIA(config.ia, CLAVE, estado, secretos=[CLAVE, TOKEN, CHAT], reloj=reloj)
    yield cliente
    cliente.cerrar()


def saldo(valor="25.50"):
    return httpx.Response(
        200,
        json={"is_available": True,
              "balance_infos": [{"currency": "USD", "total_balance": valor}]},
    )  # fmt: skip


def completado(contenido, prompt=120, salida=40):
    return httpx.Response(
        200,
        json={"choices": [{"message": {"content": contenido}}],
              "usage": {"prompt_tokens": prompt, "completion_tokens": salida}},
    )  # fmt: skip


def llamar(ia, payload=None):
    return ia.chat_json(
        "clasificador", "Eres un clasificador", payload or {"vacantes": []},
        temperatura=0, max_tokens=200,
    )  # fmt: skip


def usos(estado):
    return [dict(f) for f in estado.cx.execute("SELECT * FROM ia_uso ORDER BY id")]


@respx.mock
def test_llamada_exitosa_registra_tokens(ia, estado):
    respx.get(f"{BASE}/user/balance").mock(return_value=saldo())
    ruta = respx.post(f"{BASE}/chat/completions").mock(
        return_value=completado('{"vacantes": [{"id": 0, "aceptar": true}]}')
    )
    respuesta = llamar(ia)
    assert respuesta.ok
    assert respuesta.datos == {"vacantes": [{"id": 0, "aceptar": True}]}
    cuerpo = json.loads(ruta.calls[0].request.content)
    assert cuerpo["response_format"] == {"type": "json_object"}
    assert cuerpo["temperature"] == 0
    assert cuerpo["model"] == "deepseek-chat"
    assert ruta.calls[0].request.headers["authorization"] == f"Bearer {CLAVE}"
    [uso] = usos(estado)
    assert (uso["proposito"], uso["tokens_in"], uso["tokens_out"], uso["ok"]) == (
        "clasificador",
        120,
        40,
        1,
    )


@respx.mock
def test_saldo_bajo_no_llama(ia, estado):
    respx.get(f"{BASE}/user/balance").mock(return_value=saldo("0.40"))
    ruta = respx.post(f"{BASE}/chat/completions")
    respuesta = llamar(ia)
    assert not respuesta.ok and respuesta.motivo == "saldo bajo"
    assert not ruta.called
    assert usos(estado) == []


@respx.mock
def test_saldo_cacheado_10_minutos(ia, reloj):
    ruta_saldo = respx.get(f"{BASE}/user/balance").mock(return_value=saldo())
    assert ia.saldo() == 25.5
    reloj.momento += timedelta(minutes=9)
    assert ia.saldo() == 25.5
    assert ruta_saldo.call_count == 1
    reloj.momento += timedelta(minutes=2)
    ia.saldo()
    assert ruta_saldo.call_count == 2


@respx.mock
def test_saldo_no_disponible_igual_intenta(ia):
    respx.get(f"{BASE}/user/balance").mock(return_value=httpx.Response(500))
    respx.post(f"{BASE}/chat/completions").mock(return_value=completado("{}"))
    assert llamar(ia).ok


@pytest.mark.parametrize(
    ("respuesta_http", "motivo"),
    [
        (httpx.Response(402, json={"error": "Sin saldo"}), "saldo insuficiente (HTTP 402)"),
        (httpx.Response(503), "error del servidor (HTTP 503)"),
        (httpx.Response(401), "error HTTP 401"),
        (completado("esto no es json"), "respuesta inválida"),
        (completado("[1, 2]"), "respuesta inválida"),
        (httpx.Response(200, json={"choices": []}), "respuesta inválida"),
    ],
)  # fmt: skip
@respx.mock
def test_fallos_de_la_api(ia, estado, respuesta_http, motivo):
    respx.get(f"{BASE}/user/balance").mock(return_value=saldo())
    respx.post(f"{BASE}/chat/completions").mock(return_value=respuesta_http)
    respuesta = llamar(ia)
    assert not respuesta.ok
    assert respuesta.motivo == motivo
    [uso] = usos(estado)
    assert uso["ok"] == 0 and uso["motivo"] == motivo


@respx.mock
def test_timeout(ia, estado):
    respx.get(f"{BASE}/user/balance").mock(return_value=saldo())
    respx.post(f"{BASE}/chat/completions").mock(side_effect=httpx.ReadTimeout("lento"))
    respuesta = llamar(ia)
    assert (respuesta.ok, respuesta.motivo) == (False, "timeout")
    assert usos(estado)[0]["motivo"] == "timeout"


@respx.mock
def test_tope_diario(ia, estado, reloj):
    respx.get(f"{BASE}/user/balance").mock(return_value=saldo())
    ruta = respx.post(f"{BASE}/chat/completions").mock(return_value=completado("{}"))
    tope = ia.tope("clasificador")
    for _ in range(tope):
        assert llamar(ia).ok
    respuesta = llamar(ia)
    assert (respuesta.ok, respuesta.motivo) == (False, "tope diario alcanzado")
    assert ruta.call_count == tope
    # El tope es por propósito
    assert ia.llamadas_hoy("reportero") == 0
    # Al día siguiente (hora de Colombia) se reinicia
    reloj.momento += timedelta(days=1)
    assert llamar(ia).ok


@respx.mock
def test_payload_sin_secretos(ia):
    respx.get(f"{BASE}/user/balance").mock(return_value=saldo())
    ruta = respx.post(f"{BASE}/chat/completions").mock(return_value=completado("{}"))
    payload = {
        "vacantes": [{"titulo": "Practicante", "nota": f"token {TOKEN} chat {CHAT}"}],
        "url": f"https://api.telegram.org/bot{TOKEN}/sendMessage?chat_id={CHAT}",
        "clave": CLAVE,
        "otra": "sk-desconocidaABCDEFGHIJ",
    }
    llamar(ia, payload)
    enviado = ruta.calls[0].request.content.decode()
    for secreto in (TOKEN, CHAT, CLAVE, "sk-desconocidaABCDEFGHIJ"):
        assert secreto not in enviado
    assert "Practicante" in enviado


def test_sin_clave_no_llama(estado, reloj):
    ia = ClienteIA(cargar_configuracion().ia, None, estado, reloj=reloj)
    assert ia.chat_json("resumen", "x", {}, temperatura=0, max_tokens=10).motivo == (
        "sin clave de API"
    )
    ia.cerrar()
