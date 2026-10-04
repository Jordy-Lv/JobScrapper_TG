import os

import httpx
import pytest
import respx

from salud import Salud

URL = "https://hc-ping.com/uuid-de-prueba"


@pytest.fixture
def salud():
    s = Salud(URL)
    yield s
    s.cerrar()


@respx.mock
def test_start_exito_y_fallo(salud):
    inicio = respx.post(f"{URL}/start").mock(return_value=httpx.Response(200))
    exito = respx.post(URL).mock(return_value=httpx.Response(200))
    fallo = respx.post(f"{URL}/fail").mock(return_value=httpx.Response(200))
    assert salud.inicio() and salud.exito("3 enviadas") and salud.fallo("Traceback")
    assert inicio.called and fallo.called
    assert exito.calls[0].request.content == b"3 enviadas"


@respx.mock
def test_monitoreo_caido_no_rompe(salud, caplog):
    respx.post(URL).mock(side_effect=httpx.ConnectTimeout("sin respuesta"))
    respx.post(f"{URL}/start").mock(return_value=httpx.Response(503))
    assert salud.exito() is False
    assert salud.inicio() is False
    assert "Ping de salud" in caplog.text


@respx.mock
def test_sin_url_o_desactivado_no_hace_requests():
    ruta = respx.post(URL)
    assert Salud(None).exito() is False
    assert Salud(URL, activo=False).inicio() is False
    assert not ruta.called


@pytest.mark.skipif(
    not (os.environ.get("PRUEBA_REAL") and os.environ.get("HEALTHCHECK_URL")),
    reason="prueba real: requiere PRUEBA_REAL=1 y HEALTHCHECK_URL",
)
def test_ping_real():
    salud = Salud(os.environ["HEALTHCHECK_URL"])
    assert salud.inicio() and salud.exito("prueba manual del buscador")
    salud.cerrar()
