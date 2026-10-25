from datetime import UTC, datetime

import pytest

from buscador_vacantes.asistente import espera, progreso
from buscador_vacantes.asistente import tarjeta_postulacion as tp
from buscador_vacantes.asistente import textos as t
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
        "Euro · 🔵 Computrabajo",
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


@pytest.mark.parametrize("motivo", ["aplicar_sin_efecto", "llenado_sin_respuesta"])
def test_portal_que_no_proceso_aplicar_dice_que_no_cargo_y_ofrece_reintentar(motivo):
    card = tp.Card(fase=tp.BLOQUEO, motivo=motivo)
    d = datos(plataforma="magneto")
    texto = tp.texto(card, d)
    assert "Magneto no cargó la postulación" in texto
    assert "No envié nada todavía." in texto
    assert "no mostró la confirmación" not in texto
    assert tp.botones(card, d, cb) == [[("Reintentar", cb("rei", 7))]]


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
    assert texto.startswith(
        "✅ <b>Postulación enviada</b>\n<b>Aprendiz &lt;SENA&gt;</b>\nEuro · 🔵 Computrabajo\n"
    )
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
        "Euro · 🔵 Computrabajo",
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


def test_documento_obligatorio_que_falta_ofrece_enviarlo_o_dejar_en_respaldo():
    card = tp.Card(fase=tp.PREGUNTA, pregunta={"id": 6, "n": 1, "total": 1})
    d = datos(pendiente={"id": 6, "tipo": "documento", "opciones": [],
                         "pregunta": "Please upload your <transcripts>"})  # fmt: skip
    texto = tp.texto(card, d)
    assert "Documento necesario" in texto and "Pregunta rápida" not in texto
    assert "<b>Please upload your &lt;transcripts&gt;</b>" in texto
    assert "Envíame el PDF" in texto and "déjala en respaldo" in texto
    assert tp.botones(card, d, cb) == [
        [(tp.BOTON_ENVIAR_DOCUMENTO, cb("docp", 6))],
        [(tp.BOTON_DOCUMENTO_RESPALDO, cb("docr", 6))],
    ]


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


# --- motivo de la espera en la card en cola ------------------------------------------------------


def con_espera(codigo, plataforma="magneto", fase=tp.EN_COLA, **datos_causa):
    espera_ = {"codigo": codigo, "plataforma": plataforma, "datos": datos_causa}
    return tp.Card(fase=fase, espera=espera_)


def cuerpo(card, **cambios):
    return tp.texto(card, datos(plataforma=card.espera["plataforma"], **cambios))


def test_sin_sesion_en_magneto_ofrece_iniciar_sesion_y_crear_cuenta():
    card = con_espera("sin_sesion")
    texto = cuerpo(card)
    assert "<blockquote>⏳ En cola.\n🔒 Inicia sesión en Magneto" in texto
    assert "la postulación sale sola" in texto
    botones = tp.botones(card, datos(plataforma="magneto"), cb)
    assert etiquetas(botones) == [["Iniciar sesión", "Crear cuenta"]]
    assert botones[0][0][1] == "url:https://web.magneto365.com/sign-in"
    assert botones[0][1][1] == "url:https://www.magneto365.com/co"


def test_sin_sesion_en_elempleo_abre_la_portada_mientras_no_se_confirma_su_ingreso():
    botones = tp.botones(con_espera("sin_sesion", "elempleo"), datos(plataforma="elempleo"), cb)
    assert botones[0][0] == ("Iniciar sesión", "url:https://www.elempleo.com/co/")


def test_sin_navegador_ofrece_vincular():
    card = con_espera("sin_navegador", "computrabajo")
    assert "Falta vincular tu navegador" in cuerpo(card)
    assert tp.botones(card, datos(), cb) == [[("Vincular navegador", "cb:vincular")]]


def test_sin_latido_dice_desde_cuando_en_hora_de_bogota():
    card = con_espera("sin_latido", ultimo="2026-10-17T15:42:00+00:00")
    assert "Tu navegador no responde desde las 10:42" in cuerpo(card)
    assert tp.botones(card, datos(plataforma="magneto"), cb) is None


def test_sin_latido_sin_hora_conocida():
    texto = cuerpo(con_espera("sin_latido"))
    assert "Tu navegador no responde." in texto


def test_extension_desactualizada_lleva_versiones_y_boton_solo_con_tienda():
    card = con_espera("extension_desactualizada", version="1.3.0", minima="1.4.0")
    assert "versión 1.3.0" in cuerpo(card) and "la 1.4.0" in cuerpo(card)
    assert tp.botones(card, datos(plataforma="magneto"), cb) is None
    con_tienda = datos(plataforma="magneto", url_tienda="https://tienda.example/ext")
    assert tp.botones(card, con_tienda, cb) == [
        [("Actualizar extensión", "url:https://tienda.example/ext")]
    ]


def test_extension_en_pausa_no_lleva_botones():
    card = con_espera("extension_en_pausa")
    assert "en pausa en la extensión" in cuerpo(card)
    assert tp.botones(card, datos(plataforma="magneto"), cb) is None


def test_plataforma_apagada_sigue_en_cola_y_sin_botones():
    card = con_espera("plataforma_apagada")
    texto = cuerpo(card)
    assert "automática en Magneto está pausada" in texto and "sigue en cola" in texto
    assert "sale sola cuando se reactive" in texto
    assert tp.botones(card, datos(plataforma="magneto"), cb) is None


def test_sin_permiso_pide_activarlo_en_la_extension():
    card = con_espera("sin_permiso", "elempleo")
    assert "activa el permiso de elempleo.com" in cuerpo(card)
    assert "ventana de la extensión" in cuerpo(card)


def test_cuenta_por_confirmar_repite_los_botones_de_la_conexion():
    card = con_espera("cuenta_por_confirmar")
    botones = tp.botones(card, datos(plataforma="magneto"), cb)
    assert etiquetas(botones) == [["Confirmar Magneto", "Cancelar"]]
    assert botones[0][0][1] == "cb:cuenta:magneto:si"


def test_cuenta_distinta_ofrece_cuenta_nueva_o_no_es_mia():
    card = con_espera("cuenta_distinta")
    botones = tp.botones(card, datos(plataforma="magneto"), cb)
    assert etiquetas(botones) == [["Es mi cuenta nueva", "No es mía"]]
    assert botones[0][1][1] == "cb:cuenta:magneto:no"


def test_los_botones_de_cuenta_no_se_duplican_con_la_conexion():
    existente = [[("Confirmar Magneto", "cb:cuenta:magneto:si")]]
    d = datos(plataforma="magneto", botones_conexion=existente)
    for codigo in ("cuenta_por_confirmar", "cuenta_distinta"):
        assert tp.botones(con_espera(codigo), d, cb) == existente


def test_correo_ilegible_explica_sin_botones():
    card = con_espera("correo_ilegible")
    texto = cuerpo(card)
    assert "No pude leer el correo" in texto and "no postulo hasta comprobar" in texto
    assert tp.botones(card, datos(plataforma="magneto"), cb) is None


def test_esperas_normales_de_la_cola_sin_botones():
    assert "otra postulación tuya" in cuerpo(con_espera("otra_en_curso"))
    assert "tope de postulaciones de hoy" in cuerpo(con_espera("tope_diario"))
    pausa = con_espera("pausa", cuando="2026-10-17T15:42:00+00:00")
    assert "saldrá hacia las 10:42" in cuerpo(pausa)
    for codigo in ("otra_en_curso", "tope_diario", "pausa"):
        assert tp.botones(con_espera(codigo), datos(plataforma="magneto"), cb) is None


def test_esperando_navegador_tambien_explica_la_causa():
    card = con_espera("sin_latido", fase=tp.ESPERANDO_NAVEGADOR, ultimo="2026-10-17T15:42:00+00:00")
    assert "Tu navegador no responde" in cuerpo(card)
    assert "Se enviará cuando abras" not in cuerpo(card)


def test_sin_espera_la_card_en_cola_conserva_su_texto():
    assert "En cola. Te aviso el resultado." in tp.texto(tp.Card(), datos())
    esperando = tp.texto(tp.Card(fase=tp.ESPERANDO_NAVEGADOR), datos())
    assert "Se enviará cuando abras tu navegador." in esperando


def test_la_espera_solo_se_pinta_en_las_fases_de_cola():
    card = con_espera("sin_sesion", fase=tp.PROGRESO)
    assert "Inicia sesión" not in cuerpo(card, etapa=0)


def test_card_guardada_antes_de_la_espera_carga_igual():
    antigua = '{"mensaje_id": 5, "fase": "en_cola", "vista": "principal", "pregunta": null, '
    antigua += '"motivo": null, "afinidad": null}'
    card = tp.Card.de_texto(antigua)
    assert card.espera is None and card.mensaje_id == 5
    assert "En cola. Te aviso el resultado." in tp.texto(card, datos())
    assert tp.Card.de_texto(con_espera("sin_sesion").a_texto()).espera["codigo"] == "sin_sesion"


def test_cada_causa_del_diagnostico_tiene_texto_sin_motivos_internos():
    assert set(t.ESPERAS) == set(espera.CAUSAS)
    for codigo in espera.CAUSAS:
        texto = cuerpo(con_espera(codigo))
        assert t.ESPERAS[codigo].strip()
        for interno in ("enlace_ingresar", "fuera_del_portal", "sin_sesion:", "{", "}"):
            assert interno not in texto


def test_con_el_bloque_de_conexion_la_cuenta_no_se_explica_dos_veces():
    existente = [[("Confirmar Magneto", "cb:cuenta:magneto:si")]]
    d = datos(plataforma="magneto", botones_conexion=existente, conexion=["🔗 Conexión"])
    for codigo in ("cuenta_por_confirmar", "cuenta_distinta"):
        texto = tp.texto(con_espera(codigo), d)
        assert "Hay una sesión abierta" not in texto and "no es la que me diste" not in texto
        assert "Sale en cuanto resuelvas la cuenta de arriba." in texto


def test_cabecera_con_plataforma_sola_y_sin_plataforma():
    solo_portal = tp.texto(tp.Card(), datos(empresa=None, plataforma="magneto")).split("\n")
    assert solo_portal[:2] == ["<b>Aprendiz &lt;SENA&gt;</b>", "🟢 Magneto"]
    sin_portal = tp.texto(tp.Card(), datos(plataforma=None)).split("\n")
    assert sin_portal[:2] == ["<b>Aprendiz &lt;SENA&gt;</b>", "Euro"]
    nada = tp.texto(tp.Card(), datos(empresa=None, plataforma=None)).split("\n")
    assert nada[:2] == ["<b>Aprendiz &lt;SENA&gt;</b>", ""]


@pytest.mark.parametrize(
    ("motivo", "frase"),
    [
        ("ats_con_cuenta", "pide crear una cuenta"),
        ("captcha", "pidió resolver un captcha"),
        ("oauth", "cuenta de Google, LinkedIn u otro servicio"),
        ("codigo_verificacion", "código de verificación"),
        ("sin_ia", "necesito tu clave de IA"),
        ("documento_faltante", "documento obligatorio"),
        ("nivel_ahorro", "tu nivel de IA es Ahorro"),
    ],
)
def test_respaldo_explica_los_motivos_del_motor_generico(motivo, frase):
    card = tp.Card(fase=tp.RESPALDO, motivo=motivo)
    texto = tp.texto(card, datos())
    assert frase in texto
    assert "_" not in motivo or motivo not in texto  # nunca el código interno
    assert "No puedo postularla sola" in texto


def test_respaldo_nivel_ahorro_sugiere_subir_de_nivel_sin_pedir_clave():
    card = tp.Card(fase=tp.RESPALDO, motivo="nivel_ahorro")
    d = datos()
    assert "/ia nivel" in tp.texto(card, d)
    assert "Configurar IA" not in [b[0] for fila in tp.botones(card, d, cb) for b in fila]


def test_respaldo_sin_ia_ofrece_configurar_la_clave_y_conserva_las_demas_acciones():
    card = tp.Card(fase=tp.RESPALDO, motivo="sin_ia")
    d = datos()
    assert "Con tu clave de IA puedo seguir sola" in tp.texto(card, d)
    botones = tp.botones(card, d, cb)
    assert botones[0][0] == ("Configurar IA", cb("clave", "nueva"))
    assert ("Ver vacante", f"url:{URL}") in [b for fila in botones for b in fila]
    otro = tp.botones(tp.Card(fase=tp.RESPALDO, motivo="captcha"), d, cb)
    assert "Configurar IA" not in [b[0] for fila in otro for b in fila]


def test_ensayada_muestra_donde_habria_pulsado_enviar_y_lo_que_habria_enviado():
    card = tp.Card(fase=tp.ENSAYADA, motivo="boton:Submit application")
    d = datos(
        revision=[{"id": 1, "pregunta": "¿Por qué nosotros?", "respuesta": "Me gusta",
                   "origen": "ia"}],
        ensayo={"trabado": None, "en_plataforma": False},
    )  # fmt: skip
    texto = tp.texto(card, d)
    assert "🧪 Ensayo: no envié nada." in texto
    assert "Habría pulsado «Submit application» para enviar." in texto
    assert "¿Por qué nosotros?" in texto and "<b>Me gusta</b>" in texto
    assert "está en prueba" not in texto
    assert etiquetas(tp.botones(card, d, cb)) == [
        [tp.BOTON_ENVIAR_DE_VERDAD, tp.BOTON_PAQUETE_RESPALDO], ["Ver vacante"],
    ]  # fmt: skip
    assert tp.botones(card, d, cb)[0][0][1] == cb("ens", 7, "real")
    assert tp.botones(card, d, cb)[0][1][1] == cb("ens", 7, "resp")


def test_ensayada_en_un_portal_declarado_aclara_que_llega_hasta_el_boton_de_postular():
    card = tp.Card(fase=tp.ENSAYADA, motivo="paso:enviar")
    texto = tp.texto(card, datos(ensayo={"trabado": None, "en_plataforma": True}))
    assert "En Computrabajo el ensayo llega hasta el botón de postular" in texto
    assert "Computrabajo está en prueba" in texto


@pytest.mark.parametrize(
    ("trabado", "frase"),
    [
        ("pantalla 3: no apareció el botón", "Se trabaría en la pantalla 3: no apareció el botón."),
        ("antes de la primera pantalla: sin formulario",
         "Se trabaría antes de la primera pantalla"),
    ],
)  # fmt: skip
def test_ensayada_trabada_dice_la_pantalla_y_el_motivo_y_no_ofrece_enviar(trabado, frase):
    card = tp.Card(fase=tp.ENSAYADA, motivo="x")
    d = datos(ensayo={"trabado": trabado, "en_plataforma": False})
    assert frase in tp.texto(card, d)
    assert etiquetas(tp.botones(card, d, cb)) == [[tp.BOTON_PAQUETE_RESPALDO], ["Ver vacante"]]
