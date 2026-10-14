from datetime import datetime, timedelta

import pytest

from buscador_vacantes.comun.config import cargar_configuracion
from buscador_vacantes.comun.fechas import ZONA
from buscador_vacantes.comun.modelo import Categoria, Vacante, Veredicto
from buscador_vacantes.radar.filtros import Filtros, Motivo

AHORA = datetime(2026, 10, 3, 12, 0, tzinfo=ZONA)
A, R, D = Veredicto.ACEPTAR, Veredicto.RECHAZAR, Veredicto.DUDOSA


@pytest.fixture(scope="module")
def filtros():
    return Filtros(cargar_configuracion().filtros)


def vac(titulo, ubicacion="Cartagena, Bolívar", modalidad=None, descripcion=None, dias=1):
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
        ("Practicante Contable", D, Motivo.DUDOSA, None),  # sin descripción decide la IA
        ("Auxiliar Contable", R, Motivo.NO_TI, None),
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
        ("Aprendiz de Cocina", D, Motivo.DUDOSA, None),
        ("Asesor Comercial", R, Motivo.NO_TI, None),
        ("Practicante Redes Sociales", D, Motivo.DUDOSA, None),
        ("Practicante Sistemas de Gestión de Calidad", D, Motivo.DUDOSA, None),
        # Sin nivel → dudosa
        ("Desarrollador Java", D, Motivo.DUDOSA, None),
        # TI junto a un área no TI en el título → dudosa
        ("Programador de Mantenimiento Junior", D, Motivo.DUDOSA, None),
        ("Docente programador por horas junior", D, Motivo.DUDOSA, None),
        ("Practicante Seguridad Salud en el trabajo", D, Motivo.DUDOSA, None),
        ("Aprendiz etapa productiva", D, Motivo.DUDOSA, None),
        ("Aprendiz SENA", D, Motivo.DUDOSA, None),  # sin descripción no se rechaza: decide la IA
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
        ("Copacabana", "Presencial", R, Motivo.PRESENCIAL_FUERA),
        (None, None, R, Motivo.PRESENCIAL_FUERA),  # sin ubicación ni descripción
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


@pytest.mark.parametrize(
    ("vacante", "motivo"),
    [
        (vac("Practicante Contable Senior"), Motivo.SENIORITY),
        (vac("Practicante administrativo", dias=20), Motivo.ANTIGUEDAD),
        (vac("Practicante administrativo", "Lima, Perú (Presencial)"), Motivo.UBICACION),
    ],
)
def test_practicas_de_otra_area_siguen_los_demas_rechazos(filtros, vacante, motivo):
    evaluacion = filtros.evaluar(vacante, AHORA)
    assert (evaluacion.veredicto, evaluacion.motivo) == (R, motivo)


def test_practica_de_otra_area_con_funciones_de_ti_llega_a_la_ia(filtros):
    vacante = vac(
        "Practicante administrativo",
        descripcion="Construir tableros en Power BI y consultas SQL para el área.",
    )
    assert filtros.evaluar(vacante, AHORA).veredicto == D


# --- Lista negra (filtro-vacantes-limpias 2.1) ---


@pytest.fixture
def filtros_con_lista_negra():
    config = cargar_configuracion().filtros.model_copy(deep=True)
    config.lista_negra.empresas = ["Magneto empleos"]
    config.lista_negra.palabras = ["promotor"]
    return Filtros(config)


def test_lista_negra_por_empresa_normalizada(filtros_con_lista_negra):
    vacante = vac("Promotor(a) Junior de Tecnología")
    vacante.empresa = "MAGNETO EMPLEOS S.A.S."
    evaluacion = filtros_con_lista_negra.evaluar(vacante, AHORA)
    assert (evaluacion.veredicto, evaluacion.motivo) == (R, Motivo.LISTA_NEGRA)


def test_lista_negra_por_palabra_del_titulo(filtros_con_lista_negra):
    evaluacion = filtros_con_lista_negra.evaluar(vac("Promotor Junior TI"), AHORA)
    assert (evaluacion.veredicto, evaluacion.motivo) == (R, Motivo.LISTA_NEGRA)


def test_lista_negra_va_antes_que_las_demas_reglas(filtros_con_lista_negra):
    # Aceptable por todo lo demás, pero la empresa está en la lista negra
    vacante = vac("Desarrollador Junior")
    vacante.empresa = "Magneto empleos"
    assert filtros_con_lista_negra.evaluar(vacante, AHORA).motivo == Motivo.LISTA_NEGRA
    vacante.empresa = "Otra empresa"
    assert filtros_con_lista_negra.evaluar(vacante, AHORA).veredicto == A


def test_listas_negras_vacias_no_rechazan(filtros):
    vacante = vac("Desarrollador Junior")
    vacante.empresa = ""
    assert filtros.evaluar(vacante, AHORA).veredicto == A


# --- Alcance geográfico con ciudad base (2.2) ---


@pytest.mark.parametrize(
    ("ubicacion", "modalidad", "descripcion", "veredicto", "motivo", "exige"),
    [
        # En la ciudad base pasa con cualquier modalidad
        ("Cartagena, Bolívar", "Presencial", None, A, Motivo.ACEPTADA, None),
        ("Turbaco, Bolívar", "Presencial", None, A, Motivo.ACEPTADA, None),
        ("Mamonal, Cartagena", None, None, A, Motivo.ACEPTADA, None),
        # Presencial en otra ciudad
        ("Valledupar, Cesar", "Presencial", None, R, Motivo.PRESENCIAL_FUERA, None),
        ("Bogotá, Colombia", "Presencial", "Con 2 días remotos", R, Motivo.PRESENCIAL_FUERA, None),
        # Bolívar solo no es la ciudad base
        ("Magangué, Bolívar", "Presencial", None, R, Motivo.PRESENCIAL_FUERA, None),
        # Híbrida en otra ciudad de Colombia
        ("Bogotá", "Presencial y remoto", None, A, Motivo.ACEPTADA, None),
        ("Medellín", "Híbrido", None, A, Motivo.ACEPTADA, None),
        ("Bogotá", "Remoto o híbrido", None, A, Motivo.ACEPTADA, None),
        # Remota en otra ciudad
        ("Medellín", "Remoto", None, A, Motivo.ACEPTADA, None),
        # Modalidad desconocida con y sin descripción
        ("Medellín", None, "Analizarás datos de ventas.", D, Motivo.DUDOSA, "remoto_o_hibrido"),
        ("Cali", None, None, R, Motivo.PRESENCIAL_FUERA, None),
        (None, None, "Apoyarás al equipo de TI.", D, Motivo.DUDOSA, "remoto_o_hibrido"),
        # La descripción solo sirve para remoto o híbrido, nunca para presencial
        ("Bogotá", None, "Modalidad híbrida, 2 días en oficina", A, Motivo.ACEPTADA, None),
        ("Bogotá", None, "Trabajo presencial en la sede", D, Motivo.DUDOSA, "remoto_o_hibrido"),
        # Fuera de Colombia
        ("Lima, Perú", "Híbrido", None, R, Motivo.UBICACION, None),
        ("Cartagena, España", "Presencial", None, R, Motivo.PRESENCIAL_FUERA, None),
    ],
)  # fmt: skip
def test_alcance_con_ciudad_base(
    filtros, ubicacion, modalidad, descripcion, veredicto, motivo, exige
):
    vacante = vac("Analista de datos Jr", ubicacion, modalidad, descripcion)
    evaluacion = filtros.evaluar(vacante, AHORA)
    assert (evaluacion.veredicto, evaluacion.motivo) == (veredicto, motivo), evaluacion
    assert evaluacion.exige_modalidad == exige


def test_modalidad_en_el_titulo_gana_a_la_descripcion(filtros):
    vacante = vac(
        "Desarrollador Junior (presencial)", "Medellín", None, "Equipo con trabajo remoto"
    )
    assert filtros.evaluar(vacante, AHORA).motivo == Motivo.PRESENCIAL_FUERA


def test_en_sitio_en_otra_ciudad(filtros):
    vacante = vac("Soporte en sitio Junior (Boyacá)", "Boyacá")
    assert filtros.evaluar(vacante, AHORA).motivo == Motivo.PRESENCIAL_FUERA


def test_tecnico_en_sistemas_presencial_en_valledupar(filtros):
    vacante = vac("Técnico en Sistemas Valledupar", "Valledupar", "Presencial")
    evaluacion = filtros.evaluar(vacante, AHORA)
    assert (evaluacion.veredicto, evaluacion.motivo) == (R, Motivo.PRESENCIAL_FUERA)


def test_remoto_latam_sigue_igual(filtros):
    vacante = vac("Desarrollador Junior", "Remoto LATAM", "Remoto")
    assert filtros.evaluar(vacante, AHORA).veredicto == A


def test_remoto_sin_pais_no_exige_modalidad(filtros):
    vacante = vac("Desarrollador Junior", "Remoto", "Remoto")
    evaluacion = filtros.evaluar(vacante, AHORA)
    assert (evaluacion.motivo, evaluacion.exige_modalidad) == (Motivo.REMOTO_SIN_PAIS, None)


# --- Soporte de call center solo remoto (2.3) ---


@pytest.mark.parametrize(
    ("titulo", "ubicacion", "modalidad", "descripcion", "veredicto", "motivo", "exige"),
    [
        ("238540 Asesor/a de Soporte técnico ¡Excelente Variable!", "Bogotá", "Presencial", None,
         R, Motivo.CALL_CENTER, None),
        ("Asesor de soporte técnico", "Cartagena, Bolívar", "Presencial", None,
         R, Motivo.CALL_CENTER, None),
        ("Asesor de soporte técnico", "Cartagena, Bolívar", "Híbrido", None,
         R, Motivo.CALL_CENTER, None),
        ("Agente de soporte técnico Junior", "Colombia", "Remoto", None, A, Motivo.ACEPTADA, None),
        ("Asesor de soporte técnico", "Cartagena, Bolívar", None, None,
         R, Motivo.CALL_CENTER, None),
        ("Asesor de soporte técnico", "Cartagena, Bolívar", None, "Atenderás clientes.",
         D, Motivo.DUDOSA, "remoto"),
        ("Asesor de soporte técnico Junior", "Cartagena, Bolívar", None, "Trabajo desde casa.",
         A, Motivo.ACEPTADA, None),
    ],
)  # fmt: skip
def test_call_center_solo_remoto(
    filtros, titulo, ubicacion, modalidad, descripcion, veredicto, motivo, exige
):
    evaluacion = filtros.evaluar(vac(titulo, ubicacion, modalidad, descripcion), AHORA)
    assert (evaluacion.veredicto, evaluacion.motivo) == (veredicto, motivo), evaluacion
    assert evaluacion.exige_modalidad == exige


# --- Veredicto: práctica sin TI, confirmar modalidad y años (2.4) ---


def test_practica_sin_ti_se_rechaza_solo_tras_leer_la_descripcion(filtros):
    descripcion = "Apoyo en archivo, atención de llamadas y tareas administrativas."
    for titulo in ("Aprendiz etapa productiva", "Practicante Contable", "Aprendiz SENA"):
        evaluacion = filtros.evaluar(vac(titulo, descripcion=descripcion), AHORA)
        assert (evaluacion.veredicto, evaluacion.motivo) == (R, Motivo.NO_TI), titulo
        assert evaluacion.detalle == "práctica sin TI"


def test_practica_sin_descripcion_no_se_rechaza_por_no_ti(filtros):
    for titulo in ("Aprendiz etapa productiva", "Practicante Contable", "Aprendiz SENA"):
        evaluacion = filtros.evaluar(vac(titulo), AHORA)
        assert (evaluacion.veredicto, evaluacion.motivo) == (D, Motivo.DUDOSA), titulo


def test_practica_de_otra_area_con_ti_en_la_descripcion_pasa_a_la_ia(filtros):
    vacante = vac("Aprendiz Universitario de Planeación", descripcion="Reportes en SQL y Python.")
    assert filtros.evaluar(vacante, AHORA).veredicto == D


def test_aceptada_por_reglas_que_exige_confirmar_modalidad_es_dudosa(filtros):
    vacante = vac("Desarrollador Junior", "Medellín", None, "Trabajarás con Java y Spring Boot.")
    evaluacion = filtros.evaluar(vacante, AHORA)
    assert (evaluacion.veredicto, evaluacion.exige_modalidad) == (D, "remoto_o_hibrido")


def test_un_anio_de_experiencia_pasa_y_dos_rechazan(filtros):
    uno = vac("Técnico soporte TI Nivel 1 Junior", descripcion="Requiere 1 año de experiencia.")
    dos = vac("Técnico soporte TI Nivel 1 Junior", descripcion="Requiere 2 años de experiencia.")
    assert filtros.evaluar(uno, AHORA).veredicto == A
    assert filtros.evaluar(dos, AHORA).motivo == Motivo.SENIORITY


def test_middle_es_seniority(filtros):
    assert filtros.evaluar(vac("Middle Java Developer"), AHORA).motivo == Motivo.SENIORITY


# --- Guardarraíl de la categoría prácticas (2.5) ---


def con_categoria(titulo, descripcion=None, categoria=Categoria.PRACTICAS):
    vacante = vac(titulo, descripcion=descripcion)
    vacante.categoria = categoria
    return vacante


def test_guardarrail_profesional_marcado_como_practica_va_a_su_area(filtros):
    correccion = filtros.guardarrail_practicas(con_categoria("Programador Staff CELLS"))
    assert correccion is not None
    assert (correccion.original, correccion.nueva) == (Categoria.PRACTICAS, Categoria.DESARROLLO)
    assert not correccion.rechaza


def test_guardarrail_sin_area_va_a_otros_ti(filtros):
    vacante = con_categoria(
        "Ingeniero IBM STERLING B2B", "Integración de sistemas B2B para clientes."
    )
    correccion = filtros.guardarrail_practicas(vacante)
    assert correccion is not None and correccion.nueva == Categoria.OTROS_TI


def test_guardarrail_sin_ti_rechaza(filtros):
    correccion = filtros.guardarrail_practicas(con_categoria("Ingeniero de Procesos"))
    assert correccion is not None and correccion.rechaza


def test_guardarrail_practica_con_evidencia_no_cambia(filtros):
    assert filtros.guardarrail_practicas(con_categoria("Software Engineer Intern")) is None
    assert filtros.guardarrail_practicas(con_categoria("Trainee de Sistemas")) is None


def test_guardarrail_evidencia_fuerte_en_la_descripcion(filtros):
    vacante = con_categoria("Data Engineer Colombia", "Vinculación por contrato de aprendizaje.")
    assert filtros.guardarrail_practicas(vacante) is None


def test_guardarrail_estudiante_solo_en_la_descripcion_no_basta(filtros):
    vacante = con_categoria("Data Engineer Colombia", "Para estudiantes de últimos semestres.")
    correccion = filtros.guardarrail_practicas(vacante)
    assert correccion is not None and correccion.nueva == Categoria.DATOS


def test_guardarrail_ignora_las_demas_categorias(filtros):
    vacante = con_categoria("Programador Staff CELLS", categoria=Categoria.DESARROLLO)
    assert filtros.guardarrail_practicas(vacante) is None
    assert filtros.guardarrail_practicas(con_categoria("Programador", categoria=None)) is None


# --- Ofertas pendientes de detalle ---


def vac_linkedin(titulo, ubicacion="Colombia", descripcion=None):
    vacante = vac(titulo, ubicacion, None, descripcion)
    vacante.fuente = "linkedin"
    return vacante


def evaluar_con_detalle(filtros, vacante):
    return filtros.evaluar(vacante, AHORA, permite_detalle=True)


def test_remota_de_otra_ciudad_queda_pendiente_de_detalle(filtros):
    vacante = vac_linkedin("Software Engineer Intern", "Colombia")
    evaluacion = evaluar_con_detalle(filtros, vacante)
    assert (evaluacion.veredicto, evaluacion.motivo) == (D, Motivo.PENDIENTE_DETALLE)
    assert evaluacion.exige_modalidad == "remoto_o_hibrido"
    # Sin detalle, todo sigue como hoy
    hoy = filtros.evaluar(vacante, AHORA, permite_detalle=False)
    assert (hoy.veredicto, hoy.motivo) == (R, Motivo.PRESENCIAL_FUERA)


def test_titulo_sin_ti_se_rechaza_sin_pedir_detalle(filtros):
    evaluacion = evaluar_con_detalle(filtros, vac_linkedin("Cajera Sur de Bogotá", "Bogotá"))
    assert (evaluacion.veredicto, evaluacion.motivo) == (R, Motivo.NO_TI)


def test_seniority_del_titulo_se_rechaza_sin_pedir_detalle(filtros):
    evaluacion = evaluar_con_detalle(filtros, vac_linkedin("Desarrollador Java Senior", "Bogotá"))
    assert (evaluacion.veredicto, evaluacion.motivo) == (R, Motivo.SENIORITY)


def test_oferta_antigua_o_de_lista_negra_no_pide_detalle(filtros):
    antigua = vac_linkedin("Practicante de Sistemas", "Bogotá")
    antigua.publicada = AHORA - timedelta(days=30)
    assert evaluar_con_detalle(filtros, antigua).motivo == Motivo.ANTIGUEDAD


def test_call_center_sin_modalidad_queda_pendiente(filtros):
    vacante = vac_linkedin("Agente de soporte técnico", "Cartagena, Bolívar")
    evaluacion = evaluar_con_detalle(filtros, vacante)
    assert (evaluacion.veredicto, evaluacion.motivo) == (D, Motivo.PENDIENTE_DETALLE)
    assert evaluacion.exige_modalidad == "remoto"
    hoy = filtros.evaluar(vacante, AHORA)
    assert (hoy.veredicto, hoy.motivo) == (R, Motivo.CALL_CENTER)


@pytest.mark.parametrize("ubicacion", ["Bogotá (Presencial)", "Medellín, Antioquia, en sitio"])
def test_lo_declarado_presencial_se_rechaza_sin_detalle(filtros, ubicacion):
    evaluacion = evaluar_con_detalle(filtros, vac_linkedin("Practicante de Sistemas", ubicacion))
    assert (evaluacion.veredicto, evaluacion.motivo) == (R, Motivo.PRESENCIAL_FUERA)


def test_remoto_en_el_titulo_o_ciudad_base_no_pide_detalle(filtros):
    remoto = evaluar_con_detalle(filtros, vac_linkedin("Practicante de Sistemas (Remoto)"))
    assert (remoto.veredicto, remoto.motivo) == (A, Motivo.ACEPTADA)
    base = evaluar_con_detalle(filtros, vac_linkedin("Practicante de Sistemas", "Cartagena"))
    assert (base.veredicto, base.motivo) == (A, Motivo.ACEPTADA)


def test_fuera_de_colombia_se_rechaza_sin_detalle(filtros):
    vacante = vac_linkedin("Practicante de Sistemas", "Lima, Perú")
    assert evaluar_con_detalle(filtros, vacante).motivo == Motivo.UBICACION


def test_con_descripcion_ya_no_queda_pendiente(filtros):
    vacante = vac_linkedin("Practicante de Sistemas", "Medellín", "Analizarás datos de ventas.")
    evaluacion = evaluar_con_detalle(filtros, vacante)
    assert (evaluacion.veredicto, evaluacion.motivo) == (D, Motivo.DUDOSA)
    assert evaluacion.exige_modalidad == "remoto_o_hibrido"


def test_detalle_que_dice_presencial_no_acepta_por_reglas(filtros):
    vacante = vac_linkedin(
        "Analista Desarrollo Web Proyecto 6 Meses", "Bogotá", "El trabajo es presencial en oficina."
    )
    evaluacion = evaluar_con_detalle(filtros, vacante)
    # La descripción nunca prueba lo presencial: va a la IA con la condición, que la rechaza
    assert (evaluacion.veredicto, evaluacion.exige_modalidad) == (D, "remoto_o_hibrido")


# --- La modalidad que solo sale del detalle la confirma la IA ---


@pytest.mark.parametrize(
    ("ubicacion", "descripcion"),
    [
        ("Bogotá", "Esta posición es 100% remota para toda Colombia."),
        ("Medellín", "Trabajo híbrido, dos días en oficina."),
    ],
)
def test_remoto_o_hibrido_solo_en_la_descripcion_va_a_la_ia(filtros, ubicacion, descripcion):
    vacante = vac_linkedin("Practicante de Sistemas", ubicacion, descripcion)
    evaluacion = evaluar_con_detalle(filtros, vacante)
    assert (evaluacion.veredicto, evaluacion.motivo) == (D, Motivo.DUDOSA)
    assert evaluacion.exige_modalidad == "remoto_o_hibrido"
    # Sin detalle (otras fuentes), las reglas lo siguen aceptando
    assert filtros.evaluar(vacante, AHORA).veredicto == A


def test_call_center_remoto_solo_en_la_descripcion_exige_remoto(filtros):
    vacante = vac_linkedin(
        "Agente de soporte técnico Junior", "Cartagena, Bolívar", "Trabajo desde casa."
    )
    evaluacion = evaluar_con_detalle(filtros, vacante)
    assert (evaluacion.veredicto, evaluacion.exige_modalidad) == (D, "remoto")
    assert filtros.evaluar(vacante, AHORA).veredicto == A


def test_remoto_sin_pais_solo_en_la_descripcion_tambien_va_a_la_ia(filtros):
    vacante = vac_linkedin("Practicante de Sistemas", "Medellín", "Modalidad remota.")
    assert evaluar_con_detalle(filtros, vacante).exige_modalidad == "remoto_o_hibrido"


def test_remoto_en_la_ubicacion_o_el_portal_no_cambia(filtros):
    vacante = vac("Desarrollador Junior", "Bogotá", "Remoto")
    vacante.fuente = "linkedin"
    evaluacion = evaluar_con_detalle(filtros, vacante)
    assert (evaluacion.veredicto, evaluacion.motivo) == (A, Motivo.ACEPTADA)
    assert evaluacion.exige_modalidad is None


def test_las_otras_fuentes_no_cambian(filtros):
    # Computrabajo, elempleo y Magneto no piden detalle: permite_detalle queda en False
    vacante = vac("Practicante de Sistemas", "Bogotá", None, "Trabajo remoto desde casa.")
    assert filtros.evaluar(vacante, AHORA).veredicto == A
