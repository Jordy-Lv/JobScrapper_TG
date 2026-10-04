import json
from datetime import datetime
from pathlib import Path

import httpx
import pytest
import respx

from buscador_vacantes.config import cargar_configuracion
from buscador_vacantes.estado import Estado
from buscador_vacantes.fechas import ZONA
from buscador_vacantes.fuentes.base import TipoError
from buscador_vacantes.fuentes.getonboard import URL_BUSQUEDA, GetOnBoard
from buscador_vacantes.rotacion import Consulta

FIXTURE = Path(__file__).parent / "fixtures" / "getonboard_busqueda.json"
AHORA = datetime(2026, 10, 3, 12, 0, tzinfo=ZONA)


@pytest.fixture
def fuente():
    config = cargar_configuracion()
    estado = Estado.abrir(":memory:")
    f = GetOnBoard(config.fuentes["getonboard"], config.red, estado, dormir=lambda s: None)
    yield f
    f.cerrar()
    estado.cerrar()


def parsear(fuente, datos):
    respuesta = httpx.Response(200, json=datos)
    return fuente.parsear(respuesta, "practicante sistemas", AHORA)


def test_parser_con_fixture_real(fuente):
    vacantes = parsear(fuente, json.loads(FIXTURE.read_text(encoding="utf-8")))
    titulos = [v.titulo for v in vacantes]
    # Solo sin experiencia y junior; fuera la remota en inglés
    assert len(vacantes) == 11
    assert "Actuario Senior" not in titulos
    assert "Junior Client Success Manager" not in titulos
    assert "Ingeniero Trainee Industrial" in titulos  # en inglés pero presencial

    por_titulo = {v.titulo: v for v in vacantes}
    practicante = por_titulo["Practicante Agentes IA"]
    assert practicante.fuente == "getonboard"
    assert practicante.empresa == "AgendaPro"
    assert practicante.ubicacion == "Chile"
    assert practicante.modalidad == "Presencial"
    assert practicante.salario is None
    assert practicante.url.startswith("https://www.getonbrd.com/jobs/")
    assert practicante.id_fuente
    assert practicante.keyword == "practicante sistemas"
    assert practicante.publicada.tzinfo is not None
    assert practicante.descripcion and "<" not in practicante.descripcion

    assert por_titulo["Ejecutivo de Operaciones"].salario == "USD 650 - 700 mensual"
    assert por_titulo["Ejecutivo de Operaciones"].ubicacion == "Remoto (solo residentes en Chile)"
    net = por_titulo["Desarrollador .NET Web Forms + SQL Server (Part Time, LATAM)"]
    assert net.ubicacion == "Remoto (cualquier país)"
    assert net.modalidad == "Remoto"
    assert por_titulo["Operador de Monitoreo"].ubicacion == "Colombia"
    assert por_titulo["Practicante área POS"].modalidad == "Híbrido"


def test_campos_faltantes_quedan_vacios(fuente):
    datos = {"data": [{
        "id": "x-1",
        "attributes": {
            "title": "Practicante TI",
            "seniority": {"data": {"attributes": {"locale_key": "no_experience"}}},
        },
        "links": {"public_url": "https://www.getonbrd.com/jobs/x-1"},
    }]}  # fmt: skip
    [vacante] = parsear(fuente, datos)
    assert vacante.empresa == ""
    assert vacante.salario is None
    assert vacante.publicada is None
    assert vacante.descripcion is None


def test_marcador_remoto_localizado(fuente):
    datos = json.loads(FIXTURE.read_text(encoding="utf-8"))
    for item in datos["data"]:
        item["attributes"]["countries"] = [
            "Remoto" if c == "Remote" else c for c in item["attributes"]["countries"]
        ]
    por_titulo = {v.titulo: v for v in parsear(fuente, datos)}
    assert por_titulo["Front-end (Angular Flutter)"].ubicacion == (
        "Remoto (solo residentes en Guatemala)"
    )


def test_respuesta_sin_data_es_cambio_de_estructura(fuente):
    with pytest.raises(Exception, match="data"):
        parsear(fuente, {"errors": ["algo"]})


@respx.mock
def test_peticion_y_ejecucion(fuente):
    ruta = respx.get(URL_BUSQUEDA).mock(
        return_value=httpx.Response(200, json=json.loads(FIXTURE.read_text(encoding="utf-8")))
    )
    resultado = fuente.ejecutar([Consulta("junior TI", "nucleo")])
    assert ruta.called
    params = ruta.calls[0].request.url.params
    assert params["query"] == "junior TI"
    assert json.loads(params["expand"]) == ["company", "seniority"]
    assert resultado.intentos[0].items == 11
    assert resultado.intentos[0].tipo_error is None


@respx.mock
def test_json_invalido_es_cambio_html(fuente):
    respx.get(URL_BUSQUEDA).mock(
        return_value=httpx.Response(200, text="<html>mantenimiento</html>")
    )
    resultado = fuente.ejecutar([Consulta("junior TI", "nucleo")])
    assert resultado.intentos[0].tipo_error == TipoError.CAMBIO_HTML
