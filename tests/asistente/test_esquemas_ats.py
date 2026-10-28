import asyncio
import json
from pathlib import Path

import httpx
import pytest
import respx

from buscador_vacantes.asistente.api import Campo
from buscador_vacantes.asistente.detalle import Ritmo
from buscador_vacantes.asistente.esquemas_ats import (
    LectorEsquemas,
    a_campos,
    familia_con_lector,
    traducir_ashby,
    traducir_greenhouse,
    traducir_lever,
    traducir_typeform,
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "ats"


def cargar(nombre: str):
    texto = (FIXTURES / nombre).read_text(encoding="utf-8")
    return json.loads(texto) if nombre.endswith(".json") else texto


def por_nombre(preguntas):
    return {p.nombre: p for p in preguntas}


# --- Greenhouse -------------------------------------------------------------------------------


def test_greenhouse_traduce_texto_tipo_opciones_obligatoriedad_y_clave():
    preguntas = por_nombre(traducir_greenhouse(cargar("greenhouse_trabajo.json")))

    ingles = preguntas["question_9001"]
    assert ingles.texto == "What is your English level?"
    assert ingles.tipo == "opciones"
    assert ingles.opciones == ["A1", "A2", "B1", "B2", "C1"]
    assert ingles.obligatoria is True

    asignado = preguntas["question_9002"]
    assert asignado.opciones == ["Yes", "No"]

    salario = preguntas["question_9003"]
    assert (salario.tipo, salario.obligatoria) == ("texto", True)
    assert salario.ayuda == "Include the currency"  # sin las etiquetas HTML

    larga = preguntas["question_9005"]
    assert (larga.tipo, larga.obligatoria) == ("texto", False)

    varias = preguntas["question_9006"]
    assert varias.tipo == "opciones"
    assert varias.opciones == ["Python", "SQL", "Docker"]


def test_greenhouse_reconoce_correo_telefono_y_archivos():
    preguntas = por_nombre(traducir_greenhouse(cargar("greenhouse_trabajo.json")))
    assert preguntas["email"].tipo == "correo"
    assert preguntas["phone"].tipo == "telefono"
    assert preguntas["phone"].obligatoria is False
    assert preguntas["resume"].tipo == "archivo"
    assert preguntas["question_9004"].tipo == "archivo"  # el certificado de notas obligatorio
    assert preguntas["question_9004"].obligatoria is True


def test_greenhouse_trae_la_ubicacion_e_ignora_ocultos_demograficos_y_texto_del_cv():
    preguntas = por_nombre(traducir_greenhouse(cargar("greenhouse_trabajo.json")))
    assert preguntas["job_application_location"].texto == "Location (City)"
    assert "question_9007" not in preguntas  # input_hidden
    assert "gender" not in preguntas  # demográficas y EEOC no se responden
    assert "veteran_status" not in preguntas
    assert "resume_text" not in preguntas  # el CV va por el archivo


def test_greenhouse_sin_preguntas_devuelve_lista_vacia():
    assert traducir_greenhouse({}) == []
    assert traducir_greenhouse({"questions": None}) == []


# --- Ashby ------------------------------------------------------------------------------------


def test_ashby_usa_el_path_como_clave_y_traduce_los_tipos():
    preguntas = por_nombre(traducir_ashby(cargar("ashby_publicacion.json")))

    assert preguntas["_systemfield_name"].tipo == "texto"
    assert preguntas["_systemfield_email"].tipo == "correo"
    assert preguntas["_systemfield_phone"].tipo == "telefono"
    assert preguntas["_systemfield_phone"].obligatoria is False
    assert preguntas["_systemfield_resume"].tipo == "archivo"
    assert preguntas["_systemfield_location"].tipo == "texto"

    anios = preguntas["5f4d3c2b-0000-4000-8000-0000000000a1"]
    assert (anios.tipo, anios.obligatoria) == ("numero", True)
    assert anios.ayuda == "Number of full years"

    visa = preguntas["5f4d3c2b-0000-4000-8000-0000000000a2"]
    assert visa.tipo == "opciones"
    assert visa.opciones == ["Yes", "No"]

    ingles = preguntas["5f4d3c2b-0000-4000-8000-0000000000a3"]
    assert ingles.opciones == ["Intermediate", "Advanced"]

    assert preguntas["5f4d3c2b-0000-4000-8000-0000000000a4"].opciones == ["Postgres", "Redis"]
    assert preguntas["5f4d3c2b-0000-4000-8000-0000000000a5"].tipo == "texto"
    assert preguntas["5f4d3c2b-0000-4000-8000-0000000000a6"].tipo == "fecha"


def test_ashby_sin_formulario_devuelve_lista_vacia():
    assert traducir_ashby({"data": {"jobPosting": None}}) == []
    assert traducir_ashby({}) == []


# --- Typeform ---------------------------------------------------------------------------------


def test_typeform_traduce_las_preguntas_con_el_id_del_campo_como_clave():
    preguntas = traducir_typeform(cargar("typeform_pagina.html"))
    por_clave = por_nombre(preguntas)

    assert len(preguntas) == 10  # 11 campos menos el enunciado
    assert por_clave["f001"].texto == "¿Cuál es tu nombre completo?"
    assert por_clave["f002"].tipo == "correo"
    assert por_clave["f003"].tipo == "telefono"
    assert por_clave["f003"].obligatoria is False
    assert por_clave["f005"].opciones == ["Menos de 1", "1 a 2", "Más de 2"]
    assert por_clave["f006"].opciones == ["Git", "Docker"]
    assert por_clave["f007"].tipo == "texto"
    assert por_clave["f008"].opciones == ["Sí", "No"]
    assert por_clave["f009"].tipo == "numero"
    assert por_clave["f010"].tipo == "fecha"
    assert por_clave["f011"].tipo == "archivo"


def test_typeform_ignora_enunciados_y_pantallas_de_bienvenida_y_gracias_y_sigue_el_orden():
    preguntas = traducir_typeform(cargar("typeform_pagina.html"))
    textos = [p.texto for p in preguntas]
    assert "A continuación, unas preguntas de experiencia" not in textos
    assert "Bienvenido" not in textos
    assert "¡Gracias por postularte!" not in textos
    assert [p.nombre for p in preguntas] == [
        "f001", "f002", "f003", "f005", "f006", "f007", "f008", "f009", "f010", "f011",
    ]  # fmt: skip


def test_typeform_sin_definicion_devuelve_lista_vacia():
    assert traducir_typeform("<html><body>nada</body></html>") == []
    assert traducir_typeform("<script>window.rendererData = {rota</script>") == []


# --- Lever ------------------------------------------------------------------------------------


def test_lever_traduce_texto_tipo_opciones_obligatoriedad_y_clave():
    preguntas = por_nombre(traducir_lever(cargar("lever_apply.html")))

    assert preguntas["resume"].tipo == "archivo"
    assert preguntas["resume"].texto == "Resume/CV"  # sin la marca de obligatorio
    assert preguntas["resume"].obligatoria is True

    assert preguntas["name"].texto == "Full name"
    assert preguntas["email"].tipo == "correo"
    assert preguntas["phone"].tipo == "telefono"
    assert preguntas["location"].tipo == "texto"
    assert preguntas["urls[LinkedIn]"].obligatoria is False

    previa = preguntas["cards[92a51f92-d683-4f7b-be57-e25376f60abe][field0]"]
    assert previa.texto == "Have you ever been previously employed by Acme?"
    assert previa.tipo == "opciones"
    assert previa.opciones == ["No", "Yes - Intern", "Yes - Full Time Employment"]
    assert previa.obligatoria is True

    larga = preguntas["cards[7c1d2e3f-0000-4000-8000-000000000002][field1]"]
    assert (larga.tipo, larga.obligatoria) == ("texto", True)

    ingles = preguntas["cards[7c1d2e3f-0000-4000-8000-000000000003][field2]"]
    assert ingles.opciones == ["B1", "B2", "C1"]  # sin «Select...»


def test_lever_ignora_encuestas_voluntarias_pronombres_y_campos_ocultos():
    nombres = {p.nombre for p in traducir_lever(cargar("lever_apply.html"))}
    assert not any(n.startswith("surveysResponses") for n in nombres)
    assert "pronouns" not in nombres
    assert not nombres & {"accountId", "selectedLocation"}


def test_lever_sin_formulario_devuelve_lista_vacia():
    assert traducir_lever("<html><body>nada</body></html>") == []


@respx.mock
def test_lee_lever_de_la_pagina_de_postulacion():
    ruta = respx.get(
        "https://jobs.lever.co/prueba/2a55d6c9-c564-443a-be3e-a3851db5a93b/apply"
    ).mock(return_value=httpx.Response(200, text=cargar("lever_apply.html")))
    for url in (
        "https://jobs.lever.co/prueba/2a55d6c9-c564-443a-be3e-a3851db5a93b",
        "https://jobs.lever.co/prueba/2a55d6c9-c564-443a-be3e-a3851db5a93b/apply",
    ):
        preguntas = asyncio.run(lector().leer("lever", url))
        assert preguntas is not None
        assert "name" in {p.nombre for p in preguntas}
    assert ruta.call_count == 2


# --- salida para guardar ------------------------------------------------------------------------


def test_a_campos_produce_dicts_que_valida_el_modelo_campo():
    campos = a_campos(traducir_greenhouse(cargar("greenhouse_trabajo.json")))
    assert campos
    for crudo in campos:
        Campo.model_validate(crudo)
    ingles = next(c for c in campos if c["nombre"] == "question_9001")
    assert ingles["opciones"] == ["A1", "A2", "B1", "B2", "C1"]


# --- cliente ----------------------------------------------------------------------------------


def lector(*, intervalo=8.0, dormidas=None):
    async def dormir(segundos):
        if dormidas is not None:
            dormidas.append(segundos)

    return LectorEsquemas(
        httpx.AsyncClient(follow_redirects=True),
        Ritmo(intervalo, reloj=lambda: 0.0, dormir=dormir),
    )


def test_familias_con_lector():
    assert familia_con_lector("greenhouse")
    assert familia_con_lector("ashby")
    assert familia_con_lector("lever")
    assert familia_con_lector("typeform")
    assert not familia_con_lector("workday")
    assert not familia_con_lector("propio")


@respx.mock
def test_lee_greenhouse_por_la_api_de_tableros():
    ruta = respx.get("https://boards-api.greenhouse.io/v1/boards/prueba/jobs/4100100").mock(
        return_value=httpx.Response(200, json=cargar("greenhouse_trabajo.json"))
    )
    preguntas = asyncio.run(
        lector().leer("greenhouse", "https://job-boards.greenhouse.io/prueba/jobs/4100100")
    )
    assert ruta.calls.last.request.url.params["questions"] == "true"
    assert preguntas is not None
    assert {p.nombre for p in preguntas} >= {"question_9001", "email"}


@respx.mock
def test_greenhouse_embebido_en_el_sitio_de_la_empresa_se_lee_por_su_token():
    ruta = respx.get("https://boards-api.greenhouse.io/v1/boards/prueba/jobs/4100100").mock(
        return_value=httpx.Response(200, json=cargar("greenhouse_trabajo.json"))
    )
    url = "https://boards.greenhouse.io/embed/job_app?for=prueba&token=4100100"
    assert asyncio.run(lector().leer("greenhouse", url)) is not None
    assert ruta.called


@respx.mock
def test_api_caida_deja_la_postulacion_sin_esquema():
    respx.get("https://boards-api.greenhouse.io/v1/boards/prueba/jobs/4100100").mock(
        return_value=httpx.Response(503)
    )
    url = "https://job-boards.greenhouse.io/prueba/jobs/4100100"
    assert asyncio.run(lector().leer("greenhouse", url)) is None


@respx.mock
def test_error_de_red_y_json_roto_dejan_la_postulacion_sin_esquema():
    ruta = respx.get("https://boards-api.greenhouse.io/v1/boards/prueba/jobs/4100100")
    url = "https://job-boards.greenhouse.io/prueba/jobs/4100100"
    ruta.mock(side_effect=httpx.ConnectTimeout("lenta"))
    assert asyncio.run(lector().leer("greenhouse", url)) is None
    ruta.mock(return_value=httpx.Response(200, text="<html>no es json</html>"))
    assert asyncio.run(lector().leer("greenhouse", url)) is None


@respx.mock
def test_lee_ashby_por_la_consulta_de_la_pagina():
    ruta = respx.post("https://jobs.ashbyhq.com/api/non-user-graphql").mock(
        return_value=httpx.Response(200, json=cargar("ashby_publicacion.json"))
    )
    url = "https://jobs.ashbyhq.com/prueba/4b3b7cc7-0000-4000-8000-000000000001/application"
    preguntas = asyncio.run(lector().leer("ashby", url))
    assert preguntas is not None
    assert ruta.calls.last.request.url.params["op"] == "ApiJobPosting"
    cuerpo = json.loads(ruta.calls.last.request.content)
    assert cuerpo["variables"] == {
        "organizationHostedJobsPageName": "prueba",
        "jobPostingId": "4b3b7cc7-0000-4000-8000-000000000001",
    }
    assert "_systemfield_name" in {p.nombre for p in preguntas}


@respx.mock
def test_lee_typeform_de_la_pagina_publica():
    respx.get("https://prueba.typeform.com/to/AbC123").mock(
        return_value=httpx.Response(200, text=cargar("typeform_pagina.html"))
    )
    preguntas = asyncio.run(lector().leer("typeform", "https://prueba.typeform.com/to/AbC123"))
    assert preguntas is not None
    assert len(preguntas) == 10


@respx.mock
def test_url_que_no_es_de_una_vacante_o_familia_sin_lector_no_hace_ninguna_peticion():
    cualquiera = respx.route().mock(return_value=httpx.Response(200))
    assert (
        asyncio.run(lector().leer("greenhouse", "https://job-boards.greenhouse.io/prueba")) is None
    )
    assert asyncio.run(lector().leer("workday", "https://acme.myworkdayjobs.com/x/job/1")) is None
    assert not cualquiera.called


@respx.mock
def test_respeta_la_pausa_minima_por_dominio():
    respx.get("https://boards-api.greenhouse.io/v1/boards/prueba/jobs/1").mock(
        return_value=httpx.Response(200, json=cargar("greenhouse_trabajo.json"))
    )
    dormidas: list[float] = []
    el_lector = lector(intervalo=8.0, dormidas=dormidas)
    url = "https://job-boards.greenhouse.io/prueba/jobs/1"
    asyncio.run(el_lector.leer("greenhouse", url))
    asyncio.run(el_lector.leer("greenhouse", url))
    assert dormidas == [8.0]  # la segunda lectura al mismo dominio espera su turno


def test_un_esquema_vacio_equivale_a_ninguno():
    with respx.mock:
        respx.get("https://boards-api.greenhouse.io/v1/boards/prueba/jobs/2").mock(
            return_value=httpx.Response(200, json={"questions": []})
        )
        url = "https://job-boards.greenhouse.io/prueba/jobs/2"
        assert asyncio.run(lector().leer("greenhouse", url)) is None


@pytest.mark.parametrize("url", ["", "no es una url", "ftp://boards.greenhouse.io/a/jobs/1"])
def test_urls_invalidas_no_rompen(url):
    assert asyncio.run(lector().leer("greenhouse", url)) is None
