import json
import ssl
from datetime import datetime
from pathlib import Path

import httpx
import pytest

from buscador_vacantes.config import cargar_configuracion
from buscador_vacantes.estado import Estado
from buscador_vacantes.fechas import ZONA
from buscador_vacantes.fuentes.base import CambioHTML
from buscador_vacantes.fuentes.spe import (
    CERTIFICADO_INTERMEDIO,
    URL_BUSQUEDA,
    ServicioPublicoEmpleo,
    exige_login,
)

# Respuesta real del 2026-10-04 recortada. Variantes sintéticas (códigos 99999990xx): sin
# enlace, con teletrabajo, solo con enlace universitario público y vencida.
FIXTURE = Path(__file__).parent / "fixtures" / "spe_practicas.json"
AHORA = datetime(2026, 10, 4, 12, 0, tzinfo=ZONA)


@pytest.fixture
def config():
    return cargar_configuracion()


@pytest.fixture
def fuente(config):
    estado = Estado.abrir(":memory:")
    f = ServicioPublicoEmpleo(config.fuentes["spe"], config.red, estado)
    yield f
    f.cerrar()
    estado.cerrar()


def parsear(fuente, datos=None):
    datos = datos if datos is not None else json.loads(FIXTURE.read_text(encoding="utf-8"))
    return fuente.parsear(httpx.Response(200, json=datos), "plazas de práctica", AHORA)


def por_clave(vacantes):
    return {v.clave: v for v in vacantes}


def test_peticion_pide_plazas_de_practica_por_pagina(fuente):
    peticion = fuente.construir_peticion("cualquier palabra", 2)
    assert peticion.url == URL_BUSQUEDA
    assert peticion.params == {"page": 2, "PLAZA_PRACTICA": 1}


def test_copias_se_identifican_con_su_portal_de_origen(fuente):
    vacantes = por_clave(parsear(fuente))
    elempleo = vacantes["elempleo:1886772064"]
    assert elempleo.titulo == "Practicante para Sistemas de Información."
    assert elempleo.url.startswith("https://www.elempleo.com/co/ofertas-trabajo/Practicante-para")
    assert elempleo.empresa == ""
    assert elempleo.ubicacion == "Medellín, Antioquia"
    assert elempleo.salario == "$1.000.001 - $1.500.000"
    assert elempleo.modalidad is None
    assert elempleo.publicada.date().isoformat() == "2026-09-24"
    assert elempleo.descripcion.startswith("Publicada por ")
    magneto = vacantes["magneto:936991"]
    assert magneto.url == (
        "https://www.magneto365.com/co/empleos/operador-aeropuerto-licencia-c2-smr-936991"
    )  # sin parámetros utm
    assert magneto.ubicacion == "Colombia"


def test_prefiere_el_portal_ya_consultado(fuente):
    # La plaza trae enlace de la UAO y de elempleo: se usa el de elempleo
    vacante = por_clave(parsear(fuente))["elempleo:1886772522"]
    assert "elempleo.com" in vacante.url


def test_bolsa_universitaria_publica_queda_como_spe(fuente):
    vacante = por_clave(parsear(fuente))["spe:9999999003"]
    assert "empleabilidad.uao.edu.co" in vacante.url
    assert vacante.fuente == "spe"


def test_descartes(fuente):
    claves = set(por_clave(parsear(fuente)))
    assert "spe:34299" not in claves  # Uninorte en Symplicity: exige login
    assert not [c for c in claves if "2026-09-CAL-809" in c]  # Coally: login y vencida
    assert not [c for c in claves if "9999999001" in c]  # sin enlace
    assert not [c for c in claves if "9999999004" in c]  # vencida
    assert len(claves) == 8


def test_campos_normalizados(fuente):
    vacantes = por_clave(parsear(fuente))
    assert vacantes["magneto:1080370"].ubicacion == "Antioquia"  # municipio "DEPARTAMENTO …"
    assert vacantes["elempleo:1886772514"].ubicacion == "Bogotá, D.C."
    assert vacantes["elempleo:1886772514"].salario is None  # "A Convenir"
    assert vacantes["magneto:9999999002"].modalidad == "Remoto"  # TELETRABAJO = 1
    assert all(not v.titulo.startswith("PL-") for v in vacantes.values())


def test_exige_login():
    dominios = ("symplicity.com", "coallytalent.com")
    assert exige_login("https://uninorte-csm.symplicity.com/students/app/jobs/1", dominios)
    assert exige_login("https://www.coallytalent.com/univalle/auth/login", dominios)
    assert exige_login("https://bolsa.ejemplo.edu.co/login?next=/oferta/1", dominios)
    assert not exige_login("https://empleabilidad.uao.edu.co/uao/Practicante-1886772522", dominios)


def test_pagina_completa_cuenta_filas_recibidas(fuente):
    datos = json.loads(FIXTURE.read_text(encoding="utf-8"))
    vacantes = parsear(fuente, datos)
    assert len(vacantes) < len(datos["resultados"])
    fuente.tamano_pagina = len(datos["resultados"])
    assert fuente.pagina_completa(vacantes)  # se descartaron filas, pero la página venía llena


def test_respuesta_sin_resultados_es_cambio_de_estructura(fuente):
    with pytest.raises(CambioHTML):
        parsear(fuente, {"error": "Invalid column name 'x'."})


def test_tls_verifica_con_el_intermedio_incluido(fuente):
    assert CERTIFICADO_INTERMEDIO.exists()
    contexto = fuente.verificacion_tls()
    assert isinstance(contexto, ssl.SSLContext)
    assert contexto.verify_mode == ssl.CERT_REQUIRED
    sujetos = [dict(x[0] for x in c["subject"]) for c in contexto.get_ca_certs()]
    assert any(s.get("commonName") == "GeoTrust TLS RSA CA G1" for s in sujetos)
