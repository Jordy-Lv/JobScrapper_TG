from datetime import UTC, datetime

from buscador_vacantes.asistente import tarjeta_postulacion as tp
from buscador_vacantes.asistente.resumen_postulacion import DatosResumen, recortar
from buscador_vacantes.asistente.vacantes import VacanteIndexada

CUANDO = datetime(2026, 10, 5, 23, 23, tzinfo=UTC)
URL = "https://co.computrabajo.com/o?a=1&b=2"


def cb(*partes):
    return "cb:" + ":".join(str(p) for p in partes)


def datos(**cambios):
    base = dict(pid=7, titulo="Aprendiz <SENA>", empresa="Euro", plataforma="computrabajo", url=URL)
    base.update(cambios)
    return tp.Datos(**base)


def resumen(**cambios):
    vacante = VacanteIndexada(
        id_corto="abc", clave="computrabajo:1", fuente="computrabajo", plataforma="computrabajo",
        url=URL, titulo="Aprendiz <SENA>", empresa="Euro", enviada_en=None,
        detalle="Apoyo en soporte. " * 10,
    )  # fmt: skip
    base = dict(
        vacante=vacante, plataforma="computrabajo", enviada_en=CUANDO,
        respuestas=[{"pregunta": "¿Estudias?", "respuesta": "Sí", "origen": "perfil"}],
    )  # fmt: skip
    base.update(cambios)
    return DatosResumen(**base)


def etiquetas(botones):
    return [[texto for texto, _ in fila] for fila in botones or []]


def test_en_cola_escapa_el_titulo_y_no_lleva_botones():
    card = tp.Card()
    texto = tp.texto(card, datos())
    assert texto.split("\n") == [
        "<b>Aprendiz &lt;SENA&gt;</b>",
        "Euro",
        "",
        "<blockquote>En cola. Te aviso el resultado.</blockquote>",
    ]
    assert tp.botones(card, datos(), cb) is None


def test_progreso_marca_las_etapas_dentro_del_blockquote():
    texto = tp.texto(tp.Card(fase=tp.PROGRESO), datos(etapa=1))
    assert "<blockquote>✓ Abriendo la oferta\n⠋ <b>Preparando tu hoja de vida…</b>" in texto
    assert texto.endswith("<i>· Enviando y confirmando</i></blockquote>")


def test_el_bloque_de_conexion_va_antes_del_estado_y_sus_botones_primero():
    d = datos(
        conexion=["🔗 <b>Conexión con tus portales</b>", "✓ Navegador vinculado"],
        botones_conexion=[[("Confirmar Computrabajo", cb("cuenta", "computrabajo", "si"))]],
    )
    texto = tp.texto(tp.Card(fase=tp.PROGRESO), d)
    assert texto.index("Conexión con tus portales") < texto.index("<blockquote>")
    assert etiquetas(tp.botones(tp.Card(fase=tp.PROGRESO), d, cb)) == [["Confirmar Computrabajo"]]


def test_pregunta_con_opciones_muestra_el_avance_y_un_boton_por_opcion():
    card = tp.Card(fase=tp.PREGUNTA, pregunta={"id": 5, "n": 2, "total": 3})
    d = datos(pendiente={"id": 5, "pregunta": "¿Tienes <moto>?", "opciones": ["Sí", "No"]})
    texto = tp.texto(card, d)
    assert "Pregunta rápida (2 de 3)" in texto and "<b>¿Tienes &lt;moto&gt;?</b>" in texto
    assert "Escribe tu respuesta" not in texto
    assert tp.botones(card, d, cb) == [[("Sí", cb("pend", 5, 0))], [("No", cb("pend", 5, 1))]]


def test_pregunta_de_texto_libre_pide_escribir_y_no_muestra_avance_si_es_una():
    card = tp.Card(fase=tp.PREGUNTA, pregunta={"id": 5, "n": 1, "total": 1})
    d = datos(pendiente={"id": 5, "pregunta": "¿Por qué te interesa?", "opciones": []})
    texto = tp.texto(card, d)
    assert "Pregunta rápida\n" in texto and "(1 de 1)" not in texto
    assert "Escribe tu respuesta." in texto
    assert tp.botones(card, d, cb) is None


def test_sesion_pendiente_ofrece_crear_cuenta_con_el_enlace_del_portal():
    card = tp.Card(fase=tp.SESION)
    assert "Inicia sesión en Computrabajo en tu navegador y sigo solo" in tp.texto(card, datos())
    assert tp.botones(card, datos(), cb) == [[("Crear cuenta", "url:https://co.computrabajo.com/")]]
    assert tp.botones(card, datos(plataforma="otra"), cb) is None


def test_verificacion_pide_completarla_en_la_pestana_abierta():
    texto = tp.texto(tp.Card(fase=tp.VERIFICACION), datos())
    assert "verificación" in texto and "pestaña" in texto
    assert tp.botones(tp.Card(fase=tp.VERIFICACION), datos(), cb) is None


def test_bloqueo_explica_la_causa_aclara_que_no_se_envio_y_ofrece_reintentar():
    card = tp.Card(fase=tp.BLOQUEO, motivo="portal_correo_incorrecto")
    texto = tp.texto(card, datos())
    assert "Computrabajo dice que no puede enviarte correos" in texto
    assert "No envié nada todavía." in texto
    assert tp.botones(card, datos(), cb) == [[("Reintentar", cb("rei", 7))]]


def test_respaldo_explica_el_motivo_y_ofrece_las_acciones_con_el_seguimiento_marcado():
    card = tp.Card(fase=tp.RESPALDO, motivo="formulario_desconocido")
    assert "el formulario del portal cambió" in tp.texto(card, datos())
    assert etiquetas(tp.botones(card, datos(), cb)) == [
        ["Ver vacante", "Pegar preguntas"], ["Ya me postulé", "No me interesa"],
    ]  # fmt: skip
    marcado = tp.botones(card, datos(seguimiento="postulada"), cb)
    assert marcado[1][0] == ("✓ Ya me postulé", cb("seg", 7, "postulada"))


def test_respaldo_sin_navegador_ofrece_vincularlo_en_la_misma_card():
    card = tp.Card(fase=tp.RESPALDO, motivo="sin_navegador")
    assert "Falta vincular tu navegador." in tp.texto(card, datos())
    assert tp.botones(card, datos(), cb)[0][0] == ("Vincular navegador", cb("vincular"))


def test_cerrada_dice_el_estado_y_enlaza_la_vacante():
    card = tp.Card(fase=tp.CERRADA, motivo="vacante_cerrada")
    assert "Vacante cerrada" in tp.texto(card, datos())
    assert etiquetas(tp.botones(card, datos(), cb)) == [["Ver vacante"]]
    assert tp.botones(card, datos(url=None), cb) is None


def test_confirmada_muestra_la_cita_las_vistas_y_el_seguimiento_en_filas_de_a_tres():
    card = tp.Card(fase=tp.CONFIRMADA)
    d = datos(resumen=resumen())
    texto = tp.texto(card, d)
    assert texto.startswith("✅ <b>Aprendiz &lt;SENA&gt;</b>\nEuro\n")
    assert "Computrabajo confirmó tu postulación" in texto
    assert "Encuesta de 1 · HdV del perfil</blockquote>" in texto
    assert "¿Cómo te fue?" not in texto
    botones = tp.botones(card, d, cb)
    assert etiquetas(botones) == [
        ["Respuestas", "De qué trata", "Ver vacante"], ["Generar guía para entrevista"],
    ]  # fmt: skip
    assert botones[0][2] == ("Ver vacante", f"url:{URL}")
    assert botones[1][0] == ("Generar guía para entrevista", cb("guia", 7))


def test_incierta_avisa_que_no_hubo_confirmacion_y_conserva_las_vistas():
    card = tp.Card(fase=tp.INCIERTA)
    d = datos(resumen=resumen())
    texto = tp.texto(card, d)
    assert texto.startswith("❔") and "no mostró la confirmación" in texto
    assert etiquetas(tp.botones(card, d, cb))[0][:2] == ["Respuestas", "De qué trata"]


def test_confirmada_sin_datos_de_la_vacante_usa_un_texto_basico():
    texto = tp.texto(tp.Card(fase=tp.CONFIRMADA), datos())
    assert "✅ Computrabajo confirmó tu postulación" in texto
    sin_vistas = tp.botones(tp.Card(fase=tp.CONFIRMADA), datos(), cb)
    assert etiquetas(sin_vistas) == [["Ver vacante"], ["Generar guía para entrevista"]]


def test_vistas_internas_llevan_volver_y_el_contenido_de_la_vista():
    d = datos(resumen=resumen())
    respuestas = tp.Card(fase=tp.CONFIRMADA, vista=tp.RESPUESTAS)
    assert "Tus respuestas" in tp.texto(respuestas, d) and "<b>Sí</b> 👤" in tp.texto(respuestas, d)
    assert tp.botones(respuestas, d, cb) == [[("Volver", cb("res", 7, "v"))]]
    trata = tp.Card(fase=tp.INCIERTA, vista=tp.DE_QUE_TRATA)
    assert "Apoyo en soporte." in tp.texto(trata, d)
    assert tp.botones(trata, d, cb) == [[("Volver", cb("res", 7, "v"))]]


def test_vista_larga_se_recorta_con_puntos_suspensivos_sin_romper_etiquetas():
    largas = [{"pregunta": f"¿Pregunta {i}?", "respuesta": "x" * 450, "origen": "ia"}
              for i in range(30)]  # fmt: skip
    d = datos(resumen=resumen(respuestas=largas))
    texto = tp.texto(tp.Card(fase=tp.CONFIRMADA, vista=tp.RESPUESTAS), d)
    assert len(texto) <= tp.MAX_TEXTO and texto.endswith("…")
    assert texto.count("<b>") == texto.count("</b>")


def test_recortar_una_linea_enorme_quita_etiquetas_y_entidades_partidas():
    linea = "<b>" + "a&amp;" * 3000 + "</b>"
    texto = recortar([linea], 100)
    assert len(texto) <= 100 and "<" not in texto and texto.endswith("…")
    assert not texto[:-1].endswith("&") and not texto[:-1].endswith("&am")


def test_ningun_estado_pasa_el_limite_ni_mas_de_tres_botones_por_fila():
    pendiente = {"id": 1, "pregunta": "¿?" * 5000, "opciones": [str(i) for i in range(12)]}
    for fase in (tp.EN_COLA, tp.ESPERANDO_NAVEGADOR, tp.PREGUNTA, tp.PROGRESO, tp.SESION,
                 tp.VERIFICACION, tp.BLOQUEO, tp.CONFIRMADA, tp.INCIERTA, tp.RESPALDO,
                 tp.CERRADA):  # fmt: skip
        card = tp.Card(fase=fase, motivo="portal_redirige_inicio", pregunta={"id": 1, "n": 1})
        d = datos(titulo="T" * 5000, pendiente=pendiente, resumen=resumen())
        assert len(tp.texto(card, d)) <= tp.MAX_TEXTO, fase
        assert all(len(fila) <= tp.POR_FILA or fase == tp.PREGUNTA
                   for fila in tp.botones(card, d, cb) or []), fase  # fmt: skip


def test_el_estado_se_guarda_y_se_lee_como_texto():
    card = tp.Card(mensaje_id=9, fase=tp.PREGUNTA, vista=tp.RESPUESTAS,
                   pregunta={"id": 3, "n": 1, "total": 2}, motivo="x")  # fmt: skip
    assert tp.Card.de_texto(card.a_texto()) == card
    assert tp.Card.de_texto("") is None and tp.Card.de_texto(None) is None
