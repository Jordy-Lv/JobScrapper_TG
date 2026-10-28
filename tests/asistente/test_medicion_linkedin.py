import pytest

from buscador_vacantes.asistente.medicion_linkedin import PROPIO, familia_de, limpiar_destino

FAMILIAS = {
    "workday": ["myworkdayjobs.com", "myworkdaysite.com"],
    "greenhouse": ["greenhouse.io", "grnh.se"],
    "computrabajo": ["computrabajo.com"],
    "pandape": ["pandape.computrabajo.com", "pandape.com"],
}


def test_desenvuelve_el_enlace_de_seguridad_de_linkedin():
    url = (
        "https://www.linkedin.com/safety/go?url=https%3A%2F%2Fjob-boards.greenhouse.io%2Facme%2Fjobs"
        "%2F123%3Fgh_src%3Dx%26utm_source%3Dlinkedin&trk=flagship"
    )
    assert limpiar_destino(url) == "https://job-boards.greenhouse.io/acme/jobs/123?gh_src=x"


def test_desenvuelve_external_apply():
    url = "https://www.linkedin.com/jobs/view/externalApply/42?url=https%3A%2F%2Facme.com%2Fempleo&urlHash=x"
    assert limpiar_destino(url) == "https://acme.com/empleo"


def test_quita_parametros_de_rastreo_y_conserva_los_demas():
    url = "https://acme.com/oferta?id=7&trk=a&refId=b&trackingId=c&utm_campaign=d&UTM_medium=e"
    assert limpiar_destino(url) == "https://acme.com/oferta?id=7"


def test_deja_igual_mailto_y_vacio():
    assert limpiar_destino("mailto:rh@acme.com") == "mailto:rh@acme.com"
    assert limpiar_destino("") == ""


@pytest.mark.parametrize(
    ("url", "familia"),
    [
        ("https://acme.wd3.myworkdayjobs.com/es/externo/job/123", "workday"),
        ("https://job-boards.greenhouse.io/acme/jobs/9", "greenhouse"),
        ("https://grnh.se/abc123", "greenhouse"),
        ("https://co.computrabajo.com/ofertas-de-trabajo/oferta-x", "computrabajo"),
        ("https://acme.pandape.computrabajo.com/vacante/1", "pandape"),
        ("https://careers.acme.com/job/1", PROPIO),
        ("https://notgreenhouse.io/x", PROPIO),
        ("", PROPIO),
    ],
)
def test_familia_de(url, familia):
    assert familia_de(url, FAMILIAS) == familia
