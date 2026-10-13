import json
import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from buscador_vacantes.estado import (
    COLUMNAS_ESQUEMA_2,
    Estado,
    EstadoNoInicializado,
    a_texto,
    vacante_a_json,
    vacante_de_json,
)
from buscador_vacantes.modelo import Categoria, Vacante
from buscador_vacantes.normalizar import huella

AHORA = datetime(2026, 10, 3, 15, 0, tzinfo=UTC)


@pytest.fixture
def estado(tmp_path):
    e = Estado.abrir(tmp_path / "data" / "vacantes.db")
    yield e
    e.cerrar()


def vacante(
    fuente="linkedin",
    id_fuente="4012345",
    titulo="Practicante de Desarrollo",
    empresa="Redeban S.A.S.",
) -> Vacante:
    return Vacante(
        fuente=fuente,
        id_fuente=id_fuente,
        titulo=titulo,
        empresa=empresa,
        url=f"https://ejemplo/{id_fuente}",
        keyword="practicante sistemas",
        categoria=Categoria.PRACTICAS,
    )


def h(v: Vacante) -> str:
    return huella(v.titulo, v.empresa, v.clave)


def test_crea_base_con_todas_las_tablas(tmp_path, estado):
    assert (tmp_path / "data" / "vacantes.db").exists()
    assert estado.cx.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    esperadas = {
        "esquema_version",
        "vistas",
        "por_enviar",
        "fuentes_estado",
        "rotacion",
        "intentos",
        "corridas",
        "clasificaciones",
        "pendientes",
        "incidentes",
        "ia_uso",
        "kv",
    }
    assert esperadas <= set(estado.tablas())
    for tabla in esperadas:
        estado.cx.execute(f"SELECT * FROM {tabla} LIMIT 1").fetchall()


def test_reabrir_conserva_datos(tmp_path):
    ruta = tmp_path / "vacantes.db"
    e = Estado.abrir(ruta)
    e.kv_guardar("ultimo_banner", "2026-10-03")
    e.cerrar()
    e = Estado.abrir(ruta)
    assert e.kv_obtener("ultimo_banner") == "2026-10-03"
    assert e.cx.execute("SELECT COUNT(*) FROM esquema_version").fetchone()[0] == 1
    e.cerrar()


def test_misma_vacante_en_dos_fuentes(estado):
    enviada = vacante()
    estado.registrar_vista(enviada, h(enviada), enviada=True)
    otra = vacante(
        fuente="computrabajo",
        id_fuente="xyz",
        titulo="Practicante de desarrollo",
        empresa="Redeban",
    )
    assert estado.ya_vista(otra.clave, h(otra))


def test_misma_vacante_en_la_misma_fuente(estado):
    enviada = vacante()
    estado.registrar_vista(enviada, h(enviada), enviada=True)
    repetida = vacante(titulo="Otro título distinto")
    assert estado.ya_vista(repetida.clave, h(repetida))


def test_vacante_nueva_no_vista(estado):
    nueva = vacante()
    assert not estado.ya_vista(nueva.clave, h(nueva))


def test_seed_marca_vistas_sin_enviar(estado):
    for i in range(3):
        v = vacante(id_fuente=str(i), titulo=f"Practicante {i}")
        estado.registrar_vista(v, h(v))
    assert estado.contar_vistas() == 3
    assert estado.contar_vistas(enviadas=True) == 0
    v = vacante(id_fuente="1", titulo="Practicante 1")
    assert estado.ya_vista(v.clave, h(v))


def test_envio_a_chat_de_prueba_no_cuenta_para_el_canal(estado):
    v = vacante()
    estado.registrar_vista(v, h(v), enviada=True, prueba=True)
    assert estado.contar_vistas(enviadas=True) == 0
    assert estado.ya_vista(v.clave, h(v), prueba=True)
    assert not estado.ya_vista(v.clave, h(v), prueba=False)
    # Luego se envía al canal real: queda enviada
    estado.registrar_vista(v, h(v), enviada=True)
    assert estado.contar_vistas(enviadas=True) == 1
    assert estado.ya_vista(v.clave, h(v))


def test_registrar_dos_veces_no_duplica(estado):
    v = vacante()
    estado.registrar_vista(v, h(v))
    estado.registrar_vista(v, h(v), enviada=True)
    assert estado.contar_vistas() == 1
    assert estado.contar_vistas(enviadas=True) == 1


def test_por_enviar_ida_y_vuelta(estado):
    v = vacante()
    v.publicada = AHORA - timedelta(days=1)
    estado.guardar_por_enviar(v, h(v), AHORA)
    [(recuperada, huella_guardada, desde)] = estado.obtener_por_enviar()
    assert recuperada == v
    assert huella_guardada == h(v)
    assert desde == AHORA
    estado.quitar_por_enviar(v.clave)
    assert estado.obtener_por_enviar() == []


def test_bloqueo_de_envio_sin_inicializar(estado):
    assert not estado.inicializada()
    with pytest.raises(EstadoNoInicializado, match="--seed"):
        estado.exigir_inicializada()
    estado.marcar_inicializada(AHORA)
    estado.exigir_inicializada()
    assert estado.inicializada()


def insertar_vista(estado, clave, dias):
    estado.cx.execute(
        "INSERT INTO vistas(clave, huella, fuente, primera_vez) VALUES (?, ?, 'x', ?)",
        (clave, clave, a_texto(AHORA - timedelta(days=dias))),
    )


def test_limpieza_por_antiguedad(estado):
    with estado.transaccion() as cx:
        insertar_vista(estado, "x:91", 91)
        insertar_vista(estado, "x:89", 89)
        for dias in (31, 29):
            ts = a_texto(AHORA - timedelta(days=dias))
            cx.execute("INSERT INTO intentos(ts, fuente) VALUES (?, 'linkedin')", (ts,))
            cx.execute("INSERT INTO corridas(inicio, modo) VALUES (?, 'normal')", (ts,))
        viejo = a_texto(AHORA - timedelta(days=60))
        cx.execute(
            "INSERT INTO incidentes(fuente, tipo, abierto_desde) VALUES ('linkedin', 'bloqueo', ?)",
            (viejo,),
        )
        cx.execute(
            "INSERT INTO incidentes(fuente, tipo, abierto_desde, cerrado_en) "
            "VALUES ('magneto', 'cambio_html', ?, ?)",
            (viejo, viejo),
        )
    borrados = estado.limpiar(AHORA, 90, 30)
    assert borrados["vistas"] == 1
    assert borrados["intentos"] == 1
    assert borrados["corridas"] == 1
    assert borrados["incidentes"] == 1
    claves = [f[0] for f in estado.cx.execute("SELECT clave FROM vistas")]
    assert claves == ["x:89"]
    abiertos = estado.cx.execute(
        "SELECT fuente FROM incidentes WHERE cerrado_en IS NULL"
    ).fetchall()
    assert [f[0] for f in abiertos] == ["linkedin"]


def test_promover_prueba(estado):
    v1, v2 = vacante(id_fuente="1", titulo="A"), vacante(id_fuente="2", titulo="B")
    estado.registrar_vista(v1, h(v1), enviada=True, prueba=True)
    estado.registrar_vista(v2, h(v2))  # sembrada: no cambia
    assert not estado.ya_vista(v1.clave, h(v1))
    assert estado.promover_prueba() == 1
    assert estado.ya_vista(v1.clave, h(v1))
    assert estado.contar_vistas(enviadas=True) == 1
    assert estado.promover_prueba() == 0


# --- Esquema 2 y exige_modalidad ---


def test_json_de_pendientes_conserva_exige_modalidad():
    v = vacante()
    v.exige_modalidad = "remoto_o_hibrido"
    assert vacante_de_json(vacante_a_json(v)).exige_modalidad == "remoto_o_hibrido"
    assert vacante_de_json(vacante_a_json(vacante())).exige_modalidad is None


def test_json_antiguo_sin_exige_modalidad_se_lee():
    datos = json.loads(vacante_a_json(vacante()))
    del datos["exige_modalidad"]
    assert vacante_de_json(json.dumps(datos)).exige_modalidad is None


def test_base_nueva_nace_en_el_esquema_2(estado):
    assert estado.cx.execute("SELECT version FROM esquema_version").fetchone()[0] == 2
    for tabla, columna, _ in COLUMNAS_ESQUEMA_2:
        columnas = {f["name"] for f in estado.cx.execute(f"PRAGMA table_info({tabla})")}
        assert columna in columnas, (tabla, columna)


def crear_base_esquema_1(ruta):
    """Base como la dejaba la versión anterior: las tablas sin las columnas del esquema 2."""
    cx = sqlite3.connect(ruta)
    cx.executescript(
        """
        CREATE TABLE esquema_version (version INTEGER NOT NULL);
        INSERT INTO esquema_version VALUES (1);
        CREATE TABLE vistas (
            clave TEXT PRIMARY KEY, huella TEXT NOT NULL, fuente TEXT NOT NULL, titulo TEXT,
            empresa TEXT, url TEXT, categoria TEXT, primera_vez TEXT NOT NULL,
            enviada_en TEXT, prueba_en TEXT
        );
        INSERT INTO vistas(clave, huella, fuente, titulo, primera_vez, enviada_en)
        VALUES ('linkedin:1', 'h1', 'linkedin', 'Practicante', '2026-10-01T00:00:00+00:00',
                '2026-10-01T00:00:00+00:00');
        CREATE TABLE corridas (
            id INTEGER PRIMARY KEY AUTOINCREMENT, inicio TEXT NOT NULL, fin TEXT,
            modo TEXT NOT NULL, crudas INTEGER NOT NULL DEFAULT 0, descartes_json TEXT,
            duplicadas INTEGER NOT NULL DEFAULT 0, dudosas INTEGER NOT NULL DEFAULT 0,
            ia_aceptadas INTEGER NOT NULL DEFAULT 0, ia_rechazadas INTEGER NOT NULL DEFAULT 0,
            pendientes INTEGER NOT NULL DEFAULT 0, enviadas INTEGER NOT NULL DEFAULT 0,
            sin_red INTEGER NOT NULL DEFAULT 0, error TEXT
        );
        INSERT INTO corridas(inicio, modo, crudas)
        VALUES ('2026-10-01T00:00:00+00:00', 'normal', 7);
        CREATE TABLE clasificaciones (
            huella TEXT PRIMARY KEY, aceptar INTEGER NOT NULL, categoria TEXT, motivo TEXT,
            ts TEXT NOT NULL
        );
        INSERT INTO clasificaciones
        VALUES ('h1', 1, 'practicas', 'ok', '2026-10-01T00:00:00+00:00');
        """
    )
    cx.commit()
    cx.close()


def test_base_del_esquema_1_migra_a_2_sin_perder_filas(tmp_path):
    ruta = tmp_path / "vacantes.db"
    crear_base_esquema_1(ruta)
    e = Estado.abrir(ruta)
    assert e.cx.execute("SELECT version FROM esquema_version").fetchone()[0] == 2
    vista = e.cx.execute("SELECT * FROM vistas").fetchone()
    assert (vista["clave"], vista["enviada_en"], vista["ubicacion"], vista["modalidad"]) == (
        "linkedin:1", "2026-10-01T00:00:00+00:00", None, None,
    )  # fmt: skip
    corrida = e.cx.execute("SELECT * FROM corridas").fetchone()
    assert (corrida["crudas"], corrida["practicas_recategorizadas"]) == (7, 0)
    assert corrida["practicas_rechazadas"] == 0
    clasificacion = e.cx.execute("SELECT * FROM clasificaciones").fetchone()
    assert (clasificacion["huella"], clasificacion["version_prompt"]) == ("h1", None)
    # Una base ya migrada vuelve a abrirse sin errores
    e.cerrar()
    Estado.abrir(ruta).cerrar()


def test_volver_a_migrar_tras_bajar_la_version_tolera_las_columnas_existentes(tmp_path):
    ruta = tmp_path / "vacantes.db"
    Estado.abrir(ruta).cerrar()
    cx = sqlite3.connect(ruta)
    cx.execute("UPDATE esquema_version SET version = 1")  # vuelta atrás manual
    cx.commit()
    cx.close()
    e = Estado.abrir(ruta)
    assert e.cx.execute("SELECT version FROM esquema_version").fetchone()[0] == 2
    e.cerrar()


def test_esquema_mas_nuevo_que_el_codigo_se_rechaza(tmp_path):
    ruta = tmp_path / "vacantes.db"
    Estado.abrir(ruta).cerrar()
    cx = sqlite3.connect(ruta)
    cx.execute("UPDATE esquema_version SET version = 3")
    cx.commit()
    cx.close()
    with pytest.raises(RuntimeError, match="esquema 3"):
        Estado.abrir(ruta)


def test_registrar_vista_guarda_ubicacion_y_modalidad(estado):
    v = vacante()
    v.ubicacion, v.modalidad = "Cartagena, Bolívar", "Presencial"
    estado.registrar_vista(v, h(v), enviada=True)
    fila = estado.cx.execute("SELECT ubicacion, modalidad FROM vistas").fetchone()
    assert (fila["ubicacion"], fila["modalidad"]) == ("Cartagena, Bolívar", "Presencial")
