import asyncio
import io
import json
from datetime import UTC, datetime

import httpx
import pytest
import respx

pytest.importorskip("fpdf", reason="requiere uv sync --group asistente")
from pypdf import PdfReader  # noqa: E402

from buscador_vacantes.asistente.afinidad import Requisitos  # noqa: E402
from buscador_vacantes.asistente.campos import DatosUsuario  # noqa: E402
from buscador_vacantes.asistente.cv_adaptado import (  # noqa: E402
    AdaptacionLeve,
    Reemplazo,
    adaptar,
    carta_basica,
    cv_base,
    redactar_carta,
    validar_adaptacion,
)
from buscador_vacantes.asistente.cv_lectura import (  # noqa: E402
    Certificacion,
    Experiencia,
    Formacion,
    Idioma,
    PerfilExtraido,
    Proyecto,
)
from buscador_vacantes.asistente.cv_pdf import Contacto, generar_pdf, nombre_archivo  # noqa: E402
from buscador_vacantes.asistente.datos import BaseAsistente  # noqa: E402
from buscador_vacantes.asistente.gemini import ClienteGemini  # noqa: E402
from buscador_vacantes.config import cargar_configuracion  # noqa: E402

URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"

PERFIL = PerfilExtraido(
    es_cv=True,
    nombre="Ana María Pérez Gómez",
    ciudad="Bogotá",
    resumen="Estudiante de Ingeniería de Sistemas con interés en desarrollo de software.",
    formacion=[Formacion(institucion="Universidad Nacional", programa="Ingeniería de Sistemas",
                         semestre="6", estado="En curso", inicio="2022")],
    experiencia=[Experiencia(empresa="Universidad Nacional", cargo="Monitora académica",
                             inicio="2024", fin="2025",
                             logros=["Apoyé a 40 estudiantes en programación con Python."])],
    proyectos=[Proyecto(nombre="API de inventario", descripcion="API REST para una tienda.",
                        tecnologias=["Django", "PostgreSQL"])],
    habilidades_tecnicas=["Java", "Excel", "JS", "Python", "SQL"],
    habilidades_blandas=["Trabajo en equipo"],
    idiomas=[Idioma(idioma="Inglés", nivel="B1")],
    certificaciones=[Certificacion(nombre="Python Essentials", entidad="Cisco", anio="2024")],
)  # fmt: skip
CONTACTO = Contacto("Ana María Pérez Gómez", "Bogotá", "ana.perez@gmail.com", "310 555 1234")


def test_reordena_por_relevancia_sin_tocar_lo_demas():
    salida = AdaptacionLeve(
        resumen="Estudiante de Ingeniería de Sistemas orientada a desarrollo backend con Python.",
        habilidades_primero=["Python", "SQL"],
    )
    cv = validar_adaptacion(salida, PERFIL)
    assert cv.habilidades[:2] == ["Python", "SQL"]
    assert sorted(cv.habilidades) == sorted(PERFIL.habilidades_tecnicas)
    assert cv.perfil.experiencia == PERFIL.experiencia
    assert cv.perfil.proyectos == PERFIL.proyectos
    assert cv.descartes == [] and cv.adaptado


def test_tecnologia_inventada_en_el_resumen_usa_el_base():
    salida = AdaptacionLeve(resumen="Desarrolladora con experiencia en Docker y Kubernetes.")
    cv = validar_adaptacion(salida, PERFIL)
    assert cv.resumen == PERFIL.resumen
    assert any("Docker" in d for d in cv.descartes)


def test_habilidad_ajena_no_entra():
    cv = validar_adaptacion(AdaptacionLeve(habilidades_primero=["Docker", "Python"]), PERFIL)
    assert "Docker" not in cv.habilidades
    assert cv.habilidades[0] == "Python"


def test_reemplazos_solo_sinonimos_y_maximo_tres():
    salida = AdaptacionLeve(
        reemplazos=[
            Reemplazo(original="JS", nuevo="JavaScript"),
            Reemplazo(original="Java", nuevo="JavaScript"),  # no es sinónimo
            Reemplazo(original="Python", nuevo="Python3"),
            Reemplazo(original="SQL", nuevo="T-SQL"),
            Reemplazo(original="Excel", nuevo="Microsoft Excel"),  # 4.º válido: se ignora
        ]
    )
    cv = validar_adaptacion(salida, PERFIL)
    assert "JavaScript" in cv.habilidades and "Java" in cv.habilidades
    assert "T-SQL" in cv.habilidades and "Excel" in cv.habilidades
    assert "Microsoft Excel" not in cv.habilidades
    assert len(cv.descartes) == 2


def test_sin_ia_se_usa_el_cv_base():
    cv = asyncio.run(adaptar(DatosUsuario(PERFIL), Requisitos(), "oferta", cliente=None,
                             clave=None, usuario_id=1))  # fmt: skip
    assert cv == cv_base(PERFIL) and not cv.adaptado


def test_pdf_ats_texto_extraible():
    contenido = generar_pdf(cv_base(PERFIL), CONTACTO)
    lector = PdfReader(io.BytesIO(contenido))
    texto = "\n".join(p.extract_text() for p in lector.pages)
    for seccion in ("PERFIL", "FORMACIÓN", "EXPERIENCIA", "PROYECTOS", "HABILIDADES", "IDIOMAS"):
        assert seccion in texto
    assert "Ana María Pérez Gómez" in texto and "ana.perez@gmail.com" in texto
    assert "Ingeniería" in texto and "Python" in texto
    assert len(lector.pages) == 1
    assert not any(p.images for p in lector.pages)  # sin foto


def test_perfil_extenso_cabe_en_dos_paginas():
    largo = PERFIL.model_copy(
        update={
            "experiencia": [
                Experiencia(empresa=f"Empresa {i}", cargo="Auxiliar de sistemas",
                            logros=[f"Logro número {j} con una descripción larga " * 3
                                    for j in range(8)])
                for i in range(8)
            ],
            "proyectos": [Proyecto(nombre=f"Proyecto {i}", descripcion="Descripción. " * 20)
                          for i in range(10)],
        }
    )  # fmt: skip
    lector = PdfReader(io.BytesIO(generar_pdf(cv_base(largo), CONTACTO)))
    assert len(lector.pages) <= 2


@pytest.mark.parametrize(
    ("nombre", "esperado"),
    [
        ("Ana María Pérez Gómez", "CV_Ana_Perez.pdf"),
        ("Luis Peña", "CV_Luis_Pena.pdf"),
        ("José", "CV_Jose.pdf"),
    ],
)
def test_nombre_de_archivo(nombre, esperado):
    assert nombre_archivo(nombre) == esperado


@pytest.fixture
def cliente(tmp_path):
    base = BaseAsistente.abrir(tmp_path / "a.db")
    with base.transaccion() as cx:
        cx.execute("INSERT INTO usuarios(id, telegram_id, directorio, creado) VALUES (1,1,'u','x')")
    config = cargar_configuracion().asistente
    cliente = ClienteGemini(
        config.gemini, base, 60, reloj=lambda: datetime(2026, 10, 4, tzinfo=UTC)
    )
    yield cliente
    asyncio.run(cliente.cerrar())
    base.cerrar()


def gemini(contenido):
    return httpx.Response(
        200, json={"candidates": [{"content": {"parts": [{"text": json.dumps(contenido)}]}}]}
    )


@respx.mock
def test_adaptar_con_ia_valida_la_salida(cliente):
    respx.post(URL).mock(
        return_value=gemini({"resumen": "Orientada a datos con Kubernetes.",
                             "habilidades_primero": ["SQL", "Python"]})
    )  # fmt: skip
    cv = asyncio.run(adaptar(DatosUsuario(PERFIL), Requisitos(obligatorios=["SQL"]),
                             "Analista de datos", cliente=cliente, clave="k", usuario_id=1))  # fmt: skip
    assert cv.resumen == PERFIL.resumen  # el resumen traía una tecnología ajena
    assert cv.habilidades[:2] == ["SQL", "Python"]


@respx.mock
def test_carta_con_tecnologia_ajena_usa_la_basica(cliente):
    respx.post(URL).mock(return_value=gemini({"carta": "Tengo 3 años con Kubernetes y AWS."}))
    carta = asyncio.run(redactar_carta(DatosUsuario(PERFIL), cv_base(PERFIL), "Practicante",
                                       "oferta", 1000, cliente=cliente, clave="k", usuario_id=1))  # fmt: skip
    assert carta == carta_basica(PERFIL, "Practicante", PERFIL.habilidades_tecnicas, 1000)
    assert "Kubernetes" not in carta


@respx.mock
def test_carta_valida_de_la_ia(cliente):
    texto = "Me interesa la práctica porque he desarrollado una API con Django y Python."
    respx.post(URL).mock(return_value=gemini({"carta": texto}))
    carta = asyncio.run(redactar_carta(DatosUsuario(PERFIL), cv_base(PERFIL), "Practicante",
                                       "oferta", 1000, cliente=cliente, clave="k", usuario_id=1))  # fmt: skip
    assert carta == texto
