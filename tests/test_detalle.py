from pathlib import Path

import pytest

from buscador_vacantes.comun.config import cargar_configuracion
from buscador_vacantes.radar.detalle import (
    MAX_EXTRA_MODALIDAD,
    extraer_descripcion,
    recortar_descripcion,
)

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def terminos():
    return cargar_configuracion().filtros.ubicacion.terminos_modalidad


def test_extrae_la_descripcion_del_detalle_real():
    texto = extraer_descripcion((FIXTURES / "linkedin_detalle.html").read_text(encoding="utf-8"))
    assert texto is not None
    assert texto.startswith("En Robot.com, automatizamos empresas")
    assert "Presencial: Colombia, Estados Unidos" in texto
    assert "\n" not in texto and "  " not in texto
    assert "<" not in texto


def test_sin_bloque_de_descripcion_no_devuelve_nada():
    html = (FIXTURES / "linkedin_detalle_sin_descripcion.html").read_text(encoding="utf-8")
    assert extraer_descripcion(html) is None
    assert extraer_descripcion("") is None


def test_el_recorte_respeta_el_maximo(terminos):
    texto = "Trabajarás con equipos de datos. " * 200
    recorte = recortar_descripcion(texto, 500, terminos)
    assert len(recorte) <= 500
    assert recorte == recortar_descripcion(recorte, 500, terminos)


def test_texto_corto_no_se_toca(terminos):
    recorte = recortar_descripcion("  Oferta   remota \n de TI ", 500, terminos)
    assert recorte == "Oferta remota de TI"


def test_conserva_la_frase_de_modalidad_del_final(terminos):
    relleno = "Responsabilidades del cargo: documentar, probar y desplegar servicios. " * 40
    texto = relleno + "La posición es 100% remota para toda Colombia. Beneficios de ley."
    recorte = recortar_descripcion(texto, 300, terminos)
    assert "100% remota" in recorte
    assert len(recorte) <= 300 + MAX_EXTRA_MODALIDAD + 3
    assert "Beneficios de ley" not in recorte


def test_no_parte_palabras(terminos):
    texto = "programación " * 100
    recorte = recortar_descripcion(texto, 50, terminos)
    assert recorte == " ".join(["programación"] * 3)  # 3 × 12 + 2 espacios = 38 ≤ 50 < 51


def test_las_frases_extra_tienen_tope(terminos):
    texto = "Introducción. " + "Trabajo remoto desde casa todos los días. " * 100
    recorte = recortar_descripcion(texto, 20, terminos)
    assert len(recorte) <= 20 + MAX_EXTRA_MODALIDAD + 3
    assert recorte.startswith("Introducción.")


def test_frase_larguisima_se_recorta_alrededor_de_la_modalidad(terminos):
    cola = "x" * 400 + " la modalidad es presencial en oficina " + "y" * 400
    recorte = recortar_descripcion("Inicio del anuncio. " + cola, 20, terminos)
    assert "presencial" in recorte
    assert len(recorte) < 20 + 400


def test_sin_terminos_solo_recorta(terminos):
    texto = "palabra " * 100
    assert recortar_descripcion(texto, 40, []) == " ".join(["palabra"] * 5)
