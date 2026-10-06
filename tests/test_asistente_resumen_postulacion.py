from datetime import UTC, datetime

from buscador_vacantes.asistente.resumen_postulacion import (
    DatosResumen,
    descripcion_corta,
    hoja_de_vida,
    mensajes,
    partir,
)
from buscador_vacantes.asistente.vacantes import VacanteIndexada


def vacante(**cambios):
    datos = dict(id_corto="abc", clave="computrabajo:1", fuente="computrabajo",
                 plataforma="computrabajo", url="https://co.computrabajo.com/o?a=1&b=2",
                 titulo="Aprendiz <SENA>", empresa="Euro", enviada_en=None,
                 detalle="Apoyo en soporte. " * 10)  # fmt: skip
    datos.update(cambios)
    return VacanteIndexada(**datos)


def test_descripcion_corta_corta_en_un_final_de_frase():
    texto = "Primera frase larga de la vacante. " * 40
    corta = descripcion_corta(texto, 200)
    assert len(corta) <= 200 and corta.endswith(".")
    assert descripcion_corta("corta") == "corta"


def test_mensajes_escapan_html_y_no_pasan_el_limite_de_telegram():
    respuestas = [{"pregunta": f"¿Pregunta {i} <b>?", "respuesta": "x" * 450, "origen": "ia"}
                  for i in range(20)]  # fmt: skip
    d = DatosResumen(vacante(), "computrabajo", datetime(2026, 10, 5, 21, 0, tzinfo=UTC),
                     respuestas=respuestas)  # fmt: skip
    salida = mensajes(d)
    assert len(salida) > 1 and all(len(m) <= 4000 for m in salida)
    todo = "\n".join(salida)
    assert "Aprendiz &lt;SENA&gt;" in todo and "¿Pregunta 3 &lt;b&gt;?" in todo
    assert 'href="https://co.computrabajo.com/o?a=1&amp;b=2"' in todo
    assert "Lo que respondí (20)" in todo


def test_sin_preguntas_lo_dice():
    d = DatosResumen(vacante(), "computrabajo", None)
    assert "Computrabajo no pidió encuesta" in mensajes(d)[-1]


def test_hoja_de_vida_segun_los_pasos():
    base = dict(vacante=vacante(), plataforma="computrabajo", enviada_en=None)
    assert "Adjunté tu CV" in hoja_de_vida(DatosResumen(**base, cv_adjunto="CV_Ana.pdf"))
    actualizada = DatosResumen(**base, pasos=["cv_subir", "cv_verificar"])
    assert "Actualicé la hoja de vida de tu perfil" in hoja_de_vida(actualizada)
    fallo = DatosResumen(**base, pasos=["cv_subir", "cv_verificar_fallo"])
    assert "guardada en tu perfil" in hoja_de_vida(fallo)


def test_partir_no_corta_lineas():
    assert partir(["a" * 10, "b" * 10, "c" * 10], maximo=21) == [
        "a" * 10 + "\n" + "b" * 10,
        "c" * 10,
    ]


def test_sin_encuesta_lo_dice_en_la_cabecera():
    d = DatosResumen(vacante(), "computrabajo", None)
    assert "Sin encuesta" in mensajes(d)[0]
