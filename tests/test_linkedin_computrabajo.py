from datetime import datetime, timedelta
from pathlib import Path

import httpx
import pytest

from buscador_vacantes.config import cargar_configuracion
from buscador_vacantes.estado import Estado
from buscador_vacantes.fechas import ZONA
from buscador_vacantes.fuentes.base import CambioHTML
from buscador_vacantes.fuentes.computrabajo import Computrabajo, slug
from buscador_vacantes.fuentes.linkedin import URL_BUSQUEDA, LinkedIn

FIXTURES = Path(__file__).parent / "fixtures"
AHORA = datetime(2026, 10, 3, 22, 0, tzinfo=ZONA)


@pytest.fixture
def entorno():
    config = cargar_configuracion()
    estado = Estado.abrir(":memory:")
    yield config, estado
    estado.cerrar()


def crear(clase, entorno):
    config, estado = entorno
    return clase(config.fuentes[clase.nombre], config.red, estado)


def respuesta(nombre, url="https://x"):
    texto = (FIXTURES / nombre).read_text(encoding="utf-8")
    return httpx.Response(200, text=texto, request=httpx.Request("GET", url))


# --- LinkedIn --------------------------------------------------------------------------------


def test_linkedin_peticion_con_filtro_de_nivel(entorno):
    peticion = crear(LinkedIn, entorno).construir_peticion("practicante sistemas")
    assert peticion.url == URL_BUSQUEDA
    assert peticion.params == {
        "keywords": "practicante sistemas", "location": "Colombia", "f_E": "1,2",
        "f_TPR": "r86400", "start": 0,
    }  # fmt: skip


def test_linkedin_parser(entorno):
    vacantes = crear(LinkedIn, entorno).parsear(respuesta("linkedin_busqueda.html"), "kw", AHORA)
    assert len(vacantes) == 10
    primera = vacantes[0]
    assert primera.id_fuente == "4438187947"
    assert primera.titulo == "Technical Consultant Trainee"
    assert primera.empresa == "Thales"
    assert primera.ubicacion == "Colombia"
    assert primera.url == "https://co.linkedin.com/jobs/view/4438187947"
    assert primera.publicada == AHORA - timedelta(hours=9)  # "Hace 9 horas"
    assert primera.salario is None and primera.modalidad is None
    assert all(v.id_fuente.isdigit() and v.titulo and v.url for v in vacantes)
    assert len({v.id_fuente for v in vacantes}) == 10


def test_linkedin_sin_resultados(entorno):
    vacia = httpx.Response(200, text="", request=httpx.Request("GET", "https://x"))
    assert crear(LinkedIn, entorno).parsear(vacia, "kw", AHORA) == []


def test_linkedin_html_distinto(entorno):
    cuerpo = "<html><body><div class='authwall'>Inicia sesión</div></body></html>"
    otra = httpx.Response(200, text=cuerpo, request=httpx.Request("GET", "https://x"))
    with pytest.raises(CambioHTML):
        crear(LinkedIn, entorno).parsear(otra, "kw", AHORA)


# --- Computrabajo ----------------------------------------------------------------------------


def test_slug():
    assert slug("practicante TI") == "practicante-ti"
    assert slug("desarrollador .NET junior") == "desarrollador-net-junior"
    assert slug("técnico de sistemas") == "tecnico-de-sistemas"


def test_computrabajo_peticion(entorno):
    peticion = crear(Computrabajo, entorno).construir_peticion("aprendiz SENA")
    assert peticion.url == "https://co.computrabajo.com/trabajo-de-aprendiz-sena"
    assert peticion.params == {"pubdate": 3}


def test_computrabajo_peticion_pagina_siguiente(entorno):
    peticion = crear(Computrabajo, entorno).construir_peticion("aprendiz SENA", 3)
    assert peticion.url == "https://co.computrabajo.com/trabajo-de-aprendiz-sena"
    assert peticion.params == {"pubdate": 3, "p": 3}


def test_computrabajo_parser(entorno):
    vacantes = crear(Computrabajo, entorno).parsear(
        respuesta("computrabajo_busqueda.html"), "practicante sistemas", AHORA
    )
    assert len(vacantes) == 20
    primera = vacantes[0]
    assert primera.id_fuente == "D6ED3949AE881FB361373E686DCF3405"
    assert primera.titulo == "Practicante de Sistemas y Mantenimiento TI"
    assert primera.empresa == "TWW SAS"
    assert primera.ubicacion == "Bogotá, D.C., Bogotá, D.C."
    assert primera.salario == "$ 1.750.905 (Mensual)"
    assert primera.url == (
        "https://co.computrabajo.com/ofertas-de-trabajo/oferta-de-trabajo-de-practicante-de-"
        "sistemas-y-mantenimiento-ti-en-bogota-dc-D6ED3949AE881FB361373E686DCF3405"
    )
    assert primera.publicada.date() == (AHORA - timedelta(days=1)).date()  # "Ayer"
    # La calificación de la empresa no se mezcla con el nombre
    assert vacantes[1].empresa == "AGENCIA DE EMPLEO COMFAMA"
    assert vacantes[1].ubicacion == "Medellín, Antioquia"
    # Ninguna ubicación es una calificación tipo "4,7"
    assert not any(v.ubicacion and v.ubicacion[0].isdigit() for v in vacantes)
    assert not any(v.empresa[:1].isdigit() for v in vacantes)
    assert vacantes[2].empresa == "Importante empresa del sector"
    remotas = [v for v in vacantes if v.modalidad == "Remoto"]
    assert len(remotas) == 2
    assert all(len(v.id_fuente) == 32 for v in vacantes)
    sin_salario = [v for v in vacantes if v.salario is None]
    assert sin_salario  # algunos no publican salario


def test_computrabajo_sin_resultados(entorno):
    vacia = respuesta("computrabajo_vacio.html")
    assert crear(Computrabajo, entorno).parsear(vacia, "kw", AHORA) == []


def test_computrabajo_html_distinto(entorno):
    otra = httpx.Response(200, text="<html><body><main>Nuevo diseño</main></body></html>",
                          request=httpx.Request("GET", "https://x"))  # fmt: skip
    with pytest.raises(CambioHTML):
        crear(Computrabajo, entorno).parsear(otra, "kw", AHORA)
