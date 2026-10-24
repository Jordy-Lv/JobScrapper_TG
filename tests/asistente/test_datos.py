import sqlite3

import pytest

from buscador_vacantes.asistente.datos import ESQUEMA_VERSION, BaseAsistente, abrir_vacantes_ro
from buscador_vacantes.comun.estado import Estado

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


ESQUEMA_V3 = """
CREATE TABLE esquema_version (version INTEGER NOT NULL);
INSERT INTO esquema_version VALUES (3);
CREATE TABLE preferencias_portal (
    usuario_id INTEGER NOT NULL, plataforma TEXT NOT NULL,
    automatico INTEGER NOT NULL DEFAULT 1, umbral INTEGER, avisar INTEGER NOT NULL DEFAULT 1,
    actualizada TEXT, PRIMARY KEY (usuario_id, plataforma)
);
CREATE TABLE respuestas (
    id INTEGER PRIMARY KEY AUTOINCREMENT, postulacion_id INTEGER NOT NULL, campo TEXT,
    pregunta TEXT NOT NULL, respuesta TEXT, origen TEXT NOT NULL
);
CREATE TABLE banco_preguntas (
    pregunta_norm TEXT PRIMARY KEY, campo TEXT NOT NULL, parametro TEXT, origen TEXT NOT NULL,
    usos INTEGER NOT NULL DEFAULT 0, creada TEXT NOT NULL
);
CREATE TABLE pendientes_usuario (
    id INTEGER PRIMARY KEY AUTOINCREMENT, usuario_id INTEGER NOT NULL, postulacion_id INTEGER,
    pregunta TEXT NOT NULL, pregunta_norm TEXT NOT NULL, opciones_json TEXT, campo TEXT,
    creada TEXT NOT NULL, respondida_en TEXT, respuesta TEXT
);
INSERT INTO banco_preguntas VALUES ('aspiracion salarial', 'salario', NULL, 'semilla', 3, 'x');
INSERT INTO banco_preguntas VALUES
    ('que programa estudias y en que institucion', 'programa', NULL, 'ia', 1, 'x');
INSERT INTO respuestas(postulacion_id, campo, pregunta, respuesta, origen)
    VALUES (7, 'salario', '¿Aspiración salarial?', '1300000', 'perfil');
INSERT INTO respuestas(postulacion_id, campo, pregunta, respuesta, origen)
    VALUES (7, 'salario', 'Aspiración salarial', '1300000', 'perfil');
INSERT INTO pendientes_usuario(usuario_id, postulacion_id, pregunta, pregunta_norm, creada)
    VALUES (1, 7, '¿Ciudad?', 'ciudad', 'x');
INSERT INTO preferencias_portal(usuario_id, plataforma) VALUES (1, 'computrabajo');
"""


def test_migracion_v4_desde_una_base_v3(tmp_path):
    ruta = tmp_path / "v3.db"
    cx = sqlite3.connect(ruta)
    cx.executescript(ESQUEMA_V3)
    cx.close()
    base = BaseAsistente.abrir(ruta)
    assert ESQUEMA_VERSION == 6
    assert base.cx.execute("SELECT version FROM esquema_version").fetchone()[0] == 6
    banco = base.cx.execute("SELECT pregunta_norm, origen FROM banco_preguntas").fetchall()
    assert [tuple(f) for f in banco] == [("aspiracion salarial", "semilla")]  # sin las de IA
    filas = base.cx.execute("SELECT pregunta_norm, estado FROM respuestas").fetchall()
    assert [tuple(f) for f in filas] == [("aspiracion salarial", "enviada")]  # sin repetidas
    pendiente = base.cx.execute("SELECT tipo FROM pendientes_usuario").fetchone()
    assert pendiente["tipo"] == "formulario"
    pref = base.cx.execute("SELECT revisar_respuestas FROM preferencias_portal").fetchone()
    assert pref["revisar_respuestas"] == 0
    with pytest.raises(sqlite3.IntegrityError), base.transaccion() as c:
        c.execute(
            "INSERT INTO respuestas(postulacion_id, pregunta, origen, pregunta_norm) "
            "VALUES (7, 'Aspiración salarial', 'perfil', 'aspiracion salarial')"
        )
    base.cerrar()
    BaseAsistente.abrir(ruta).cerrar()  # reabrir no vuelve a migrar ni falla


def test_migracion_v5_desde_una_base_v4(tmp_path):
    ruta = tmp_path / "v4.db"
    BaseAsistente.abrir(ruta).cerrar()
    viejo = sqlite3.connect(ruta)
    viejo.executescript(
        "DROP TABLE recetas; DROP TABLE parches_flujo; DROP TABLE dominios_barrera;"
        "ALTER TABLE postulaciones DROP COLUMN receta_id;"
        "ALTER TABLE postulaciones DROP COLUMN parches_json;"
        "UPDATE esquema_version SET version = 4;"
    )
    viejo.close()
    base = BaseAsistente.abrir(ruta)
    assert base.cx.execute("SELECT version FROM esquema_version").fetchone()[0] == ESQUEMA_VERSION
    assert {"recetas", "parches_flujo", "dominios_barrera"} <= set(base.tablas())
    columnas = {f["name"] for f in base.cx.execute("PRAGMA table_info(postulaciones)")}
    assert {"receta_id", "parches_json"} <= columnas
    base.cerrar()


def test_migracion_v6_desde_una_base_v5_deja_a_todos_en_normal(tmp_path):
    ruta = tmp_path / "v5.db"
    BaseAsistente.abrir(ruta).cerrar()
    viejo = sqlite3.connect(ruta)
    viejo.executescript(
        "INSERT INTO usuarios(telegram_id, estado, directorio, creado) "
        "VALUES (1, 'activo', 'u1', 'x');"
        "INSERT INTO postulaciones(usuario_id, estado, creada, actualizada) "
        "VALUES (1, 'enviada', 'x', 'x');"
        "ALTER TABLE usuarios DROP COLUMN nivel_ia;"
        "ALTER TABLE postulaciones DROP COLUMN nivel_ia;"
        "UPDATE esquema_version SET version = 5;"
    )
    viejo.close()
    base = BaseAsistente.abrir(ruta)
    assert base.cx.execute("SELECT version FROM esquema_version").fetchone()[0] == ESQUEMA_VERSION
    assert base.cx.execute("SELECT nivel_ia FROM usuarios").fetchone()["nivel_ia"] == "normal"
    # Las postulaciones anteriores no llevan nivel: nunca se encolaron con uno
    assert base.cx.execute("SELECT nivel_ia FROM postulaciones").fetchone()["nivel_ia"] is None
    base.cerrar()
