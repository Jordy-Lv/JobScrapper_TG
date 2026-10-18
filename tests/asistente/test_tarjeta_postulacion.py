from datetime import UTC, datetime

from buscador_vacantes.asistente import progreso
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


def test_progreso_muestra_la_barra_con_porcentaje_y_tiempo_antes_del_estado():
    texto = tp.texto(tp.Card(fase=tp.PROGRESO), datos(etapa=1, segundos_etapa=5))
    barra = progreso.linea_barra(1, 5)
    assert f"\n\n{barra}\n\n<blockquote>" in texto
    assert "37 %" in barra and "~25 s" in barra


def test_la_barra_solo_va_en_el_progreso():
    assert "%" not in tp.texto(tp.Card(), datos())
    pregunta = datos(pendiente={"id": 1, "pregunta": "?"})
    assert "%" not in tp.texto(tp.Card(fase=tp.PREGUNTA), pregunta)


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
    assert texto.startswith("✅ <b>Postulación enviada</b>\n<b>Aprendiz &lt;SENA&gt;</b>\nEuro\n")
    assert "██████████████  100 %" in texto
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
                 tp.CERRADA, tp.CUENTA, tp.CANCELADA):  # fmt: skip
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


def test_cuenta_muestra_los_segundos_la_barra_y_el_boton_cancelar():
    d = datos(pid=0, id_corto="abc", segundos=3, total=5)
    texto = tp.texto(tp.Card(fase=tp.CUENTA), d)
    assert texto.split("\n") == [
        "<b>Aprendiz &lt;SENA&gt;</b>",
        "Euro",
        "",
        "<blockquote>⚡ Postulando en 3 s",
        "▰▰▱▱▱</blockquote>",
    ]
    assert tp.botones(tp.Card(fase=tp.CUENTA), d, cb) == [[("Cancelar", "cb:cancel:abc")]]


def test_la_barra_se_llena_hasta_el_final_y_no_pasa_de_diez_casillas():
    assert tp._barra(5, 5) == "▱▱▱▱▱"
    assert tp._barra(1, 5) == "▰▰▰▰▱"
    assert tp._barra(0, 5) == "▰▰▰▰▰"
    assert len(tp._barra(30, 60)) == 10


def test_cancelada_dice_que_no_envio_nada_y_ofrece_postular():
    d = datos(pid=0, id_corto="abc")
    card = tp.Card(fase=tp.CANCELADA)
    assert "<blockquote>Cancelaste la postulación. No envié nada.</blockquote>" in tp.texto(card, d)
    assert tp.botones(card, d, cb) == [[("Postular", "cb:post:abc")]]


def test_cancelada_por_reinicio_avisa_que_la_cuenta_se_interrumpio():
    card = tp.Card(fase=tp.CANCELADA, motivo="interrumpida")
    texto = tp.texto(card, datos(pid=0, id_corto="abc"))
    assert "La cuenta se interrumpió; no envié nada." in texto


def test_la_cuenta_conserva_el_bloque_de_conexion_del_alta():
    d = datos(pid=0, id_corto="abc", segundos=2, total=5,
              conexion=["🔗 <b>Conexión con tus portales</b>"])  # fmt: skip
    texto = tp.texto(tp.Card(fase=tp.CUENTA), d)
    assert texto.index("Conexión con tus portales") < texto.index("Postulando en 2 s")


# --- preguntas de dato y revisión de respuestas ----------------------------------------------


def pendiente_dato(opciones=("SENA", "ITM")):
    return {"id": 4, "pregunta": "¿En qué institución estudias?", "opciones": list(opciones),
            "tipo": "dato"}  # fmt: skip


def test_pregunta_de_dato_con_sugerencias_escribir_y_reservado():
    card = tp.Card(fase=tp.PREGUNTA, pregunta={"id": 4, "n": 1, "total": 1})
    d = datos(pendiente=pendiente_dato())
    texto = tp.texto(card, d)
    assert "<b>¿En qué institución estudias?</b>" in texto
    assert "Elige una opción o escríbela tú." in texto and "Escribe tu respuesta." not in texto
    assert tp.botones(card, d, cb) == [
        [("SENA", cb("pend", 4, 0)), ("ITM", cb("pend", 4, 1))],
        [(tp.BOTON_ESCRIBIR, cb("pesc", 4))],
        [(tp.BOTON_RESERVADO, cb("pres", 4))],
    ]


def test_pregunta_de_dato_tras_escribir_yo_espera_texto():
    card = tp.Card(fase=tp.PREGUNTA, pregunta={"id": 4, "n": 1, "total": 1, "escribir": True})
    d = datos(pendiente=pendiente_dato())
    assert "Escribe tu respuesta." in tp.texto(card, d)
    assert etiquetas(tp.botones(card, d, cb)) == [[tp.BOTON_RESERVADO]]


def test_pregunta_de_dato_sin_sugerencias_no_ofrece_escribir_yo():
    card = tp.Card(fase=tp.PREGUNTA, pregunta={"id": 4, "n": 1, "total": 1})
    d = datos(pendiente=pendiente_dato(opciones=()))
    assert "Escribe tu respuesta." in tp.texto(card, d)
    assert etiquetas(tp.botones(card, d, cb)) == [[tp.BOTON_RESERVADO]]


def test_pregunta_del_formulario_sigue_como_antes():
    card = tp.Card(fase=tp.PREGUNTA, pregunta={"id": 5, "n": 1, "total": 1})
    d = datos(pendiente={"id": 5, "pregunta": "¿Tienes moto?", "opciones": ["Sí", "No"],
                         "tipo": "formulario"})  # fmt: skip
    assert tp.botones(card, d, cb) == [[("Sí", cb("pend", 5, 0))], [("No", cb("pend", 5, 1))]]
    assert "Elige una opción" not in tp.texto(card, d)


REVISION = [
    {"id": 31, "pregunta": "¿Por qué te interesa?", "respuesta": "Quiero <aprender>.",
     "origen": "ia"},
    {"id": 32, "pregunta": "¿Qué estudias?", "respuesta": "ADSO en el SENA.", "origen": "usuario"},
]  # fmt: skip


def test_revision_muestra_las_respuestas_y_aclara_que_no_se_envio_nada():
    card = tp.Card(fase=tp.REVISION)
    d = datos(revision=REVISION)
    texto = tp.texto(card, d)
    assert "Aún no envié nada" in texto
    assert "1· ¿Por qué te interesa?\n<b>Quiero &lt;aprender&gt;.</b>" in texto
    assert "<b>ADSO en el SENA.</b> 💬" in texto  # la corregida por el usuario
    assert tp.botones(card, d, cb) == [
        [("✅ Enviar", cb("rev", 7, "ok")), ("✏️ Corregir", cb("rev", 7, "c"))]
    ]


def test_revision_corregir_lista_las_respuestas_y_pide_el_texto():
    d = datos(revision=REVISION)
    lista = tp.Card(fase=tp.REVISION, vista=tp.CORREGIR)
    assert "¿Qué respuesta quieres corregir?" in tp.texto(lista, d)
    assert tp.botones(lista, d, cb) == [
        [("1", cb("rev", 7, 1)), ("2", cb("rev", 7, 2))],
        [("Volver", cb("rev", 7, "v"))],
    ]
    escribiendo = tp.Card(fase=tp.REVISION, pregunta={"corrigiendo": 32})
    assert "texto nuevo para la respuesta 2" in tp.texto(escribiendo, d)
    assert tp.botones(escribiendo, d, cb) == [[("Volver", cb("rev", 7, "v"))]]


def test_revision_larga_va_aparte_y_la_card_lo_dice():
    larga = [{"id": n, "pregunta": f"Pregunta {n}", "respuesta": "x" * 900, "origen": "ia"}
             for n in range(6)]  # fmt: skip
    card = tp.Card(fase=tp.REVISION)
    d = datos(revision=larga)
    assert not tp.revision_cabe(card, d)
    texto = tp.texto(card, d)
    assert len(texto) <= tp.MAX_TEXTO and "mensajes de abajo" in texto and "x" * 900 not in texto
