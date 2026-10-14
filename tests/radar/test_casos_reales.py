"""Regresión con vacantes reales publicadas entre el 2026-10-10 y el 2026-10-13.

Cada caso del fixture evalúa la vacante con las reglas (`Filtros.evaluar`) y, si la IA la acepta
con una categoría, con el guardarraíl de prácticas. Ver el encabezado del fixture.
"""

from datetime import datetime, timedelta
from pathlib import Path

import pytest
import yaml

from buscador_vacantes.comun.config import cargar_configuracion
from buscador_vacantes.comun.fechas import ZONA
from buscador_vacantes.comun.modelo import Categoria, Vacante, Veredicto
from buscador_vacantes.radar.filtros import Filtros

FIXTURE = Path(__file__).parent / "fixtures" / "casos_reales_2026-10.yaml"
AHORA = datetime(2026, 10, 13, 12, 0, tzinfo=ZONA)
CASOS = yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def config():
    return cargar_configuracion()


@pytest.fixture(scope="module")
def filtros(config):
    return Filtros(config.filtros)


def crear_vacante(caso: dict) -> Vacante:
    return Vacante(
        fuente=caso["fuente"],
        id_fuente="1",
        titulo=caso["titulo"],
        empresa=caso["empresa"],
        url="https://x/1",
        keyword="kw",
        ubicacion=caso.get("ubicacion"),
        modalidad=caso.get("modalidad"),
        descripcion=caso.get("descripcion"),
        publicada=AHORA - timedelta(days=1),
    )


def test_el_fixture_trae_unos_treinta_casos():
    assert 25 <= len(CASOS) <= 50
    assert len({c["caso"] for c in CASOS}) == len(CASOS)


@pytest.mark.parametrize("caso", CASOS, ids=[c["caso"] for c in CASOS])
def test_caso_real(config, filtros, caso):
    vacante = crear_vacante(caso)
    esperado = caso["esperado"]
    detalle = config.fuentes[caso["fuente"]].detalle
    permite_detalle = bool(detalle and detalle.activo)  # LinkedIn pide el detalle de la oferta
    evaluacion = filtros.evaluar(vacante, AHORA, permite_detalle=permite_detalle)
    assert evaluacion.veredicto == Veredicto(esperado["veredicto"]), evaluacion
    if "motivo" in esperado:
        assert evaluacion.motivo == esperado["motivo"], evaluacion
    if "categoria" in esperado:
        assert evaluacion.categoria == Categoria(esperado["categoria"]), evaluacion
    if "exige_modalidad" in esperado:
        assert evaluacion.exige_modalidad == esperado["exige_modalidad"], evaluacion

    # Categoría con la que se publicaría, después del guardarraíl de prácticas
    ia = caso.get("ia")
    if ia:
        vacante.categoria = Categoria(ia["categoria"])
        final = ia["final"]
    elif "final" in caso:
        vacante.categoria = evaluacion.categoria
        final = caso["final"]
    else:
        return
    correccion = filtros.guardarrail_practicas(vacante)
    if correccion is None:
        publicada = vacante.categoria.value
    else:
        publicada = "rechazar" if correccion.rechaza else correccion.nueva.value
    assert publicada == final, correccion


CON_DETALLE = [c for c in CASOS if "con_detalle" in c]


def test_hay_casos_con_detalle():
    assert {c["titulo"] for c in CON_DETALLE} >= {
        "Analista Desarrollo Web Proyecto 6 Meses",
        "Software Engineer Intern",
        "Programador Junior- Data Engineering",
    }


@pytest.mark.parametrize("caso", CON_DETALLE, ids=[c["caso"] for c in CON_DETALLE])
def test_caso_real_tras_leer_el_detalle(filtros, caso):
    """La oferta pendiente se evalúa de nuevo con la descripción que trae su detalle."""
    vacante = crear_vacante(caso)
    detalle = caso["con_detalle"]
    vacante.descripcion = detalle["descripcion"].strip()
    esperado = detalle["esperado"]
    evaluacion = filtros.evaluar(vacante, AHORA, permite_detalle=True)
    assert evaluacion.veredicto == Veredicto(esperado["veredicto"]), evaluacion
    assert evaluacion.motivo == esperado["motivo"], evaluacion
    assert evaluacion.exige_modalidad == esperado.get("exige_modalidad"), evaluacion
