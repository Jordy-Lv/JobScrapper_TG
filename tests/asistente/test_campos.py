import json

import pytest

pytest.importorskip("pypdf", reason="requiere uv sync --group asistente")

from buscador_vacantes.asistente import campos  # noqa: E402
from buscador_vacantes.asistente.campos import (  # noqa: E402
    RESERVADO,
    DatosUsuario,
    clave_cuestionario,
    es_guardable,
    nombre_fuente,
    separar_nombre,
)
from buscador_vacantes.asistente.cv_lectura import Enlace, PerfilExtraido  # noqa: E402


def datos(nombre="Ana María Pérez Gómez", cuestionario=None, enlaces=()):
    perfil = PerfilExtraido(es_cv=True, nombre=nombre, enlaces=list(enlaces))
    return DatosUsuario(perfil, cuestionario or {})


@pytest.mark.parametrize(
    ("completo", "esperado"),
    [
        ("Ana María Pérez Gómez", ("Ana María", "Pérez Gómez")),
        ("Juan Pérez Gómez", ("Juan", "Pérez Gómez")),
        ("Ana María Pérez", ("Ana María", "Pérez")),
        ("Ana Pérez", ("Ana", "Pérez")),
        ("Ana", ("Ana", None)),
        ("María de la Cruz Rojas Díaz", ("María de la Cruz", "Rojas Díaz")),
        ("Carlos Andrés De la Rosa Soto", ("Carlos Andrés", "De la Rosa Soto")),
        ("  ", (None, None)),
        (None, (None, None)),
    ],
)
def test_separar_nombre(completo, esperado):
    assert separar_nombre(completo) == esperado


def test_nombre_y_apellido_se_derivan_del_nombre_completo():
    d = datos()
    assert d.valor("nombre_pila") == "Ana María"
    assert d.valor("apellido") == "Pérez Gómez"


def test_nombre_y_apellido_dados_por_separado_mandan():
    d = datos(cuestionario={"nombre_pila": "Ana", "apellido": "Pérez"})
    assert (d.valor("nombre_pila"), d.valor("apellido")) == ("Ana", "Pérez")


def test_nombre_del_cuestionario_manda_sobre_el_del_cv():
    d = datos(nombre="A. Pérez", cuestionario={"nombre": "Ana Sofía Ruiz Mora"})
    assert (d.valor("nombre_pila"), d.valor("apellido")) == ("Ana Sofía", "Ruiz Mora")


def test_enlace_de_linkedin_aparte_del_portafolio():
    d = datos(enlaces=[
        Enlace(tipo="github", url="https://github.com/ana"),
        Enlace(tipo="LinkedIn", url="https://www.linkedin.com/in/ana"),
    ])  # fmt: skip
    assert d.valor("enlace_linkedin") == "https://www.linkedin.com/in/ana"
    assert d.valor("enlace_portafolio") == "https://github.com/ana"


def test_enlace_de_linkedin_se_reconoce_por_la_url():
    d = datos(enlaces=[Enlace(tipo="otro", url="https://co.linkedin.com/in/ana")])
    assert d.valor("enlace_linkedin") == "https://co.linkedin.com/in/ana"
    assert datos().valor("enlace_linkedin") is None


def test_pais_promedio_y_salario_usd_solo_si_el_usuario_los_dio():
    assert datos().valor("pais") is None
    assert datos().valor("promedio") is None
    assert datos().valor("salario_usd") is None
    d = datos(cuestionario={"pais": "Colombia", "promedio": "4.2", "salario_usd": "1500"})
    assert (d.valor("pais"), d.valor("promedio"), d.valor("salario_usd")) == (
        "Colombia", "4.2", "1500",
    )  # fmt: skip


def test_autorizacion_para_trabajar_es_por_pais():
    d = datos(cuestionario={"autorizacion_trabajo:colombia": "Sí"})
    assert d.valor("autorizacion_trabajo", "Colombia") == "Sí"
    assert d.valor("autorizacion_trabajo", "colombia") == "Sí"  # sin importar mayúsculas
    assert d.valor("autorizacion_trabajo", "Estados Unidos") is None
    assert d.valor("autorizacion_trabajo") is None


def test_reservado_no_se_entrega():
    d = datos(cuestionario={"pais": RESERVADO, "autorizacion_trabajo:colombia": RESERVADO})
    assert d.valor("pais") is None
    assert d.valor("autorizacion_trabajo", "Colombia") is None


def test_clave_cuestionario_y_campos_guardables():
    assert clave_cuestionario("autorizacion_trabajo", "México") == "autorizacion_trabajo:mexico"
    assert clave_cuestionario("ciudad", None) == "ciudad"
    assert clave_cuestionario("conoce", "Excel") == "conoce"
    assert es_guardable("promedio") and es_guardable("autorizacion_trabajo:colombia")
    assert not es_guardable("autorizacion_trabajo")  # sin país no hay dónde guardarlo
    assert not es_guardable("conoce") and not es_guardable(None)


def test_fuente_vacante_sale_de_la_plataforma():
    assert nombre_fuente("linkedin") == "LinkedIn"
    assert nombre_fuente("computrabajo") == "Computrabajo"
    assert nombre_fuente("otra") == "otra"
    assert nombre_fuente(None) is None


def test_catalogo_describe_los_campos_nuevos():
    for campo in ("nombre_pila", "apellido", "pais", "enlace_linkedin", "salario_usd", "promedio",
                  "fuente_vacante"):  # fmt: skip
        assert campo in campos.CAMPOS
    assert "autorizacion_trabajo" in campos.CAMPOS_PARAMETRO
    assert campos.es_campo_valido("autorizacion_trabajo", "Colombia")
    assert not campos.es_campo_valido("autorizacion_trabajo", None)


def test_nombre_apellido_y_linkedin_nunca_van_a_la_ia():
    d = datos(
        cuestionario={"nombre_pila": "Ana", "apellido": "Pérez", "pais": "Colombia",
                      "enlace_linkedin": "https://www.linkedin.com/in/ana", "promedio": "4.2"},
        enlaces=[Enlace(tipo="linkedin", url="https://www.linkedin.com/in/ana")],
    )  # fmt: skip
    para_ia = d.para_ia()
    texto = json.dumps(para_ia, ensure_ascii=False)
    for contacto in ("Ana", "Pérez", "linkedin.com"):
        assert contacto not in texto
    assert para_ia["cuestionario"] == {"pais": "Colombia", "promedio": "4.2"}
