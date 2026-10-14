import sqlite3

import pytest

from buscador_vacantes.asistente.datos import ESQUEMA_VERSION, BaseAsistente, abrir_vacantes_ro
from buscador_vacantes.estado import Estado

AHORA = "2026-10-04T15:00:00+00:00"


@pytest.fixture
def base(tmp_path):
    base = BaseAsistente.abrir(tmp_path / "asistente.db")
    yield base
    base.cerrar()


def crear_usuario(base, telegram_id=111, directorio="u1"):
    with base.transaccion() as cx:
        return cx.execute(
            "INSERT INTO usuarios(telegram_id, directorio, creado) VALUES (?, ?, ?)",
            (telegram_id, directorio, AHORA),
        ).lastrowid


def test_crea_todas_las_tablas(base):
    assert {
        "usuarios",
        "codigos_vinculo",
        "navegadores",
        "cuentas_portal",
        "vacantes",
        "postulaciones",
        "postulacion_pasos",
        "respuestas",
        "evidencia",
        "banco_preguntas",
        "respuestas_aprendidas",
        "pendientes_usuario",
        "selectores",
        "ia_uso",
        "auditoria",
        "bajas",
        "kv",
    } <= set(base.tablas())


def test_wal_y_claves_foraneas(base):
    assert base.cx.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert base.cx.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_abrir_dos_veces_no_duplica_version(tmp_path):
    BaseAsistente.abrir(tmp_path / "a.db").cerrar()
    base = BaseAsistente.abrir(tmp_path / "a.db")
    assert base.cx.execute("SELECT COUNT(*) FROM esquema_version").fetchone()[0] == 1
    base.cerrar()


def test_una_postulacion_por_usuario_y_vacante(base):
    usuario = crear_usuario(base)
    sql = (
        "INSERT INTO postulaciones(usuario_id, id_corto, estado, creada, actualizada) "
        "VALUES (?, ?, 'en_cola', ?, ?)"
    )
    with base.transaccion() as cx:
        cx.execute(sql, (usuario, "abc123", AHORA, AHORA))
    with pytest.raises(sqlite3.IntegrityError), base.transaccion() as cx:
        cx.execute(sql, (usuario, "abc123", AHORA, AHORA))


def test_varios_completar_perfil_sin_vacante(base):
    usuario = crear_usuario(base)
    sql = (
        "INSERT INTO postulaciones(usuario_id, tipo, estado, creada, actualizada) "
        "VALUES (?, 'completar_perfil', 'en_cola', ?, ?)"
    )
    with base.transaccion() as cx:
        cx.execute(sql, (usuario, AHORA, AHORA))
        cx.execute(sql, (usuario, AHORA, AHORA))


def test_borrar_usuario_borra_en_cascada(base):
    usuario = crear_usuario(base)
    with base.transaccion() as cx:
        postulacion = cx.execute(
            "INSERT INTO postulaciones(usuario_id, id_corto, estado, creada, actualizada) "
            "VALUES (?, 'x', 'enviada', ?, ?)",
            (usuario, AHORA, AHORA),
        ).lastrowid
        cx.execute(
            "INSERT INTO respuestas(postulacion_id, pregunta, origen) VALUES (?, 'p', 'perfil')",
            (postulacion,),
        )
        cx.execute("DELETE FROM usuarios WHERE id = ?", (usuario,))
    assert base.cx.execute("SELECT COUNT(*) FROM postulaciones").fetchone()[0] == 0
    assert base.cx.execute("SELECT COUNT(*) FROM respuestas").fetchone()[0] == 0


def test_kv(base):
    assert base.kv_obtener("x") is None
    base.kv_guardar("x", "1")
    base.kv_guardar("x", "2")
    assert base.kv_obtener("x") == "2"


def test_vacantes_db_en_solo_lectura(tmp_path):
    ruta = tmp_path / "vacantes.db"
    Estado.abrir(ruta).cerrar()
    cx = abrir_vacantes_ro(ruta)
    assert cx.execute("SELECT COUNT(*) FROM vistas").fetchone()[0] == 0
    with pytest.raises(sqlite3.OperationalError):
        cx.execute("INSERT INTO kv(clave, valor) VALUES ('a', 'b')")
    cx.close()


def test_base_del_esquema_1_gana_la_ficha_de_la_vacante(tmp_path):
    ruta = tmp_path / "a.db"
    BaseAsistente.abrir(ruta).cerrar()
    viejo = sqlite3.connect(ruta)
    viejo.execute("ALTER TABLE vacantes DROP COLUMN ficha_json")
    viejo.execute("UPDATE esquema_version SET version = 1")
    viejo.commit()
    viejo.close()
    base = BaseAsistente.abrir(ruta)
    columnas = {f["name"] for f in base.cx.execute("PRAGMA table_info(vacantes)")}
    assert "ficha_json" in columnas
    assert base.cx.execute("SELECT version FROM esquema_version").fetchone()[0] == ESQUEMA_VERSION
    base.cerrar()
