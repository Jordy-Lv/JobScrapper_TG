"""Las rutas a los recursos de assets/ apuntan a archivos que existen.

Un recurso movido sin actualizar su ruta solo fallaría en ejecución (PDF sin tipografía,
publicación sin encabezado, selectores sin cargar, TLS del SPE); aquí falla en la suite.
"""

from buscador_vacantes.asistente import cv_pdf, nucleo, respuestas, tecnologias
from buscador_vacantes.comun import config as cfg
from buscador_vacantes.radar.fuentes import spe

PORTALES_CON_SELECTORES = ("computrabajo", "magneto")
TIPOGRAFIAS = ("LiberationSans-Regular.ttf", "LiberationSans-Bold.ttf", "LiberationSans-Italic.ttf")


def test_recursos_del_asistente_existen():
    assert respuestas.RUTA_BANCO.is_file()
    assert tecnologias.RUTA.is_file()
    for portal in PORTALES_CON_SELECTORES:
        assert (nucleo.RUTA_SELECTORES / f"{portal}.json").is_file()
    for tipografia in TIPOGRAFIAS:
        assert (cv_pdf.FUENTES / tipografia).is_file()


def test_recursos_del_radar_existen():
    assert spe.CERTIFICADO_INTERMEDIO.is_file()
    config = cfg.cargar_configuracion()
    assert (cfg.RAIZ / config.banner.imagen).is_file()
    assert (cfg.RAIZ / cfg.Banner().imagen).is_file()  # valor por defecto del esquema


def test_recursos_de_marca_existen():
    for archivo in ("logo.jpg", "logo_emblema.png", "welcome_banner.jpg"):
        assert (cfg.RAIZ / "assets" / "marca" / archivo).is_file()


def test_no_quedan_archivos_sueltos_en_la_raiz_de_assets():
    sueltos = sorted(p.name for p in (cfg.RAIZ / "assets").iterdir() if p.is_file())
    # logo_v1 y logo_v2 esperan la decisión del dueño (se borran o pasan a marca/)
    assert set(sueltos) <= {"logo_v1.jpg", "logo_v2.jpg"}, sueltos
