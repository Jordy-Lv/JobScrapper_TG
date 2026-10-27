"""Coherencia de plataformas: con `automatica: true` necesita nombre, dominio y selectores."""

import json
import re
from pathlib import Path

import pytest
from bs4 import BeautifulSoup
from pydantic import ValidationError

from buscador_vacantes.asistente import textos as t
from buscador_vacantes.asistente.familias_ats import RUTA_FAMILIAS, leer_familias
from buscador_vacantes.asistente.reglas_motor import RUTA_REGLAS, leer_reglas
from buscador_vacantes.asistente.vacantes import PLATAFORMAS
from buscador_vacantes.comun import config as cfg
from buscador_vacantes.comun.config import AsistentePlataforma, cargar_configuracion
from buscador_vacantes.comun.normalizar import normalizar_texto

RUTA_SELECTORES = cfg.RAIZ / "assets" / "asistente" / "selectores"


def incompletas(
    plataformas: dict[str, AsistentePlataforma],
    nombres: dict[str, str] = t.NOMBRES_PLATAFORMA,
    dominios: dict[str, str] = PLATAFORMAS,
    ruta_selectores: Path = RUTA_SELECTORES,
) -> list[str]:
    """Lo que le falta a cada plataforma automática para postular sola."""
    faltas = []
    for plataforma, ajustes in plataformas.items():
        if not ajustes.automatica:
            continue
        if plataforma not in nombres:
            faltas.append(f"{plataforma}: sin nombre")
        if plataforma not in dominios.values():
            faltas.append(f"{plataforma}: sin dominio")
        if not (ruta_selectores / f"{plataforma}.json").is_file():
            faltas.append(f"{plataforma}: sin selectores")
    return faltas


def test_las_plataformas_automaticas_de_config_estan_completas():
    assert incompletas(cargar_configuracion().asistente.plataformas) == []


def test_elempleo_postula_sola_tras_su_piloto():
    """Activada el 2026-10-18 (tarea 7.1); la autorización de datos ya nombra su cuenta."""
    asistente = cargar_configuracion().asistente
    assert asistente.plataformas["elempleo"].automatica is True
    assert "Computrabajo, Magneto y elempleo" in asistente.politica.texto
    assert asistente.politica.version == 4  # la 4 suma LinkedIn (postular-linkedin)
    assert "documentos PDF que decidas guardar" in asistente.politica.texto
    for frase in ("LinkedIn (opcional)", "permiso opcional sobre las páginas https",
                  "nunca tu sesión ni tu contraseña"):
        assert frase in asistente.politica.texto


def test_falta_un_nombre():
    plataformas = cargar_configuracion().asistente.plataformas
    nombres = {k: v for k, v in t.NOMBRES_PLATAFORMA.items() if k != "magneto"}
    assert incompletas(plataformas, nombres=nombres) == ["magneto: sin nombre"]


def test_falta_el_dominio():
    plataformas = cargar_configuracion().asistente.plataformas
    dominios = {k: v for k, v in PLATAFORMAS.items() if v != "computrabajo"}
    assert incompletas(plataformas, dominios=dominios) == ["computrabajo: sin dominio"]


def test_automatica_sin_selectores_cargados(tmp_path):
    plataformas = {"elempleo": AsistentePlataforma(automatica=True)}
    assert incompletas(plataformas, ruta_selectores=tmp_path) == ["elempleo: sin selectores"]
    assert incompletas(plataformas) == []  # con assets/asistente/selectores/elempleo.json


def test_sin_automatica_no_exige_nada():
    plataformas = {"inventada": AsistentePlataforma(automatica=False)}
    assert incompletas(plataformas) == []


# --- reglas del motor genérico (assets/asistente/motor_generico.json) ----------------------


def test_reglas_del_motor_generico_validas_y_con_version():
    reglas = leer_reglas()
    assert reglas.version
    for clave, textos in reglas.textos:
        for idioma in ("es", "en", "pt"):
            assert getattr(textos, idioma), (clave, idioma)
    assert "beecatcher" in reglas.trampas
    # El desafío visible del reCAPTCHA Enterprise que usan Greenhouse y Ashby
    assert any("recaptcha/enterprise/bframe" in s for s in reglas.captcha.desafio)


def test_reglas_del_motor_generico_rechaza_un_idioma_faltante(tmp_path):
    datos = json.loads(RUTA_REGLAS.read_text(encoding="utf-8"))
    del datos["textos"]["enviar"]["pt"]
    ruta = tmp_path / "motor_generico.json"
    ruta.write_text(json.dumps(datos), encoding="utf-8")
    with pytest.raises(ValidationError, match="pt"):
        leer_reglas(ruta)
    datos["textos"]["enviar"]["pt"] = ["enviar"]
    datos["desconocida"] = 1
    ruta.write_text(json.dumps(datos), encoding="utf-8")
    with pytest.raises(ValidationError, match="desconocida"):
        leer_reglas(ruta)


# --- datos de las familias de ATS (assets/asistente/familias_ats.json) ---------------------------


def test_familias_ats_validas_con_version_y_las_cuatro_familias():
    datos = leer_familias()
    assert datos.version
    assert set(datos.familias) == {"greenhouse", "ashby", "lever", "typeform"}
    for nombre, familia in datos.familias.items():
        enviar, exito = familia.enviar, familia.exito
        assert enviar.selectores or enviar.textos, nombre
        assert exito.url or exito.textos or exito.selectores, nombre


def test_cada_familia_declara_su_cv_su_boton_y_su_exito():
    familias = leer_familias().familias
    assert "input#resume" in familias["greenhouse"].cv
    assert "Submit application" in familias["greenhouse"].enviar.textos
    assert "/confirmation" in familias["greenhouse"].exito.url
    assert "#_systemfield_resume" in familias["ashby"].cv
    assert "Submit Application" in familias["ashby"].enviar.textos
    assert "input[name=resume]" in familias["lever"].cv
    assert "#btn-submit" in familias["lever"].enviar.selectores
    assert "/thanks" in familias["lever"].exito.url
    assert familias["typeform"].cv == []  # el archivo es una pantalla más del formulario


def test_familias_ats_rechaza_claves_desconocidas_familias_sin_boton_y_codigo(tmp_path):
    datos = json.loads(RUTA_FAMILIAS.read_text(encoding="utf-8"))
    ruta = tmp_path / "familias_ats.json"

    def escribir_y_leer(cambio):
        copia = json.loads(json.dumps(datos))
        cambio(copia)
        ruta.write_text(json.dumps(copia), encoding="utf-8")
        return leer_familias(ruta)

    with pytest.raises(ValidationError, match="desconocida"):
        escribir_y_leer(lambda d: d["familias"]["lever"].update(desconocida=1))
    with pytest.raises(ValidationError, match="botón"):
        escribir_y_leer(lambda d: d["familias"]["lever"]["enviar"].update(selectores=[], textos=[]))
    with pytest.raises(ValidationError, match="éxito"):
        escribir_y_leer(
            lambda d: d["familias"]["lever"]["exito"].update(url=[], textos=[], selectores=[])
        )
    with pytest.raises(ValidationError, match="código"):
        escribir_y_leer(lambda d: d["familias"]["lever"]["cv"].append("javascript:alert(1)"))
    with pytest.raises(ValidationError, match="vacío"):
        escribir_y_leer(lambda d: d["familias"]["lever"]["cv"].append("  "))


# --- selectores de LinkedIn (assets/asistente/selectores/linkedin.json, postular-linkedin 5.2) ---

FIXTURES_LINKEDIN = cfg.RAIZ / "tests" / "fixtures" / "linkedin"


def linkedin():
    return json.loads((RUTA_SELECTORES / "linkedin.json").read_text(encoding="utf-8"))


def pagina(nombre):
    texto = (FIXTURES_LINKEDIN / nombre).read_text(encoding="utf-8")
    return BeautifulSoup(texto, "lxml")


def test_linkedin_trae_version_y_el_cv_de_perfil_multiple_y_sigue_apagada():
    datos = linkedin()
    assert datos["version"] and datos["cv"]["modo"] == "perfil_multiple"
    # Con el archivo cargado la plataforma sigue apagada hasta el piloto: sin postular sola
    assert cargar_configuracion().asistente.plataformas["linkedin"].automatica is False


def test_los_hosts_prohibidos_de_linkedin_coinciden_con_la_configuracion():
    config = cargar_configuracion().asistente.linkedin
    assert set(linkedin()["hosts_prohibidos"]) == set(config.hosts_prohibidos)


def test_los_textos_de_linkedin_estan_normalizados_y_la_progresion_es_una_expresion_valida():
    datos = linkedin()
    for grupo, textos in datos["textos"].items():
        for texto in textos:
            assert texto == normalizar_texto(texto), (grupo, texto)
    for nombres in datos["modal"]["botones"].values():
        assert all(n == normalizar_texto(n) for n in nombres)
    assert re.compile(datos["modal"]["progreso"]["texto"]).search("1/4 paginas")


def test_el_boton_de_la_sencilla_y_el_enlace_de_la_externa_se_encuentran_en_sus_recortes():
    datos = linkedin()
    sencilla = pagina("vacante_sencilla.html")
    assert len(sencilla.select(datos["tipo"]["sencilla"][0])) == 1
    assert not sencilla.select(datos["tipo"]["externa"][0])
    externa = pagina("vacante_externa.html")
    [enlace] = externa.select(datos["tipo"]["externa"][0])  # el del aviso de privacidad no cuenta
    assert datos["tipo"]["externa_destino"]["ruta"] in enlace["href"]
    assert len(externa.select("a[href*='/safety/go']")) == 2
    assert not externa.select(datos["tipo"]["sencilla"][0])


def test_cerrada_y_pausada_se_distinguen_solo_por_el_texto():
    datos = linkedin()
    for archivo, grupo, otro in (("vacante_cerrada.html", "cerrada", "pausada"),
                                 ("vacante_pausada.html", "pausada", "cerrada")):  # fmt: skip
        visible = normalizar_texto(pagina(archivo).get_text(" "))
        assert any(t in visible for t in datos["textos"][grupo])
        assert not any(t in visible for t in datos["textos"][otro])
        botones = ",".join([datos["tipo"]["sencilla"][0], datos["tipo"]["externa"][0]])
        assert not pagina(archivo).select(botones)


@pytest.mark.parametrize(
    "archivo", ["modal_un_paso.html", "modal_varios_pasos_1.html", "modal_varios_pasos_2_cv.html"]
)
def test_el_modal_se_encuentra_con_su_titulo_y_su_boton_de_cerrar(archivo):
    modal = linkedin()["modal"]
    sopa = pagina(archivo)
    assert len(sopa.select(modal["contenedor"][0])) == 1
    assert len(sopa.select(modal["titulo"][0])) == 1
    assert len(sopa.select(modal["cerrar"][0])) == 1


def test_el_modal_de_un_paso_se_cierra_con_su_x_y_desmarca_seguir_a_la_empresa():
    modal = linkedin()["modal"]
    sopa = pagina("modal_un_paso.html")
    [casilla] = sopa.select(modal["seguir_empresa"]["selector"][0])
    assert casilla.has_attr("checked") and modal["seguir_empresa"]["accion"] == "desmarcar"
    botones = [normalizar_texto(b.get_text(" ")) for b in sopa.select("dialog button")]
    assert any(t in botones for t in modal["botones"]["enviar"])
    assert not any(t in botones for t in modal["botones"]["siguiente"])  # no hay «Siguiente»


def test_el_modal_de_varios_pasos_trae_progreso_siguiente_y_el_grupo_de_cv():
    modal = linkedin()["modal"]
    uno, dos = pagina("modal_varios_pasos_1.html"), pagina("modal_varios_pasos_2_cv.html")
    progreso = re.compile(modal["progreso"]["texto"])
    assert progreso.search(normalizar_texto(uno.get_text(" ")))
    assert progreso.search(normalizar_texto(dos.get_text(" "))).groups() == ("2", "4")
    botones = [normalizar_texto(b.get_text(" ")) for b in dos.select("dialog button")]
    assert all(any(t in botones for t in modal["botones"][b]) for b in ("siguiente", "volver"))
    assert dos.select(modal["cv"]["grupo"][0]) and not dos.select("input[type=file]")
    assert modal["cv"]["subir"] in botones and modal["cv"]["obligatorio"] in normalizar_texto(
        dos.get_text(" ")
    )


def test_el_segundo_dialogo_de_cierre_se_distingue_del_modal_y_ofrece_descartar():
    modal = linkedin()["modal"]
    cierre = pagina("modal_confirmar_cierre.html")
    [dialogo] = cierre.select(modal["confirmar_cierre"]["contenedor"][0])
    textos = [normalizar_texto(b.get_text(" ")) for b in dialogo.select("button")]
    assert modal["confirmar_cierre"]["descartar"] in textos
    # Con el modal abierto y el aviso encima, el contenedor del modal sigue siendo uno solo
    ambos = BeautifulSoup(
        str(pagina("modal_un_paso.html").select_one("dialog")) + str(dialogo), "lxml"
    )
    assert len(ambos.select(modal["contenedor"][0])) == 1
    assert len(ambos.select(modal["confirmar_cierre"]["contenedor"][0])) == 1


def test_el_flujo_declarado_de_linkedin_solo_revisa_si_la_vacante_sigue_abierta():
    """El resto (sencilla y externa) lo conduce el motor genérico de la extensión."""
    [paso] = linkedin()["postular"]
    assert (paso["nombre"], paso["accion"]) == ("revisar_vacante", "detectar")
    assert {c["resultado"] for c in paso["casos"]} == {"vacante_cerrada"}
    assert not any(p.get("envia") for p in linkedin()["postular"])  # nunca pulsa «Enviar»
