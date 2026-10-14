"""Regresión con vacantes reales publicadas entre el 2026-10-10 y el 2026-10-13.

Cada caso del fixture evalúa la vacante con las reglas (`Filtros.evaluar`) y, si la IA la acepta
con una categoría, con el guardarraíl de prácticas. Ver el encabezado del fixture.
"""

from datetime import datetime, timedelta
from pathlib import Path

import pytest
import yaml

from buscador_vacantes.config import cargar_configuracion
from buscador_vacantes.fechas import ZONA
from buscador_vacantes.filtros import Filtros
from buscador_vacantes.modelo import Categoria, Vacante, Veredicto

FIXTURE = Path(__file__).parent / "fixtures" / "casos_reales_2026-10.yaml"
AHORA = datetime(2026, 10, 13, 12, 0, tzinfo=ZONA)
CASOS = yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def filtros():
    return Filtros(cargar_configuracion().filtros)


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
    assert 25 <= len(CASOS) <= 45
    assert len({c["caso"] for c in CASOS}) == len(CASOS)


@pytest.mark.parametrize("caso", CASOS, ids=[c["caso"] for c in CASOS])
def test_caso_real(filtros, caso):
    vacante = crear_vacante(caso)
    esperado = caso["esperado"]
    evaluacion = filtros.evaluar(vacante, AHORA)
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
