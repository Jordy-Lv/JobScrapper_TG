import asyncio
import socket
import sqlite3
import sys

import pytest

pytest.importorskip("fastapi", reason="requiere uv sync --group asistente")
pytest.importorskip("telegram", reason="requiere uv sync --group asistente")
pytest.importorskip("uvicorn", reason="requiere uv sync --group asistente")

import httpx  # noqa: E402
import respx  # noqa: E402

from buscador_vacantes import config as cfg  # noqa: E402
from buscador_vacantes.asistente import cli, servicio  # noqa: E402
from buscador_vacantes.asistente.cifrado import generar_clave  # noqa: E402
from buscador_vacantes.estado import Estado  # noqa: E402

TOKEN = "123456:ABC-token-de-prueba"
BOT = {"id": 123456, "is_bot": True, "first_name": "Asistente", "username": "AsistentePruebaBot"}


def puerto_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def configuracion(tmp_path, activo=True, puerto=8787):
    Estado.abrir(tmp_path / "vacantes.db").cerrar()
    base = cfg.cargar_configuracion()
    asistente = base.asistente.model_copy(update={
        "activo": activo,
        "bot_usuario": "AsistentePruebaBot",
        "dueno_telegram_id": 1,
        "base_datos": tmp_path / "asistente.db",
        "archivos": tmp_path / "archivos",
        "vacantes_db": tmp_path / "vacantes.db",
        "api": base.asistente.api.model_copy(update={"host": "127.0.0.1", "puerto": puerto}),
    })  # fmt: skip
    return base.model_copy(update={"asistente": asistente})


def secretos(token=TOKEN):
    return cfg.Secretos(asistente_bot_token=token, asistente_clave_cifrado=generar_clave())


def test_con_activo_falso_sale_sin_construir_el_servicio(tmp_path, monkeypatch, capsys):
    def no_debe_construirse(*_a, **_k):
        raise AssertionError("no debe construirse con activo: false")

    monkeypatch.setattr(servicio, "Servicio", no_debe_construirse)
    assert cli._servicio(configuracion(tmp_path, activo=False), secretos()) == 0
    assert "desactivado" in capsys.readouterr().out
    assert not (tmp_path / "asistente.db").exists()  # ni siquiera se crea la base


def test_sin_token_del_bot_se_rechaza_indicando_el_secreto(tmp_path):
    with pytest.raises(cfg.ErrorConfiguracion, match="ASISTENTE_BOT_TOKEN"):
        cli._servicio(configuracion(tmp_path), secretos(token=None))


def test_sin_dependencias_muestra_el_mensaje_de_instalacion(tmp_path, monkeypatch, capsys):
    # None en sys.modules hace que importar el módulo falle como si faltaran las dependencias
    monkeypatch.setitem(sys.modules, "buscador_vacantes.asistente.servicio", None)
    assert cli._servicio(configuracion(tmp_path), secretos()) == 2
    assert "uv sync --group asistente" in capsys.readouterr().err


def telegram_simulado(llamadas: list[str]):
    """Bot API simulada: getMe responde el bot y getUpdates no trae nada (con una pausa corta)."""

    async def responder(request: httpx.Request) -> httpx.Response:
        metodo = request.url.path.rsplit("/", 1)[-1]
        llamadas.append(metodo)
        if metodo == "getUpdates":
            await asyncio.sleep(0.05)
        resultado = BOT if metodo == "getMe" else [] if metodo == "getUpdates" else True
        return httpx.Response(200, json={"ok": True, "result": resultado})

    return responder


async def esperar_api(puerto: int, tiempo_s: float = 15) -> httpx.Response:
    limite = asyncio.get_running_loop().time() + tiempo_s
    async with httpx.AsyncClient() as cliente:
        while True:
            try:
                return await cliente.post(f"http://127.0.0.1:{puerto}/api/v1/latido", json={})
            except httpx.TransportError:
                if asyncio.get_running_loop().time() > limite:
                    raise
                await asyncio.sleep(0.05)


def test_arranque_y_parada_del_servicio(tmp_path):
    puerto = puerto_libre()
    llamadas: list[str] = []
    servidor = servicio.Servicio(configuracion(tmp_path, puerto=puerto), secretos())

    async def escenario():
        ejecucion = asyncio.create_task(servidor.ejecutar())
        try:
            sin_token = await esperar_api(puerto)
            async with httpx.AsyncClient() as cliente:
                fuera = await cliente.get(f"http://127.0.0.1:{puerto}/otra-ruta")
            assert sin_token.status_code == 401  # la API responde, pero exige el token
            assert fuera.status_code == 404
            await asyncio.sleep(0.2)  # deja correr un ciclo de tareas periódicas y el sondeo
            assert not ejecucion.done()
        finally:
            servidor.detener.set()  # lo mismo que hace SIGTERM
        await asyncio.wait_for(ejecucion, timeout=20)  # el cierre limpio termina por sí solo

    with respx.mock(assert_all_called=False) as telegram:
        telegram.route(host="127.0.0.1").pass_through()
        telegram.route(host="api.telegram.org").mock(side_effect=telegram_simulado(llamadas))
        asyncio.run(escenario())

    assert "getMe" in llamadas and "getUpdates" in llamadas  # el bot arrancó y sondeó
    with pytest.raises(sqlite3.ProgrammingError):  # la base quedó cerrada
        servidor.nucleo.base.cx.execute("SELECT 1")
    with pytest.raises(OSError), socket.create_connection(("127.0.0.1", puerto), timeout=1):
        pass  # el puerto de la API quedó libre
