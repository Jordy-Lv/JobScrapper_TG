import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

pytest.importorskip("telegram", reason="requiere uv sync --group asistente")

from telegram.error import BadRequest, NetworkError  # noqa: E402

from buscador_vacantes.asistente.datos import BaseAsistente  # noqa: E402
from buscador_vacantes.asistente.membresia import Comprobador, SinPermisos  # noqa: E402
from buscador_vacantes.asistente.usuarios import EstadoUsuario, Usuarios  # noqa: E402
from buscador_vacantes.estado import a_texto  # noqa: E402

AHORA = datetime(2026, 10, 4, 15, 0, tzinfo=UTC)


@pytest.fixture
def usuarios(tmp_path):
    base = BaseAsistente.abrir(tmp_path / "asistente.db")
    yield Usuarios(base, tmp_path / "archivos")
    base.cerrar()


def encolar(usuarios, usuario, id_corto, estado="en_cola"):
    with usuarios.base.transaccion() as cx:
        return cx.execute(
            "INSERT INTO postulaciones(usuario_id, id_corto, estado, creada, actualizada) "
            "VALUES (?, ?, ?, ?, ?)",
            (usuario.id, id_corto, estado, a_texto(AHORA), a_texto(AHORA)),
        ).lastrowid


def estado_postulacion(usuarios, pid):
    return usuarios.base.cx.execute(
        "SELECT estado FROM postulaciones WHERE id = ?", (pid,)
    ).fetchone()[0]


class BotFalso:
    def __init__(self, respuestas):
        self.respuestas = respuestas  # telegram_id -> status | excepción
        self.consultas = 0

    async def get_chat_member(self, chat_id, user_id):
        self.consultas += 1
        r = self.respuestas[user_id]
        if isinstance(r, Exception):
            raise r
        return SimpleNamespace(status=r, is_member=r != "left")


def comprobador(usuarios, respuestas):
    avisos = []

    async def avisar(texto):
        avisos.append(texto)

    bot = BotFalso(respuestas)
    return Comprobador(bot, -100, usuarios, cache_min=10, avisar_dueno=avisar), bot, avisos


def test_no_miembro_rechazado_sin_guardar_datos(usuarios):
    c, _, _ = comprobador(usuarios, {222: "left"})
    assert asyncio.run(c.es_miembro_nuevo(222)) is False
    assert usuarios.obtener(222) is None
    assert usuarios.base.cx.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0] == 0


def test_miembro_nuevo_aceptado(usuarios):
    c, _, _ = comprobador(usuarios, {222: "member"})
    assert asyncio.run(c.es_miembro_nuevo(222)) is True


def test_comprobar_usa_cache(usuarios):
    usuario = usuarios.crear(111, "Ana", AHORA)
    c, bot, _ = comprobador(usuarios, {111: "member"})
    asyncio.run(c.comprobar(usuario, AHORA + timedelta(minutes=5)))
    assert bot.consultas == 0
    asyncio.run(c.comprobar(usuario, AHORA + timedelta(minutes=15)))
    assert bot.consultas == 1


def test_kicked_suspende_en_la_tarea_diaria(usuarios):
    usuario = usuarios.crear(111, "Ana", AHORA)
    usuarios.completar_alta(usuario)
    pid = encolar(usuarios, usuario, "aaa")
    c, _, _ = comprobador(usuarios, {111: "kicked"})
    asyncio.run(c.comprobar_todos(AHORA))
    assert usuarios.obtener(111).estado == EstadoUsuario.SUSPENDIDO
    assert estado_postulacion(usuarios, pid) == "cancelada"


def test_sin_permisos_bloquea_altas_y_avisa_una_vez(usuarios):
    usuarios.crear(111, "Ana", AHORA)
    error = BadRequest("Chat_admin_required")
    c, _, avisos = comprobador(usuarios, {111: error, 222: error})
    asyncio.run(c.comprobar_todos(AHORA))
    assert usuarios.obtener(111).estado == EstadoUsuario.ALTA  # sin cambios
    assert usuarios.altas_bloqueadas()
    with pytest.raises(SinPermisos):
        asyncio.run(c.es_miembro_nuevo(222))
    asyncio.run(c.comprobar_todos(AHORA))
    assert len(avisos) == 1


def test_error_de_red_no_cambia_nada(usuarios):
    usuario = usuarios.crear(111, "Ana", AHORA)
    c, _, avisos = comprobador(usuarios, {111: NetworkError("sin red")})
    despues = asyncio.run(c.comprobar(usuario, AHORA + timedelta(hours=1)))
    assert despues.estado == EstadoUsuario.ALTA
    assert not usuarios.altas_bloqueadas() and avisos == []
