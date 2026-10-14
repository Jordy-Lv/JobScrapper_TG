import pytest

from buscador_vacantes.asistente import preguntas_tarjeta as pt
from buscador_vacantes.asistente import textos as t


def cb(*partes):
    return "cb:" + ":".join(str(p) for p in partes)


def indice(clave):
    return next(i for i, it in enumerate(t.CUESTIONARIO) if it.clave == clave)


def test_progreso_faltan_y_ultima():
    est = pt.Preguntas(indices=[3, 5, 6], actual=3)
    assert pt.progreso(est) == "<b>Faltan 3</b>\n"
    est.actual = 5
    assert pt.progreso(est) == "<b>Faltan 2</b>\n"
    est.actual = 6
    assert pt.progreso(est) == "<b>Última</b>\n"


def test_progreso_al_editar_y_fuera_del_bloque():
    assert pt.progreso(pt.Preguntas(indices=[3], actual=3, editando=True)) == "<b>Editando</b>\n"
    assert pt.progreso(pt.Preguntas(indices=[3], actual=9)) == ""


def test_siguiente_dentro_del_bloque():
    est = pt.Preguntas(indices=[3, 5], actual=3)
    assert est.siguiente() == 5
    est.actual = 5
    assert est.siguiente() is None


def test_botones_de_pregunta_con_rango_otro_sugerido_y_omitir():
    i = indice("salario")
    item = t.CUESTIONARIO[i]
    est = pt.Preguntas(indices=[i], actual=i)
    botones = pt.botones_pregunta(
        est, cb, opciones=item.opciones, por_fila=item.por_fila, otro=item.otro,
        sugerido="Cali", opcional=True,
    )  # fmt: skip
    etiquetas = [b[0] for fila in botones for b in fila]
    assert etiquetas == [*item.opciones, "✏️ Otro valor", "Usar Cali", "Omitir"]
    assert botones[0][0][1] == cb("cuest", i, 0)
    assert botones[-1][0][1] == cb("cuest", i, "omitir")


def test_botones_al_editar_incluyen_volver_al_resumen():
    est = pt.Preguntas(indices=[1], actual=1, editando=True)
    botones = pt.botones_pregunta(
        est, cb, opciones=(), por_fila=4, otro="", sugerido=None, opcional=False
    )
    assert botones == [[("↩️ Volver al resumen", cb("cuest", "volver"))]]


def test_texto_otro_pide_el_valor_dentro_de_la_tarjeta():
    i = indice("salario")
    est = pt.Preguntas(indices=[i], actual=i)
    texto = pt.texto_otro(est, t.CUESTIONARIO[i].pregunta)
    assert "Escribe el valor" in texto and texto.startswith("<b>Última</b>")
    assert pt.botones_otro(cb) == [[("↩️ Volver", cb("cuest", "volver"))]]


def test_aviso_de_formato_se_pinta_en_la_tarjeta():
    est = pt.Preguntas(indices=[5], actual=5, aviso=pt.AVISO_NUMERO)
    assert "⚠️ Escribe solo el número" in pt.texto_otro(est, "Salario")


def test_resumen_con_respuestas_omitidas_y_salario_formateado():
    indices = [indice("documento"), indice("salario"), indice("horario")]
    est = pt.Preguntas(indices=indices, actual=indices[0])
    texto = pt.texto_resumen(est, {"salario": "2000000", "horario": "Flexible"})
    assert "• Documento: —" in texto
    assert "• Aspiración salarial: $2.000.000" in texto
    assert "• Horario: Flexible" in texto


def test_el_resumen_recorta_respuestas_largas_y_escapa_html():
    i = indice("nombre")
    est = pt.Preguntas(indices=[i], actual=i)
    texto = pt.texto_resumen(est, {"nombre": "<b>" + "x" * 500})
    assert "&lt;b&gt;" in texto and "…" in texto and len(texto) < 200


def test_resumen_de_todo_el_cuestionario_cabe_en_telegram():
    indices = list(range(len(t.CUESTIONARIO)))
    est = pt.Preguntas(indices=indices, actual=0)
    respuestas = {it.clave: "z" * 500 for it in t.CUESTIONARIO}
    assert len(pt.texto_resumen(est, respuestas)) < 4096


def test_botones_de_resumen_y_lista():
    assert [b[1] for b in pt.botones_resumen(cb)[0]] == [cb("cuest", "ok"), cb("cuest", "editar")]
    est = pt.Preguntas(indices=[3, 5], actual=3)
    lista = pt.botones_lista(est, cb)
    assert [f[0][1] for f in lista] == [cb("cuest", "campo", 3), cb("cuest", "campo", 5),
                                        cb("cuest", "volver")]  # fmt: skip
    assert lista[0][0][0] == "Documento"


def test_callbacks_caben_en_el_limite_de_telegram():
    for i in range(len(t.CUESTIONARIO)):
        assert len(cb("cuest", "campo", i).encode()) <= 64
        assert len(cb("cuest", i, "omitir").encode()) <= 64


def test_ida_y_vuelta_del_estado():
    est = pt.Preguntas(mensaje_id=7, fase=pt.RESUMEN, indices=[3, 5], actual=5, editando=True)
    assert pt.Preguntas.de_texto(est.a_texto()) == est
    assert pt.Preguntas.de_texto("") is None
    assert pt.Preguntas.de_texto(None) is None


@pytest.mark.parametrize("clave", [it.clave for it in t.CUESTIONARIO])
def test_todas_las_preguntas_tienen_etiqueta(clave):
    assert clave in pt.ETIQUETAS
