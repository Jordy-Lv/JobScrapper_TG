from datetime import datetime, timedelta

import pytest

from config import cargar_configuracion
from fechas import ZONA
from filtros import Filtros, Motivo
from modelo import Categoria, Vacante, Veredicto

AHORA = datetime(2026, 10, 3, 12, 0, tzinfo=ZONA)
A, R, D = Veredicto.ACEPTAR, Veredicto.RECHAZAR, Veredicto.DUDOSA


@pytest.fixture(scope="module")
def filtros():
    return Filtros(cargar_configuracion().filtros)


def vac(titulo, ubicacion="Bogotá, Colombia", modalidad=None, descripcion=None, dias=1):
    return Vacante(
        fuente="prueba", id_fuente="1", titulo=titulo, empresa="Empresa", url="https://x/1",
        keyword="kw", ubicacion=ubicacion, modalidad=modalidad, descripcion=descripcion,
        publicada=AHORA - timedelta(days=dias) if dias is not None else None,
    )  # fmt: skip


@pytest.mark.parametrize(
    ("titulo", "veredicto", "motivo", "categoria"),
    [
        # Escenarios de la spec filtrado-vacantes
        ("Desarrollador Java Senior", R, Motivo.SENIORITY, None),
        ("Aprendiz SENA Desarrollo de Software", A, Motivo.ACEPTADA, Categoria.PRACTICAS),
        ("Practicante Contable", R, Motivo.NO_TI, None),
        ("Practicante", D, Motivo.DUDOSA, None),
        ("Analista de Procesos", D, Motivo.DUDOSA, None),
        ("Practicante de Sistemas en Srta. Group", A, Motivo.ACEPTADA, Categoria.PRACTICAS),
        ("Práctica profesional Tecnología", A, Motivo.ACEPTADA, Categoria.PRACTICAS),
        ("DBA Junior SQL Server", A, Motivo.ACEPTADA, Categoria.BASES_DATOS),
        ("Analista de Datos Jr - Power BI", A, Motivo.ACEPTADA, Categoria.DATOS),
        ("Aprendiz SENA Soporte de Redes", A, Motivo.ACEPTADA, Categoria.PRACTICAS),
        ("Analista Junior", D, Motivo.DUDOSA, None),
        ("Analista Jr CloudOps (SysOps AWS)", A, Motivo.ACEPTADA, Categoria.INFRAESTRUCTURA),
        ("Aprendiz Análisis de Datos", A, Motivo.ACEPTADA, Categoria.PRACTICAS),
        ("Técnico de Soporte IT Junior", A, Motivo.ACEPTADA, Categoria.SOPORTE),
        # Resto de roles de TI
        ("Analista de Redes Junior", A, Motivo.ACEPTADA, Categoria.INFRAESTRUCTURA),
        ("QA Tester Junior", A, Motivo.ACEPTADA, Categoria.QA),
        ("Analista SOC Junior", A, Motivo.ACEPTADA, Categoria.CIBERSEGURIDAD),
        ("Desarrollador Backend Jr. Python", A, Motivo.ACEPTADA, Categoria.DESARROLLO),
        ("Desarrollador C# .NET Junior", A, Motivo.ACEPTADA, Categoria.DESARROLLO),
        ("Auxiliar de Sistemas", A, Motivo.ACEPTADA, Categoria.SOPORTE),
        ("Ingeniero de Sistemas Junior", A, Motivo.ACEPTADA, Categoria.OTROS_TI),
        ("Junior DevOps Engineer", A, Motivo.ACEPTADA, Categoria.INFRAESTRUCTURA),
        # Seniority y otros rechazos
        ("Semi Senior Java Developer", R, Motivo.SENIORITY, None),
        ("Líder Técnico de Desarrollo", R, Motivo.SENIORITY, None),
        ("Desarrollador Sr. Python", R, Motivo.SENIORITY, None),
        ("Desarrollador con 3 años de experiencia", R, Motivo.SENIORITY, None),
        ("Aprendiz de Cocina", R, Motivo.NO_TI, None),
        ("Asesor Comercial", R, Motivo.NO_TI, None),
        ("Practicante Redes Sociales", D, Motivo.DUDOSA, None),
        ("Practicante Sistemas de Gestión de Calidad", R, Motivo.NO_TI, None),
        # Sin nivel → dudosa
        ("Desarrollador Java", D, Motivo.DUDOSA, None),
        # TI junto a un área no TI en el título → dudosa
        ("Programador de Mantenimiento Junior", D, Motivo.DUDOSA, None),
        ("Docente programador por horas junior", D, Motivo.DUDOSA, None),
        ("Practicante Seguridad Salud en el trabajo", R, Motivo.NO_TI, None),
    ],
)  # fmt: skip
def test_veredicto_por_titulo(filtros, titulo, veredicto, motivo, categoria):
    evaluacion = filtros.evaluar(vac(titulo), AHORA)
    assert (evaluacion.veredicto, evaluacion.motivo) == (veredicto, motivo), evaluacion
    assert evaluacion.categoria == categoria


def test_seniority_solo_en_la_descripcion_no_rechaza(filtros):
    vacante = vac(
        "Desarrollador Junior",
        descripcion="Trabajarás con el líder técnico y el manager del equipo senior.",
    )
    evaluacion = filtros.evaluar(vacante, AHORA)
    assert evaluacion.veredicto == A
    assert evaluacion.categoria == Categoria.DESARROLLO


def test_experiencia_alta_en_la_descripcion_rechaza(filtros):
    vacante = vac("Desarrollador Junior", descripcion="Requisitos: 4 años de experiencia en Java.")
    assert filtros.evaluar(vacante, AHORA).motivo == Motivo.SENIORITY


@pytest.mark.parametrize(
    "descripcion",
    [
        "Somos una empresa con 10 años en el mercado.",
        "Experiencia de 1 a 3 años en desarrollo web.",
        "Experiencia mínima de 6 meses.",
    ],
)
def test_anios_que_no_rechazan(filtros, descripcion):
    vacante = vac("Desarrollador Junior", descripcion=descripcion)
    assert filtros.evaluar(vacante, AHORA).veredicto == A


def test_vacante_antigua(filtros):
    evaluacion = filtros.evaluar(vac("Practicante de Sistemas", dias=20), AHORA)
    assert (evaluacion.veredicto, evaluacion.motivo) == (R, Motivo.ANTIGUEDAD)
    assert filtros.evaluar(vac("Practicante de Sistemas", dias=15), AHORA).veredicto == A
    assert filtros.evaluar(vac("Practicante de Sistemas", dias=None), AHORA).veredicto == A


@pytest.mark.parametrize(
    ("ubicacion", "modalidad", "veredicto", "motivo"),
    [
        ("Cartagena, Bolívar", None, A, Motivo.ACEPTADA),
        ("Copacabana", "Presencial", A, Motivo.ACEPTADA),
        (None, None, A, Motivo.ACEPTADA),
        ("Lima, Perú (Presencial)", None, R, Motivo.UBICACION),
        ("Chile", "Presencial", R, Motivo.UBICACION),
        ("Remoto - solo residentes en México", "Remoto", R, Motivo.UBICACION),
        ("Remoto (solo residentes en Chile)", "Remoto", R, Motivo.UBICACION),
        ("Remoto, Mexico", "Remoto", R, Motivo.UBICACION),
        ("Remoto - residentes en Colombia", "Remoto", A, Motivo.ACEPTADA),
        ("Remoto LATAM", "Remoto", A, Motivo.ACEPTADA),
        ("Remoto (cualquier país)", "Remoto", A, Motivo.ACEPTADA),
        ("Bogotá", "Remoto", A, Motivo.ACEPTADA),
        ("Remoto", "Remoto", D, Motivo.REMOTO_SIN_PAIS),
        ("Remoto (solo residentes en el país de la empresa)", "Remoto", D, Motivo.REMOTO_SIN_PAIS),
    ],
)
def test_alcance_geografico(filtros, ubicacion, modalidad, veredicto, motivo):
    evaluacion = filtros.evaluar(vac("Desarrollador Junior", ubicacion, modalidad), AHORA)
    assert (evaluacion.veredicto, evaluacion.motivo) == (veredicto, motivo), evaluacion


def test_remoto_sin_pais_no_salva_lo_que_no_es_ti(filtros):
    evaluacion = filtros.evaluar(vac("Asesor Comercial", "Remoto", "Remoto"), AHORA)
    assert evaluacion.motivo == Motivo.NO_TI


@pytest.mark.parametrize(
    ("titulo", "descripcion"),
    [
        ("Auxiliar logistico rionegro", "Manejo de sistemas de inventario y software ERP."),
        ("Instalador de proyectos y servicios junior", "Cableado estructurado y redes de datos."),
        ("Banco de Talentos Aprendices Técnicos", "Técnicos en sistemas, desarrollo de software."),
    ],
)
def test_ti_solo_en_descripcion_es_dudosa(filtros, titulo, descripcion):
    evaluacion = filtros.evaluar(vac(titulo, descripcion=descripcion), AHORA)
    assert evaluacion.veredicto == D, evaluacion


def test_area_no_ti_con_sistemas_solo_en_descripcion_es_dudosa(filtros):
    vacante = vac("Practicante Contable", descripcion="Manejo de sistemas contables y Excel.")
    assert filtros.evaluar(vacante, AHORA).veredicto == D


def test_categoria_ia_de_respaldo(filtros):
    assert filtros.categoria_por_terminos(vac("Desarrollador web")) == Categoria.DESARROLLO
    assert filtros.categoria_por_terminos(vac("Analista")) == Categoria.OTROS_TI
    assert filtros.categoria_por_terminos(vac("Pasante de datos")) == Categoria.PRACTICAS


@pytest.mark.parametrize(
    ("titulo", "veredicto", "categoria"),
    [
        ("Practicantes técnicos y tecnólogos en Sistemas", A, Categoria.PRACTICAS),
        ("Aprendiz SENA - Mantenimiento de Cómputo", A, Categoria.PRACTICAS),
        ("GenO - Programa de Pasantías", D, None),
        ("Desarrolladores Junior", A, Categoria.DESARROLLO),
    ],
)
def test_plurales_y_soporte_de_computo(filtros, titulo, veredicto, categoria):
    evaluacion = filtros.evaluar(vac(titulo), AHORA)
    assert (evaluacion.veredicto, evaluacion.categoria) == (veredicto, categoria), evaluacion


def test_plural_no_aplica_a_terminos_cortos(filtros):
    # "its" no es "it": sin TI ni disparadores se rechaza
    evaluacion = filtros.evaluar(vac("Its Coordinator Assistant"), AHORA)
    assert evaluacion.motivo != Motivo.ACEPTADA


def test_remoto_en_portal_colombiano_implica_colombia(filtros):
    vacante = vac("Desarrollador Junior", "Remoto", "Remoto")
    vacante.fuente = "computrabajo"
    assert filtros.evaluar(vacante, AHORA).veredicto == A
    vacante.fuente = "getonboard"
    assert filtros.evaluar(vacante, AHORA).motivo == Motivo.REMOTO_SIN_PAIS


def test_reino_unido_es_exterior(filtros):
    vacante = vac("Desarrollador Junior", "London Area, United Kingdom", "Remoto")
    assert filtros.evaluar(vacante, AHORA).motivo == Motivo.UBICACION
