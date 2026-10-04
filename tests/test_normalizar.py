from buscador_vacantes.normalizar import (
    coincidencias,
    compilar_terminos,
    huella,
    normalizar_empresa,
    normalizar_texto,
    normalizar_titulo,
)


def test_texto_sin_tildes_y_minusculas():
    assert (
        normalizar_texto("  Práctica   profesional TECNOLOGÍA ")
        == "practica profesional tecnologia"
    )
    assert normalizar_texto(None) == ""


def test_empresa_sin_sufijos_societarios():
    assert normalizar_empresa("Redeban S.A.S.") == "redeban"
    assert normalizar_empresa("Redeban") == "redeban"
    assert normalizar_empresa("Accenture Colombia") == "accenture"
    assert normalizar_empresa("Bancolombia S.A.") == "bancolombia"
    assert normalizar_empresa("Grupo Éxito Ltda.") == "grupo exito"


def test_misma_vacante_en_dos_fuentes():
    linkedin = huella("Practicante de Desarrollo", "Redeban S.A.S.", "linkedin:1")
    computrabajo = huella("Practicante de desarrollo", "Redeban", "computrabajo:abc")
    assert linkedin == computrabajo


def test_titulos_distintos_no_comparten_huella():
    assert huella("Practicante de Desarrollo", "Redeban", "a:1") != huella(
        "Practicante de Datos", "Redeban", "a:2"
    )


def test_empresa_anonima_usa_la_clave():
    uno = huella("Auxiliar de sistemas", "Importante empresa del sector", "computrabajo:1")
    otro = huella("Auxiliar de sistemas", "Importante empresa del sector", "computrabajo:2")
    vacia = huella("Auxiliar de sistemas", "", "computrabajo:3")
    assert len({uno, otro, vacia}) == 3


def test_titulo_sin_puntuacion():
    assert normalizar_titulo("Practicante – Desarrollo (Java)") == "practicante desarrollo java"


def test_limite_de_palabra():
    patron = compilar_terminos(["senior", "sr", "ssr"])
    assert coincidencias(patron, normalizar_texto("Practicante de Sistemas en Srta. Group")) == []
    assert coincidencias(patron, normalizar_texto("Desarrollador Sr. Java")) == ["sr"]


def test_tildes_en_terminos_y_texto():
    patron = compilar_terminos(["práctica", "tecnología"])
    texto = normalizar_texto("Práctica profesional Tecnología")
    assert coincidencias(patron, texto) == ["practica", "tecnologia"]


def test_terminos_con_simbolos():
    patron = compilar_terminos([".net", "c#", "c++", "power bi"])
    texto = normalizar_texto("Desarrollador C# y .NET junior, Power  BI deseable, C++")
    assert set(coincidencias(patron, texto)) == {"c#", ".net", "power bi", "c++"}
    assert coincidencias(compilar_terminos(["ti"]), "gestion de tiendas") == []


def test_lista_vacia():
    assert compilar_terminos([]) is None
    assert coincidencias(None, "texto") == []


def test_entidades_html():
    assert normalizar_texto("Practicante de An&#xE1;lisis &amp; Datos") == (
        "practicante de analisis & datos"
    )
