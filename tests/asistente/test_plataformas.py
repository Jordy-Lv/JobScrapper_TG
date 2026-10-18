"""Coherencia de plataformas: con `automatica: true` necesita nombre, dominio y selectores."""

from pathlib import Path

from buscador_vacantes.asistente import textos as t
from buscador_vacantes.asistente.vacantes import PLATAFORMAS
from buscador_vacantes.comun import config as cfg
from buscador_vacantes.comun.config import AsistentePlataforma, cargar_configuracion

RUTA_SELECTORES = cfg.RAIZ / "assets" / "asistente" / "selectores"


def incompletas(
    plataformas: dict[str, AsistentePlataforma],
    nombres: dict[str, str] = t.NOMBRES_PLATAFORMA,
    dominios: dict[str, str] = PLATAFORMAS,
    ruta_selectores: Path = RUTA_SELECTORES,
) -> list[str]:
    """Lo que le falta a cada plataforma automática para postular sola."""
    faltas = []
    for plataforma, ajustes in plataformas.items():
        if not ajustes.automatica:
            continue
        if plataforma not in nombres:
            faltas.append(f"{plataforma}: sin nombre")
        if plataforma not in dominios.values():
            faltas.append(f"{plataforma}: sin dominio")
        if not (ruta_selectores / f"{plataforma}.json").is_file():
            faltas.append(f"{plataforma}: sin selectores")
    return faltas


def test_las_plataformas_automaticas_de_config_estan_completas():
    assert incompletas(cargar_configuracion().asistente.plataformas) == []


def test_elempleo_postula_sola_tras_su_piloto():
    """Activada el 2026-10-18 (tarea 7.1); la autorización de datos ya nombra su cuenta."""
    asistente = cargar_configuracion().asistente
    assert asistente.plataformas["elempleo"].automatica is True
    assert "Computrabajo, Magneto y elempleo" in asistente.politica.texto
    assert asistente.politica.version == 2


def test_falta_un_nombre():
    plataformas = cargar_configuracion().asistente.plataformas
    nombres = {k: v for k, v in t.NOMBRES_PLATAFORMA.items() if k != "magneto"}
    assert incompletas(plataformas, nombres=nombres) == ["magneto: sin nombre"]


def test_falta_el_dominio():
    plataformas = cargar_configuracion().asistente.plataformas
    dominios = {k: v for k, v in PLATAFORMAS.items() if v != "computrabajo"}
    assert incompletas(plataformas, dominios=dominios) == ["computrabajo: sin dominio"]


def test_automatica_sin_selectores_cargados(tmp_path):
    plataformas = {"elempleo": AsistentePlataforma(automatica=True)}
    assert incompletas(plataformas, ruta_selectores=tmp_path) == ["elempleo: sin selectores"]
    assert incompletas(plataformas) == []  # con assets/asistente/selectores/elempleo.json


def test_sin_automatica_no_exige_nada():
    plataformas = {"inventada": AsistentePlataforma(automatica=False)}
    assert incompletas(plataformas) == []
