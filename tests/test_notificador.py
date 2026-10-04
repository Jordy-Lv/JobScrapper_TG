import json
import stat
import sys

import httpx
import pytest
import respx

from buscador_vacantes.config import cargar_configuracion
from buscador_vacantes.notificador_telegram import (
    API,
    NotificadorBotAPI,
    NotificadorHermesCLI,
    crear_notificador,
)

TOKEN = "123456789:AAFakeTokenFakeTokenFakeTokenFake12"
CHAT = "-100999"
BASE = f"{API}/bot{TOKEN}"


@pytest.fixture
def pausas():
    return []


@pytest.fixture
def bot(pausas):
    notificador = NotificadorBotAPI(TOKEN, dormir=pausas.append)
    yield notificador
    notificador.cerrar()


@respx.mock
def test_send_message_html_sin_vista_previa(bot):
    ruta = respx.post(f"{BASE}/sendMessage").mock(
        return_value=httpx.Response(200, json={"ok": True, "result": {"message_id": 77}})
    )
    resultado = bot.enviar_mensaje(CHAT, "<b>hola</b>")
    assert resultado.ok and resultado.message_id == 77
    cuerpo = json.loads(ruta.calls[0].request.content)
    assert cuerpo == {
        "chat_id": CHAT,
        "text": "<b>hola</b>",
        "parse_mode": "HTML",
        "link_preview_options": {"is_disabled": True},
    }
    # Con notificación normal: no se envía disable_notification
    assert "disable_notification" not in cuerpo


@respx.mock
def test_error_de_parseo(bot):
    respx.post(f"{BASE}/sendMessage").mock(
        return_value=httpx.Response(
            400,
            json={
                "ok": False,
                "error_code": 400,
                "description": "Bad Request: can't parse entities",
            },
        )  # fmt: skip
    )
    resultado = bot.enviar_mensaje(CHAT, "<b>roto")
    assert not resultado.ok
    assert resultado.codigo == 400
    assert "can't parse entities" in resultado.error


@respx.mock
def test_token_invalido_401(bot):
    respx.post(f"{BASE}/sendMessage").mock(
        return_value=httpx.Response(401, json={"ok": False, "description": "Unauthorized"})
    )
    resultado = bot.enviar_mensaje(CHAT, "x")
    assert resultado.codigo == 401
    assert "token del bot inválido" in resultado.error
    assert TOKEN not in resultado.error


@respx.mock
def test_429_espera_y_reintenta_una_vez(bot, pausas):
    ruta = respx.post(f"{BASE}/sendMessage")
    ruta.side_effect = [
        httpx.Response(429, json={"ok": False, "description": "Too Many Requests",
                                  "parameters": {"retry_after": 3}}),
        httpx.Response(200, json={"ok": True, "result": {"message_id": 1}}),
    ]  # fmt: skip
    assert bot.enviar_mensaje(CHAT, "x").ok
    assert pausas == [3]


@respx.mock
def test_429_con_espera_larga_falla(bot, pausas):
    respx.post(f"{BASE}/sendMessage").mock(
        return_value=httpx.Response(
            429, json={"ok": False, "parameters": {"retry_after": 600}, "description": "Flood"}
        )
    )
    resultado = bot.enviar_mensaje(CHAT, "x")
    assert not resultado.ok and resultado.codigo == 429
    assert pausas == []


@respx.mock
def test_error_de_conexion(bot):
    respx.post(f"{BASE}/sendMessage").mock(side_effect=httpx.ConnectError("sin red"))
    resultado = bot.enviar_mensaje(CHAT, "x")
    assert not resultado.ok and "conexión" in resultado.error


@respx.mock
def test_send_photo(bot, tmp_path):
    imagen = tmp_path / "banner.jpg"
    imagen.write_bytes(b"\xff\xd8\xff fake jpeg")
    ruta = respx.post(f"{BASE}/sendPhoto").mock(
        return_value=httpx.Response(200, json={"ok": True, "result": {"message_id": 5}})
    )
    assert bot.enviar_foto(CHAT, imagen).ok
    contenido = ruta.calls[0].request.content
    assert b'name="chat_id"' in contenido and CHAT.encode() in contenido
    assert b"fake jpeg" in contenido


def test_send_photo_sin_archivo(bot, tmp_path):
    resultado = bot.enviar_foto(CHAT, tmp_path / "no-existe.jpg")
    assert not resultado.ok and "no se pudo leer" in resultado.error


@pytest.fixture
def hermes_falso(tmp_path):
    """Script que imita `hermes send`: guarda sus argumentos y falla si el texto dice FALLA."""
    registro = tmp_path / "llamadas.json"
    script = tmp_path / "hermes"
    script.write_text(
        f"#!{sys.executable}\n"
        "import json, sys\n"
        f"open({str(registro)!r}, 'a').write(json.dumps(sys.argv[1:]) + '\\n')\n"
        "if 'FALLA' in sys.argv[-1]:\n"
        "    print('chat no encontrado', file=sys.stderr)\n"
        "    sys.exit(2)\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return script, registro


def test_hermes_cli_envia_texto_y_foto(hermes_falso, tmp_path):
    script, registro = hermes_falso
    notificador = NotificadorHermesCLI(str(script))
    assert notificador.enviar_mensaje(CHAT, "<b>hola</b>").ok
    assert notificador.enviar_foto(CHAT, tmp_path / "banner.jpg").ok
    llamadas = [json.loads(linea) for linea in registro.read_text().splitlines()]
    assert llamadas == [
        ["send", "-t", f"telegram:{CHAT}", "<b>hola</b>"],
        ["send", "-t", f"telegram:{CHAT}", f"MEDIA:{tmp_path / 'banner.jpg'}"],
    ]


def test_hermes_cli_fallo(hermes_falso):
    script, _ = hermes_falso
    resultado = NotificadorHermesCLI(str(script)).enviar_mensaje(CHAT, "FALLA")
    assert not resultado.ok
    assert resultado.codigo == 2
    assert "chat no encontrado" in resultado.error


def test_hermes_cli_comando_inexistente(tmp_path):
    resultado = NotificadorHermesCLI(str(tmp_path / "nada")).enviar_mensaje(CHAT, "x")
    assert not resultado.ok and "no se pudo ejecutar" in resultado.error


def test_crear_notificador():
    telegram = cargar_configuracion().telegram
    assert isinstance(crear_notificador(telegram, TOKEN), NotificadorBotAPI)
    with pytest.raises(ValueError):
        crear_notificador(telegram, None)
    cli = crear_notificador(telegram.model_copy(update={"modo": "hermes_cli"}), None)
    assert isinstance(cli, NotificadorHermesCLI)
