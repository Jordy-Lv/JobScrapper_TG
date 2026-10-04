from datetime import datetime, timedelta
from pathlib import Path

import httpx
import pytest
import respx

from buscador_vacantes.config import cargar_configuracion
from buscador_vacantes.estado import Estado
from buscador_vacantes.fechas import ZONA
from buscador_vacantes.fuentes.base import CambioHTML
from buscador_vacantes.fuentes.elempleo import Elempleo
from buscador_vacantes.rotacion import Consulta

FIXTURE = Path(__file__).parent / "fixtures" / "elempleo_busqueda.html"
AHORA = datetime(2026, 10, 3, 22, 0, tzinfo=ZONA)


@pytest.fixture
def fuente():
    config = cargar_configuracion()
    estado = Estado.abrir(":memory:")
    f = Elempleo(config.fuentes["elempleo"], config.red, estado, dormir=lambda s: None)
    yield f
    f.cerrar()
    estado.cerrar()


def test_peticion_con_filtro_de_fecha(fuente):
    peticion = fuente.construir_peticion("practicante sistemas")
    assert peticion.url == (
        "https://www.elempleo.com/co/ofertas-empleo/hace-1-semana/trabajo-practicante-sistemas"
    )


def test_parser_con_fixture_real(fuente):
    respuesta = httpx.Response(200, text=FIXTURE.read_text(encoding="utf-8"))
    vacantes = fuente.parsear(respuesta, "practicante sistemas", AHORA)
    assert len(vacantes) == 10
    primera = vacantes[0]
    assert primera.id_fuente == "1886775823"
    assert primera.titulo == "Practicante de sistemas y mantenimineto - ti"
    assert primera.empresa == "TWW SAS"
    assert primera.ubicacion == "Bogotá"
    assert primera.salario == "$1,5 a $2 millones"
    assert primera.modalidad == "Presencial"
    assert primera.url == (
        "https://www.elempleo.com/co/ofertas-trabajo/"
        "practicante-de-sistemas-y-mantenimineto-ti-1886775823"
    )
    assert primera.publicada.date() == (AHORA - timedelta(days=1)).date()
    assert primera.descripcion and "etapa práctica" in primera.descripcion
    assert {v.modalidad for v in vacantes} == {"Presencial", "Híbrido"}
    assert all(v.id_fuente.isdigit() for v in vacantes)


def test_estructura_ausente(fuente):
    with pytest.raises(CambioHTML):
        fuente.parsear(httpx.Response(200, text="<html><body>otra cosa</body></html>"), "k", AHORA)


@respx.mock
def test_404_es_sin_resultados(fuente):
    respx.get(url__startswith="https://www.elempleo.com/").mock(
        return_value=httpx.Response(404, text=FIXTURE.read_text(encoding="utf-8"))
    )
    resultado = fuente.ejecutar([Consulta("zzqxw", "cola_larga")])
    assert resultado.vacantes == []
    assert resultado.intentos[0].tipo_error is None
    assert resultado.intentos[0].status == 404
    assert resultado.cooldown_hasta is None
