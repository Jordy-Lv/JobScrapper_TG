from datetime import UTC, datetime, timedelta

import pytest

from buscador_vacantes.asistente.datos import BaseAsistente
from buscador_vacantes.asistente.usuarios_linkedin import UsuariosLinkedin

T0 = datetime(2026, 10, 4, 15, 0, tzinfo=UTC)  # 10:00 en Bogotá


@pytest.fixture
def linkedin(tmp_path):
    base = BaseAsistente.abrir(tmp_path / "a.db")
    with base.transaccion() as cx:
        for uid in (1, 2):
            cx.execute(
                "INSERT INTO usuarios(id, telegram_id, directorio, creado) VALUES (?, ?, ?, 'x')",
                (uid, uid, f"u{uid}"),
            )
    yield UsuariosLinkedin(base)
    base.cerrar()


def test_sin_aceptar_no_hay_estado_ni_permiso(linkedin):
    assert linkedin.estado(1) is None
    assert not linkedin.acepto(1, 1)
    assert linkedin.fijar(1, sencilla=False) is False  # sin aceptar no hay interruptores


def test_aceptar_guarda_version_y_fecha_y_enciende_los_dos_interruptores(linkedin):
    linkedin.aceptar(1, 1, T0)
    estado = linkedin.estado(1)
    assert (estado.version, estado.aceptado_en) == (1, T0)
    assert estado.sencilla and estado.externas and estado.pausado_hasta is None
    assert linkedin.acepto(1, 1) and not linkedin.acepto(2, 1)


def test_una_version_nueva_del_texto_pide_aceptar_de_nuevo_y_conserva_los_interruptores(linkedin):
    linkedin.aceptar(1, 1, T0)
    linkedin.fijar(1, externas=False)
    assert not linkedin.acepto(1, 2)
    linkedin.aceptar(1, 2, T0 + timedelta(days=30))
    assert linkedin.acepto(1, 2)
    estado = linkedin.estado(1)
    assert estado.sencilla and not estado.externas


def test_los_interruptores_son_independientes(linkedin):
    linkedin.aceptar(1, 1, T0)
    assert linkedin.fijar(1, sencilla=False)
    assert not linkedin.estado(1).sencilla and linkedin.estado(1).externas
    assert linkedin.fijar(1, externas=False)
    assert not linkedin.estado(1).externas
    assert linkedin.fijar(1, sencilla=True, externas=True)
    assert linkedin.estado(1).sencilla and linkedin.estado(1).externas


def test_la_pausa_vence_sola(linkedin):
    linkedin.aceptar(1, 1, T0)
    assert linkedin.pausado_hasta(1, T0) is None
    linkedin.pausar(1, T0 + timedelta(hours=24))
    assert linkedin.pausado_hasta(1, T0 + timedelta(hours=23)) == T0 + timedelta(hours=24)
    assert linkedin.pausado_hasta(1, T0 + timedelta(hours=24, seconds=1)) is None
    assert linkedin.pausado_hasta(2, T0) is None  # es por usuario


def test_las_aperturas_se_cuentan_por_usuario_y_por_dia_de_bogota(linkedin):
    linkedin.registrar_apertura(1, "abc", T0)
    linkedin.registrar_apertura(1, "def", T0 + timedelta(hours=1))
    linkedin.registrar_apertura(2, "abc", T0)
    assert linkedin.aperturas_hoy(1, T0 + timedelta(hours=2)) == 2
    assert linkedin.aperturas_hoy(2, T0) == 1
    assert linkedin.ultima_apertura(1) == T0 + timedelta(hours=1)
    # Al día siguiente (hora de Bogotá) el contador vuelve a cero
    assert linkedin.aperturas_hoy(1, T0 + timedelta(days=1)) == 0
    assert linkedin.manana(T0) == datetime(2026, 10, 5, 5, 0, tzinfo=UTC)
    assert linkedin.ultima_apertura(2) == T0
    assert UsuariosLinkedin.ultima_apertura(linkedin, 99) is None
