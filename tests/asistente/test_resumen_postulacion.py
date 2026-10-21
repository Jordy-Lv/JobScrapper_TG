from datetime import UTC, datetime

from buscador_vacantes.asistente.campos import RESERVADO
from buscador_vacantes.asistente.resumen_postulacion import (
    DatosResumen,
    de_que_trata,
    descripcion_corta,
    hoja_de_vida,
    partir,
    respuestas,
    tarjeta,
)
from buscador_vacantes.asistente.vacantes import VacanteIndexada

CUANDO = datetime(2026, 10, 5, 23, 23, tzinfo=UTC)


def vacante(**cambios):
    datos = dict(id_corto="abc", clave="computrabajo:1", fuente="computrabajo",
                 plataforma="computrabajo", url="https://co.computrabajo.com/o?a=1&b=2",
                 titulo="Aprendiz <SENA>", empresa="Euro", enviada_en=None,
                 detalle="Apoyo en soporte. " * 10)  # fmt: skip
    datos.update(cambios)
    return VacanteIndexada(**datos)


def resp(n, origen="perfil", respuesta="Sí"):
    return {"pregunta": f"¿Pregunta {n} <b>?", "respuesta": respuesta, "origen": origen}


def test_descripcion_corta_corta_en_un_final_de_frase():
    texto = "Primera frase larga de la vacante. " * 40
    corta = descripcion_corta(texto, 200)
    assert len(corta) <= 200 and corta.endswith(".")
    assert descripcion_corta("corta") == "corta"


def test_tarjeta_con_encuesta_titulo_empresa_y_cita():
    d = DatosResumen(vacante(), "computrabajo", CUANDO, respuestas=[resp(i) for i in range(4)])
    lineas = tarjeta(d).split("\n")
    assert lineas[0] == "✅ <b>Postulación enviada</b>"
    assert lineas[1] == "<b>Aprendiz &lt;SENA&gt;</b>" and lineas[2] == "Euro · Computrabajo"
    assert lineas[3] == "" and lineas[4] == "██████████████  100 %" and lineas[5] == ""
    assert lineas[6] == "<blockquote>Computrabajo confirmó tu postulación"
    assert lineas[8] == "Encuesta de 4 · HdV del perfil</blockquote>"


def test_tarjeta_confirmada_con_duracion_y_folio():
    d = DatosResumen(vacante(), "computrabajo", CUANDO, duracion_s=14, folio="P-12")
    lineas = tarjeta(d).split("\n")
    assert lineas[7].endswith(" · 14 s · Folio P-12")
    largo = DatosResumen(vacante(), "computrabajo", CUANDO, duracion_s=75)
    assert " · 1 min 15 s" in tarjeta(largo)


def test_tarjeta_confirmada_omite_duracion_y_folio_si_faltan():
    texto = tarjeta(DatosResumen(vacante(), "computrabajo", CUANDO))
    assert "Folio" not in texto and " s" not in texto.split("\n")[7]
    sin_hora = tarjeta(DatosResumen(vacante(), "computrabajo", None, duracion_s=9))
    assert "<blockquote>Computrabajo confirmó tu postulación\n9 s\n" in sin_hora
    nada = tarjeta(DatosResumen(vacante(), "computrabajo", None))
    assert "confirmó tu postulación\nSin encuesta · HdV del perfil</blockquote>" in nada


def test_tarjeta_sin_encuesta_y_sin_confirmacion():
    d = DatosResumen(vacante(), "computrabajo", CUANDO)
    assert tarjeta(d).endswith("Sin encuesta · HdV del perfil</blockquote>")
    d = DatosResumen(
        vacante(), "computrabajo", CUANDO, respuestas=[resp(1)], confirmada=False,
        duracion_s=14, folio="P-12",
    )  # fmt: skip
    texto = tarjeta(d)
    assert texto.startswith("❔ <b>Aprendiz") and "no mostró la confirmación" in texto
    assert "Postulación enviada" not in texto and "100 %" not in texto
    assert "Folio" not in texto and "14 s" not in texto


def test_hoja_de_vida_segun_los_pasos():
    base = dict(vacante=vacante(), plataforma="computrabajo", enviada_en=None)
    assert hoja_de_vida(DatosResumen(**base, cv_adjunto="CV_Ana.pdf")) == "CV adaptado adjunto"
    actualizada = DatosResumen(**base, pasos=["cv_subir", "cv_verificar"])
    assert hoja_de_vida(actualizada) == "CV adaptado en tu perfil"
    fallo = DatosResumen(**base, pasos=["cv_subir", "cv_verificar_fallo"])
    assert hoja_de_vida(fallo) == "HdV del perfil"


def test_respuestas_con_iconos_de_origen_y_leyenda():
    d = DatosResumen(
        vacante(), "computrabajo", CUANDO,
        respuestas=[resp(1, "perfil", "SENA"), resp(2, "ia"), resp(3, "aprendida")],
    )  # fmt: skip
    texto = "\n".join(respuestas(d))
    assert "1· ¿Pregunta 1 &lt;b&gt;?\n<b>SENA</b> 👤" in texto
    assert "<b>Sí</b> 🤖" in texto and "<b>Sí</b> 💬" in texto
    assert texto.endswith("👤 tu perfil · 🤖 redactada con IA · 💬 lo que me dijiste")


def test_redactada_con_un_dato_del_usuario_va_con_ia_y_la_corregida_con_lo_que_dijiste():
    d = DatosResumen(
        vacante(), "computrabajo", CUANDO,
        respuestas=[resp(1, "ia", "Estudio ADSO en el SENA."), resp(2, "usuario", "Me gusta."),
                    resp(3, "aprendida", RESERVADO)],
    )  # fmt: skip
    texto = "\n".join(respuestas(d))
    assert "<b>Estudio ADSO en el SENA.</b> 🤖" in texto and "redactada con IA" in texto
    assert "<b>Me gusta.</b> 💬" in texto
    assert RESERVADO not in texto and "<b>—</b> 💬" in texto


def test_respuestas_largas_se_parten_sin_pasar_el_limite_de_telegram():
    d = DatosResumen(vacante(), "computrabajo", CUANDO,
                     respuestas=[resp(i, "ia", "x" * 450) for i in range(20)])  # fmt: skip
    salida = respuestas(d)
    assert len(salida) > 1 and all(len(m) <= 4000 for m in salida)


def test_de_que_trata_ficha_descripcion_plegable_y_requisitos():
    ficha = {
        "salario": "$ 1.750.905 mensual",
        "ubicacion": "Duitama, Boyacá",
        "vence": "2026-12-04",
    }
    d = DatosResumen(
        vacante(ficha=ficha), "computrabajo", CUANDO, afinidad=60,
        requisitos={"obligatorios": ["Sistemas"], "nivel": "Junior", "modalidad": "Presencial"},
    )  # fmt: skip
    texto = "\n".join(de_que_trata(d))
    assert "📍 Duitama, Boyacá" in texto and "💰 $ 1.750.905 mensual" in texto
    assert "<blockquote expandable>Apoyo en soporte." in texto
    assert "Piden: Sistemas" in texto and "Nivel: Junior · Modalidad: Presencial" in texto
    assert "🎯 Tu afinidad: 60 %" in texto and "Vence 04/12/2026" in texto


def test_partir_no_corta_lineas():
    assert partir(["a" * 10, "b" * 10, "c" * 10], maximo=21) == [
        "a" * 10 + "\n" + "b" * 10,
        "c" * 10,
    ]
