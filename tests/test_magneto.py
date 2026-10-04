import json
from datetime import datetime
from pathlib import Path

import httpx
import pytest

from config import cargar_configuracion
from estado import Estado
from fechas import ZONA
from filtros import Filtros, Motivo
from fuentes.base import CambioHTML
from fuentes.magneto import URL_BUSQUEDA, Magneto

FIXTURE = Path(__file__).parent / "fixtures" / "magneto_busqueda.json"
AHORA = datetime(2026, 10, 3, 22, 0, tzinfo=ZONA)


@pytest.fixture
def fuente():
    config = cargar_configuracion()
    estado = Estado.abrir(":memory:")
    f = Magneto(config.fuentes["magneto"], config.red, estado)
    yield f
    f.cerrar()
    estado.cerrar()


def parsear(fuente, datos):
    return fuente.parsear(httpx.Response(200, json=datos), "practicante sistemas", AHORA)


def test_peticion(fuente):
    peticion = fuente.construir_peticion("practicante sistemas")
    assert peticion.url == URL_BUSQUEDA
    assert peticion.params["device"] == "desktop"
    assert json.loads(peticion.params["paginator"]) == {"page": 1, "pageSize": 20}
    assert json.loads(peticion.params["order"]) == {"field": "publish_date", "order": "DESC"}
    assert json.loads(peticion.params["queries"]) == [
        {"field": "all", "term": "practicante sistemas"}
    ]


def test_parser_con_fixture_real(fuente):
    vacantes = parsear(fuente, json.loads(FIXTURE.read_text(encoding="utf-8")))
    assert len(vacantes) == 12
    primera = vacantes[0]
    assert primera.id_fuente == "1088539"
    assert primera.titulo == "Aprendiz Universitario de Procesos (Híbrido)"
    assert primera.empresa == "ASSIST CONSULTORES DE SISTEMA"
    assert primera.url == (
        "https://www.magneto365.com/co/empleos/aprendiz-universitario-de-procesos-hibrido-1088539"
    )
    assert primera.ubicacion == "Bogotá, D.C."
    assert primera.salario == "$1.750.905"
    assert primera.modalidad == "Remoto o híbrido"
    assert primera.publicada == datetime(2026, 10, 2, 15, 7, 29, 800000, tzinfo=ZONA)
    assert primera.descripcion and "<" not in primera.descripcion
    assert vacantes[3].salario is None  # a convenir


def test_varias_ciudades(fuente):
    datos = json.loads(FIXTURE.read_text(encoding="utf-8"))
    fila = dict(datos["rows"][0], cities=["Medellín", "Bello", "Itagüí", "Envigado", "Sabaneta"])
    [vacante] = parsear(fuente, {"rows": [fila]})
    assert vacante.ubicacion == "Medellín, Bello, Itagüí y 2 más"


def test_experiencia_alta_la_rechaza_el_filtro(fuente):
    vacantes = parsear(fuente, json.loads(FIXTURE.read_text(encoding="utf-8")))
    con_experiencia = vacantes[4]
    assert con_experiencia.descripcion.startswith("Experiencia requerida: 4 años.")
    evaluacion = Filtros(cargar_configuracion().filtros).evaluar(con_experiencia, AHORA)
    assert evaluacion.motivo == Motivo.SENIORITY


def test_sin_resultados_y_estructura_invalida(fuente):
    assert parsear(fuente, {"totalRows": 0, "rows": []}) == []
    with pytest.raises(CambioHTML):
        parsear(fuente, {"httpCode": 400, "message": "error"})
