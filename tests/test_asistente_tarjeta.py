from buscador_vacantes.asistente import tarjeta
from buscador_vacantes.asistente import textos as t
from buscador_vacantes.asistente.tarjeta import Tarjeta


def cb(*partes):
    return "cb:" + ":".join(str(p) for p in partes)


def test_con_el_navegador_vinculado_pide_iniciar_sesion_en_los_portales():
    texto = tarjeta.texto(Tarjeta(navegador=True))
    assert texto.split("\n") == [
        "🔗 <b>Conexión con tus portales</b>",
        "✓ Navegador vinculado",
        "· Inicia sesión en Computrabajo y Magneto en ese navegador.",
    ]


def test_una_linea_por_portal_segun_su_estado():
    tj = Tarjeta(navegador=True)
    tj.poner_cuenta("computrabajo", tarjeta.CONFIRMADA, "ana@gmail.com")
    tj.poner_cuenta("magneto", tarjeta.POR_CONFIRMAR, "ana<2>@gmail.com")
    lineas = tarjeta.texto(tj).split("\n")
    assert "✓ Computrabajo · ana@gmail.com" in lineas
    assert any(x.startswith("❓ <b>Magneto</b>") and "ana&lt;2&gt;@gmail.com" in x for x in lineas)
    assert not any("Inicia sesión en Computrabajo y Magneto" in x for x in lineas)


def test_confirmar_conserva_el_correo_ya_mostrado():
    tj = Tarjeta()
    tj.poner_cuenta("magneto", tarjeta.POR_CONFIRMAR, "ana@gmail.com")
    tj.poner_cuenta("magneto", tarjeta.CONFIRMADA)
    assert tj.cuentas["magneto"]["correo"] == "ana@gmail.com"


def test_botones_solo_mientras_hay_una_cuenta_por_resolver():
    tj = Tarjeta()
    assert tarjeta.botones(tj, cb) is None
    tj.poner_cuenta("computrabajo", tarjeta.POR_CONFIRMAR, "a@b.co")
    assert tarjeta.botones(tj, cb) == [
        [
            ("✅ Confirmar Computrabajo", "cb:cuenta:computrabajo:si"),
            ("Cancelar", "cb:cuenta:computrabajo:no"),
        ]
    ]
    tj.poner_cuenta("computrabajo", tarjeta.DISTINTA, "a@b.co", "l***@hotmail.com")
    assert tarjeta.botones(tj, cb)[0][0] == (
        "Es mi cuenta nueva, usarla",
        "cb:cuenta:computrabajo:nueva",
    )
    tj.poner_cuenta("computrabajo", tarjeta.CONFIRMADA)
    assert tarjeta.botones(tj, cb) is None


def test_cierre_del_alta_y_vacante_en_cola_o_con_etapas():
    tj = Tarjeta(navegador=True, listo=True)
    assert t.ALTA_LISTA not in tarjeta.texto(tj)  # el cierre va en un mensaje aparte
    en_cola = tarjeta.texto(tj, ("Aprendiz <SENA>", "Euro"))
    assert "Ya puedes tocar" not in en_cola
    assert "<b>Aprendiz &lt;SENA&gt;</b>" in en_cola and "⏳ En cola" in en_cola
    avance = tarjeta.texto(tj, ("Aprendiz", None), etapa=1, cuadro=0)
    assert "✓ Abriendo la oferta" in avance and "<b>Preparando tu hoja de vida…</b>" in avance


def test_el_estado_se_guarda_y_se_lee_como_texto():
    tj = Tarjeta(mensaje_id=7, navegador=True, pid=3)
    tj.poner_cuenta("magneto", tarjeta.REVISANDO)
    assert Tarjeta.de_texto(tj.a_texto()) == tj
    assert Tarjeta.de_texto("") is None and Tarjeta.de_texto(None) is None
