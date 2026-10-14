from datetime import datetime, timedelta
from pathlib import Path

import httpx
import pytest
import respx

from buscador_vacantes.config import cargar_configuracion
from buscador_vacantes.estado import Estado, a_texto, de_texto
from buscador_vacantes.fechas import ZONA
from buscador_vacantes.fuentes.base import CambioHTML
from buscador_vacantes.fuentes.computrabajo import Computrabajo, slug
from buscador_vacantes.fuentes.linkedin import URL_BUSQUEDA, LinkedIn
from buscador_vacantes.rotacion import Consulta

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
        "f_TPR": "r86400", "sortBy": "DD", "start": 0,
    }  # fmt: skip


def test_linkedin_peticion_ordenada_por_fecha_por_defecto(entorno):
    config, _ = entorno
    assert crear(LinkedIn, entorno).construir_peticion("x").params["sortBy"] == "DD"
    # Sin la sección consulta en la configuración, también ordena por fecha
    conf = config.fuentes["linkedin"].model_copy(deep=True)
    conf.opciones.pop("consulta")
    sin_consulta = LinkedIn(conf, config.red, entorno[1])
    assert sin_consulta.construir_peticion("x").params["sortBy"] == "DD"


def test_linkedin_orden_configurable_o_ausente(entorno):
    config, estado = entorno
    for orden, esperado in (("R", "R"), ("", None)):
        conf = config.fuentes["linkedin"].model_copy(deep=True)
        conf.opciones["consulta"]["orden"] = orden
        params = LinkedIn(conf, config.red, estado).construir_peticion("x").params
        assert params.get("sortBy") == esperado


def test_linkedin_pagina_dos_empieza_en_la_tarjeta_diez(entorno):
    fuente = crear(LinkedIn, entorno)
    assert fuente.soporta_paginas and fuente.tamano_pagina == 10
    assert [fuente.construir_peticion("x", p).params["start"] for p in (1, 2, 3)] == [0, 10, 20]


def test_linkedin_config_real_trae_dos_variantes(entorno):
    config, _ = entorno
    variantes = config.fuentes["linkedin"].opciones["variantes"]
    assert [v["location"] for v in variantes] == ["Colombia", "Cartagena, Bolívar, Colombia"]
    assert variantes[0]["f_WT"] == "2,3" and "f_WT" not in variantes[1]


def test_linkedin_variante_remoto_o_hibrido_en_colombia(entorno):
    fuente = crear(LinkedIn, entorno)
    fuente.variante = entorno[0].fuentes["linkedin"].opciones["variantes"][0]
    peticion = fuente.construir_peticion("practicante sistemas")
    assert peticion.params == {
        "keywords": "practicante sistemas", "location": "Colombia", "f_E": "1,2",
        "f_TPR": "r86400", "f_WT": "2,3", "sortBy": "DD", "start": 0,
    }  # fmt: skip


def test_linkedin_variante_ciudad_base(entorno):
    fuente = crear(LinkedIn, entorno)
    fuente.variante = entorno[0].fuentes["linkedin"].opciones["variantes"][1]
    params = fuente.construir_peticion("practicante sistemas").params
    assert params["location"] == "Cartagena, Bolívar, Colombia"
    assert "f_WT" not in params and "modalidad" not in params


def test_linkedin_variante_remoto_o_hibrido_pone_la_modalidad(entorno):
    fuente = crear(LinkedIn, entorno)
    fuente.variante = entorno[0].fuentes["linkedin"].opciones["variantes"][0]
    vacantes = fuente.parsear(respuesta("linkedin_busqueda.html"), "kw", AHORA)
    assert len(vacantes) == 10
    assert {v.modalidad for v in vacantes} == {"Remoto o híbrido"}


def test_linkedin_variante_ciudad_base_deja_la_modalidad_vacia(entorno):
    fuente = crear(LinkedIn, entorno)
    fuente.variante = entorno[0].fuentes["linkedin"].opciones["variantes"][1]
    vacantes = fuente.parsear(respuesta("linkedin_busqueda.html"), "kw", AHORA)
    assert {v.modalidad for v in vacantes} == {None}


def test_linkedin_variante_remoto_o_hibrido_pasa_el_filtro_geografico(entorno):
    from buscador_vacantes.filtros import Filtros

    fuente = crear(LinkedIn, entorno)
    fuente.variante = entorno[0].fuentes["linkedin"].opciones["variantes"][0]
    vacante = fuente.parsear(respuesta("linkedin_busqueda.html"), "kw", AHORA)[0]
    vacante.titulo, vacante.ubicacion = "Practicante de Sistemas", "Bogotá, Distrito Capital"
    evaluacion = Filtros(entorno[0].filtros).evaluar(vacante, AHORA)
    assert evaluacion.veredicto == "aceptar"


# --- LinkedIn: ventana de publicación, sondeos y segunda página --------------------------------

CONSULTA = '"practicante sistemas" OR "aprendiz SENA"'


class Reloj:
    """Reloj controlable; con ``avance`` cada lectura corre ese tiempo (peticiones lentas)."""

    def __init__(self, avance=timedelta(0)):
        self.momento = AHORA
        self.avance = avance

    def __call__(self):
        actual = self.momento
        self.momento += self.avance
        return actual


def tarjetas(n, desde=0):
    items = "".join(
        f'<li><div class="base-search-card" data-entity-urn="urn:li:jobPosting:{desde + i}">'
        f'<h3 class="base-search-card__title">Practicante {desde + i}</h3>'
        f'<h4 class="base-search-card__subtitle"><a>Empresa</a></h4>'
        f'<span class="job-search-card__location">Colombia</span></div></li>'
        for i in range(n)
    )
    return f"<ul>{items}</ul>"


def linkedin(entorno, reloj=None, pausas=None, variante_id=0, **cambios):
    config, estado = entorno
    conf = config.fuentes["linkedin"].model_copy(deep=True)
    for campo, valor in cambios.items():
        setattr(conf, campo, valor)
    fuente = LinkedIn(
        conf, config.red, estado, corrida_id=1,
        dormir=(pausas if pausas is not None else []).append,
        aleatorio=lambda a, b: (a + b) / 2, reloj=reloj or Reloj(),
    )  # fmt: skip
    fuente.variante_id = variante_id
    return fuente


def lote_dos_paginas(keyword=CONSULTA):
    return [Consulta(keyword, "nucleo", 1), Consulta(keyword, "nucleo", 2)]


def parametros(llamada):
    return dict(llamada.request.url.params)


def guardar_sondeo(fuente, hace, keyword=CONSULTA):
    fuente.estado.kv_guardar(fuente._clave_sondeo(keyword), a_texto(AHORA - hace))


def test_linkedin_sin_sondeo_pide_las_ultimas_24_horas(entorno):
    assert crear(LinkedIn, entorno).construir_peticion(CONSULTA).params["f_TPR"] == "r86400"


def test_linkedin_ventana_en_operacion_normal(entorno):
    fuente = linkedin(entorno)
    guardar_sondeo(fuente, timedelta(minutes=60))
    # 60 min desde el sondeo + 30 de margen = 1,5 h, pero el mínimo configurado es 2 h
    assert fuente.construir_peticion(CONSULTA).params["f_TPR"] == "r7200"


def test_linkedin_ventana_es_el_tiempo_desde_el_sondeo_mas_el_margen(entorno):
    config, estado = entorno
    conf = config.fuentes["linkedin"].model_copy(deep=True)
    conf.opciones["consulta"]["ventana_min_h"] = 1
    fuente = LinkedIn(conf, config.red, estado, reloj=Reloj())
    guardar_sondeo(fuente, timedelta(minutes=60))
    assert fuente.construir_peticion(CONSULTA).params["f_TPR"] == "r5400"  # 1,5 h


def test_linkedin_ventana_cubre_el_hueco_tras_un_cooldown(entorno):
    fuente = linkedin(entorno)
    guardar_sondeo(fuente, timedelta(hours=5))
    segundos = int(fuente.construir_peticion(CONSULTA).params["f_TPR"][1:])
    assert segundos >= 5 * 3600  # al menos las 5 h del cooldown
    assert segundos == 5 * 3600 + 30 * 60  # más el margen


def test_linkedin_ventana_nunca_pasa_de_24_horas(entorno):
    fuente = linkedin(entorno)
    guardar_sondeo(fuente, timedelta(days=3))
    assert fuente.construir_peticion(CONSULTA).params["f_TPR"] == "r86400"


def test_linkedin_ventana_minima_de_24_horas_pide_siempre_un_dia(entorno):
    config, estado = entorno
    conf = config.fuentes["linkedin"].model_copy(deep=True)
    conf.opciones["consulta"]["ventana_min_h"] = 24
    fuente = LinkedIn(conf, config.red, estado, reloj=Reloj())
    guardar_sondeo(fuente, timedelta(minutes=10))
    assert fuente.construir_peticion(CONSULTA).params["f_TPR"] == "r86400"


def test_linkedin_sondeo_es_por_variante_y_por_consulta(entorno):
    fuente = linkedin(entorno)
    guardar_sondeo(fuente, timedelta(hours=5))
    assert fuente.construir_peticion(CONSULTA).params["f_TPR"] == "r19800"
    assert fuente.construir_peticion("otra consulta").params["f_TPR"] == "r86400"
    otra_variante = linkedin(entorno, variante_id=1)
    assert otra_variante.construir_peticion(CONSULTA).params["f_TPR"] == "r86400"


def test_linkedin_ventana_se_fija_una_vez_por_consulta_y_corrida(entorno):
    fuente = linkedin(entorno, reloj=Reloj(avance=timedelta(minutes=10)))
    guardar_sondeo(fuente, timedelta(hours=5))
    primera = fuente.construir_peticion(CONSULTA, 1).params["f_TPR"]
    segunda = fuente.construir_peticion(CONSULTA, 2).params["f_TPR"]
    assert primera == segunda == "r19800"


@respx.mock
def test_linkedin_pagina_completa_pide_la_segunda_y_no_mas(entorno):
    pausas = []
    fuente = linkedin(entorno, pausas=pausas)
    ruta = respx.get(URL_BUSQUEDA).mock(return_value=httpx.Response(200, text=tarjetas(10)))
    resultado = fuente.ejecutar(lote_dos_paginas())
    assert ruta.call_count == 2
    assert [parametros(c)["start"] for c in respx.calls] == ["0", "10"]
    assert [parametros(c)["f_TPR"] for c in respx.calls] == ["r86400", "r86400"]
    assert [parametros(c)["sortBy"] for c in respx.calls] == ["DD", "DD"]
    assert pausas == [32.5]  # la pausa propia de 20-45 s entre las dos páginas
    assert len(resultado.vacantes) == 20


@respx.mock
def test_linkedin_pagina_incompleta_no_pide_la_segunda(entorno):
    pausas = []
    fuente = linkedin(entorno, pausas=pausas)
    ruta = respx.get(URL_BUSQUEDA).mock(return_value=httpx.Response(200, text=tarjetas(6)))
    resultado = fuente.ejecutar(lote_dos_paginas())
    assert ruta.call_count == 1 and pausas == []
    assert len(resultado.ejecutadas) == 1 and len(resultado.vacantes) == 6


@respx.mock
def test_linkedin_la_cola_larga_lee_solo_la_primera_pagina(entorno):
    fuente = linkedin(entorno)
    ruta = respx.get(URL_BUSQUEDA).mock(return_value=httpx.Response(200, text=tarjetas(10)))
    fuente.ejecutar([Consulta("cola", "cola_larga", 1)])
    assert ruta.call_count == 1


@respx.mock
def test_linkedin_guarda_el_sondeo_al_terminar_con_la_hora_de_inicio(entorno):
    reloj = Reloj(avance=timedelta(seconds=3))
    fuente = linkedin(entorno, reloj=reloj)
    respx.get(URL_BUSQUEDA).mock(return_value=httpx.Response(200, text=tarjetas(10)))
    fuente.ejecutar(lote_dos_paginas())
    # Se guarda cuándo empezó la primera petición, no la segunda ni el fin de la consulta
    assert fuente.estado.kv_obtener(fuente._clave_sondeo(CONSULTA)) == a_texto(AHORA)


@respx.mock
def test_linkedin_segunda_pagina_con_429_deja_intacto_el_sondeo_anterior(entorno):
    fuente = linkedin(entorno)
    guardar_sondeo(fuente, timedelta(hours=1))
    anterior = fuente.estado.kv_obtener(fuente._clave_sondeo(CONSULTA))
    respx.get(URL_BUSQUEDA).mock(
        side_effect=[httpx.Response(200, text=tarjetas(10)), httpx.Response(429)]
    )
    resultado = fuente.ejecutar(lote_dos_paginas())
    assert resultado.cooldown_hasta is not None
    assert fuente.estado.kv_obtener(fuente._clave_sondeo(CONSULTA)) == anterior


@respx.mock
def test_linkedin_primera_pagina_con_429_no_registra_sondeo(entorno):
    fuente = linkedin(entorno)
    respx.get(URL_BUSQUEDA).mock(return_value=httpx.Response(429))
    fuente.ejecutar(lote_dos_paginas())
    assert fuente.estado.kv_obtener(fuente._clave_sondeo(CONSULTA)) is None


@respx.mock
def test_linkedin_con_ambas_paginas_buenas_actualiza_el_sondeo(entorno):
    fuente = linkedin(entorno)
    guardar_sondeo(fuente, timedelta(hours=1))
    respx.get(URL_BUSQUEDA).mock(return_value=httpx.Response(200, text=tarjetas(10)))
    fuente.ejecutar(lote_dos_paginas())
    assert de_texto(fuente.estado.kv_obtener(fuente._clave_sondeo(CONSULTA))) >= AHORA


@respx.mock
def test_linkedin_respuesta_vacia_cuenta_como_sondeo_exitoso(entorno):
    fuente = linkedin(entorno)
    respx.get(URL_BUSQUEDA).mock(return_value=httpx.Response(200, text=""))
    fuente.ejecutar(lote_dos_paginas())
    assert fuente.estado.kv_obtener(fuente._clave_sondeo(CONSULTA)) is not None


@respx.mock
def test_linkedin_html_distinto_no_registra_sondeo(entorno):
    fuente = linkedin(entorno)
    respx.get(URL_BUSQUEDA).mock(return_value=httpx.Response(200, text="<p>authwall</p>"))
    fuente.ejecutar(lote_dos_paginas())
    assert fuente.estado.kv_obtener(fuente._clave_sondeo(CONSULTA)) is None


@respx.mock
def test_linkedin_dry_run_no_registra_sondeo_ni_cambia_la_ventana(entorno):
    fuente = linkedin(entorno)
    guardar_sondeo(fuente, timedelta(hours=5))
    anterior = fuente.estado.kv_obtener(fuente._clave_sondeo(CONSULTA))
    fuente.persistir_estado = False
    respx.get(URL_BUSQUEDA).mock(return_value=httpx.Response(200, text=tarjetas(10)))
    fuente.ejecutar(lote_dos_paginas())
    assert fuente.estado.kv_obtener(fuente._clave_sondeo(CONSULTA)) == anterior
    assert linkedin(entorno).construir_peticion(CONSULTA).params["f_TPR"] == "r19800"


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
