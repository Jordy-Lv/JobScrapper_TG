from datetime import UTC, datetime, timedelta

import pytest

from buscador_vacantes.asistente.datos import BaseAsistente
from buscador_vacantes.asistente.usuarios import (
    EstadoUsuario,
    Membresia,
    Usuarios,
    interpretar_miembro,
)
from buscador_vacantes.estado import a_texto

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


@pytest.mark.parametrize(
    ("status", "is_member", "esperado"),
    [
        ("creator", None, Membresia.MIEMBRO),
        ("administrator", None, Membresia.MIEMBRO),
        ("member", None, Membresia.MIEMBRO),
        ("restricted", True, Membresia.MIEMBRO),
        ("restricted", False, Membresia.NO_MIEMBRO),
        ("left", None, Membresia.NO_MIEMBRO),
        ("kicked", None, Membresia.NO_MIEMBRO),
    ],
)
def test_interpretar_miembro(status, is_member, esperado):
    assert interpretar_miembro(status, is_member) == esperado


def test_alta_crea_directorio_privado_y_paso_inicial(usuarios):
    usuario = usuarios.crear(111, "Ana", AHORA)
    assert usuario.estado == EstadoUsuario.ALTA
    assert usuario.paso_alta == "politica"
    assert usuarios.directorio(usuario).is_dir()
    assert "Ana" not in repr(usuario)


def test_politica_versionada(usuarios):
    usuario = usuarios.crear(111, "Ana", AHORA)
    assert usuarios.requiere_politica(usuario, 1)
    usuarios.aceptar_politica(usuario, 1, AHORA)
    usuario = usuarios.obtener(111)
    assert not usuarios.requiere_politica(usuario, 1)
    assert usuarios.requiere_politica(usuario, 2)  # nueva versión: aceptar de nuevo


def test_paso_del_alta_persistente(usuarios):
    usuario = usuarios.crear(111, "Ana", AHORA)
    usuarios.fijar_paso(usuario, "cuestionario:5")
    assert usuarios.obtener(111).paso_alta == "cuestionario:5"
    usuarios.completar_alta(usuarios.obtener(111))
    usuario = usuarios.obtener(111)
    assert usuario.estado == EstadoUsuario.ACTIVO and usuario.paso_alta is None


def test_sale_del_grupo_suspende_y_cancela_pendientes(usuarios):
    usuario = usuarios.crear(111, "Ana", AHORA)
    usuarios.completar_alta(usuario)
    pendiente = encolar(usuarios, usuario, "aaa")
    enviada = encolar(usuarios, usuario, "bbb", "enviada")
    usuario = usuarios.aplicar_membresia(usuarios.obtener(111), Membresia.NO_MIEMBRO, AHORA)
    assert usuario.estado == EstadoUsuario.SUSPENDIDO
    assert estado_postulacion(usuarios, pendiente) == "cancelada"
    assert estado_postulacion(usuarios, enviada) == "enviada"


def test_vuelve_al_grupo_reactiva(usuarios):
    usuario = usuarios.crear(111, "Ana", AHORA)
    usuarios.completar_alta(usuario)
    usuarios.aplicar_membresia(usuarios.obtener(111), Membresia.NO_MIEMBRO, AHORA)
    usuario = usuarios.aplicar_membresia(usuarios.obtener(111), Membresia.MIEMBRO, AHORA)
    assert usuario.estado == EstadoUsuario.ACTIVO


def test_suspension_del_admin_no_se_levanta_por_membresia(usuarios):
    usuario = usuarios.crear(111, "Ana", AHORA)
    usuarios.completar_alta(usuario)
    usuarios.suspender(usuarios.obtener(111), actor=999, ahora=AHORA)
    usuario = usuarios.aplicar_membresia(usuarios.obtener(111), Membresia.MIEMBRO, AHORA)
    assert usuario.estado == EstadoUsuario.SUSPENDIDO
    auditoria = usuarios.base.cx.execute("SELECT actor, accion FROM auditoria").fetchall()
    assert [tuple(f) for f in auditoria] == [(999, "suspender")]


def test_cache_de_membresia(usuarios):
    usuario = usuarios.crear(111, "Ana", AHORA)
    assert usuarios.membresia_vigente(usuario, AHORA + timedelta(minutes=5), cache_min=10)
    assert not usuarios.membresia_vigente(usuario, AHORA + timedelta(minutes=11), cache_min=10)


def test_bloqueo_de_altas_no_toca_existentes(usuarios):
    usuarios.crear(111, "Ana", AHORA)
    usuarios.bloquear_altas("el bot no es administrador del grupo")
    assert usuarios.altas_bloqueadas()
    assert usuarios.obtener(111).estado == EstadoUsuario.ALTA
    usuarios.desbloquear_altas()
    assert not usuarios.altas_bloqueadas()


def test_borrar_no_deja_archivos_ni_filas(usuarios):
    usuario = usuarios.crear(111, "Ana", AHORA)
    (usuarios.directorio(usuario) / "cv.pdf").write_bytes(b"%PDF")
    pid = encolar(usuarios, usuario, "aaa", "enviada")
    with usuarios.base.transaccion() as cx:
        cx.execute(
            "INSERT INTO respuestas(postulacion_id, pregunta, origen) VALUES (?, 'p', 'perfil')",
            (pid,),
        )
        cx.execute(
            "INSERT INTO respuestas_aprendidas(usuario_id, pregunta_norm, respuesta, actualizada)"
            " VALUES (?, 'p', 'r', ?)",
            (usuario.id, a_texto(AHORA)),
        )
    usuarios.borrar(usuario, AHORA)
    assert not usuarios.directorio(usuario).exists()
    for tabla in ("usuarios", "postulaciones", "respuestas", "respuestas_aprendidas"):
        assert usuarios.base.cx.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0] == 0
    assert usuarios.base.cx.execute("SELECT COUNT(*) FROM bajas").fetchone()[0] == 1


def test_inactividad_aviso_y_borrado(usuarios):
    usuario = usuarios.crear(111, "Ana", AHORA)
    dentro_de_un_anio = AHORA + timedelta(days=370)
    avisar = usuarios.por_avisar_inactividad(dentro_de_un_anio, meses=12)
    assert [u.id for u in avisar] == [usuario.id]
    usuarios.marcar_aviso_inactividad(usuario, dentro_de_un_anio)
    assert usuarios.por_avisar_inactividad(dentro_de_un_anio, meses=12) == []
    assert usuarios.por_borrar_inactividad(dentro_de_un_anio + timedelta(days=10)) == []
    borrar = usuarios.por_borrar_inactividad(dentro_de_un_anio + timedelta(days=31))
    assert [u.id for u in borrar] == [usuario.id]


def test_responder_al_aviso_cancela_el_borrado(usuarios):
    usuario = usuarios.crear(111, "Ana", AHORA)
    aviso = AHORA + timedelta(days=370)
    usuarios.marcar_aviso_inactividad(usuario, aviso)
    usuarios.tocar_actividad(usuario, aviso + timedelta(days=1))
    assert usuarios.por_borrar_inactividad(aviso + timedelta(days=31)) == []
