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
        "· Inicia sesión en Computrabajo, Magneto y elempleo en ese navegador.",
    ]


def test_una_linea_por_portal_segun_su_estado():
    tj = Tarjeta(navegador=True)
    tj.poner_cuenta("computrabajo", tarjeta.CONFIRMADA, "ana@gmail.com")
    tj.poner_cuenta("magneto", tarjeta.POR_CONFIRMAR, "ana<2>@gmail.com")
    lineas = tarjeta.texto(tj).split("\n")
    assert "✓ 🔵 Computrabajo · ana@gmail.com" in lineas
    assert any(
        x.startswith("❓ <b>🟢 Magneto</b>") and "ana&lt;2&gt;@gmail.com" in x for x in lineas
    )
    assert not any("Inicia sesión en Computrabajo, Magneto" in x for x in lineas)


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
            ("Confirmar Computrabajo", "cb:cuenta:computrabajo:si"),
            ("Cancelar", "cb:cuenta:computrabajo:no"),
        ]
    ]
    tj.poner_cuenta("computrabajo", tarjeta.DISTINTA, "a@b.co", "l***@hotmail.com")
    assert tarjeta.botones(tj, cb)[0][0] == (
        "Es mi cuenta nueva",
        "cb:cuenta:computrabajo:nueva",
    )
    tj.poner_cuenta("computrabajo", tarjeta.CONFIRMADA)
    assert tarjeta.botones(tj, cb) is None


def test_el_cierre_del_alta_va_en_un_mensaje_aparte():
    tj = Tarjeta(navegador=True, listo=True)
    assert t.ALTA_LISTA not in tarjeta.texto(tj)
    assert tarjeta.lineas(tj) == tarjeta.texto(tj).split("\n")


def test_el_estado_se_guarda_y_se_lee_como_texto():
    tj = Tarjeta(mensaje_id=7, navegador=True, pid=3)
    tj.poner_cuenta("magneto", tarjeta.REVISANDO)
    assert Tarjeta.de_texto(tj.a_texto()) == tj
    assert Tarjeta.de_texto("") is None and Tarjeta.de_texto(None) is None


def _con_dos_portales() -> Tarjeta:
    tj = Tarjeta(navegador=True)
    tj.poner_cuenta("computrabajo", tarjeta.POR_CONFIRMAR, "ana@gmail.com")
    tj.poner_cuenta("magneto", tarjeta.CONFIRMADA, "ana@magneto.co")
    return tj


def test_solo_muestra_el_portal_de_la_vacante():
    tj = _con_dos_portales()
    assert tarjeta.lineas(tj, solo="magneto") == [
        "🔗 <b>Conexión con tus portales</b>",
        "✓ Navegador vinculado",
        "✓ 🟢 Magneto · ana@magneto.co",
    ]
    assert tarjeta.botones(tj, cb, solo="magneto") is None
    assert tarjeta.botones(tj, cb, solo="computrabajo") == [
        [
            ("Confirmar Computrabajo", "cb:cuenta:computrabajo:si"),
            ("Cancelar", "cb:cuenta:computrabajo:no"),
        ]
    ]


def test_solo_sin_cuenta_del_portal_pide_iniciar_sesion_en_el():
    tj = Tarjeta(navegador=True)
    tj.poner_cuenta("computrabajo", tarjeta.CONFIRMADA, "ana@gmail.com")
    lineas = tarjeta.lineas(tj, solo="magneto")
    assert lineas[-1] == "· 🟢 Magneto: inicia sesión con tu cuenta en ese navegador"
    assert not any("Computrabajo" in x for x in lineas)
    assert tarjeta.botones(tj, cb, solo="magneto") is None


def test_excepto_muestra_los_demas_portales():
    tj = _con_dos_portales()
    lineas = tarjeta.lineas(tj, excepto="magneto")
    assert not any("Magneto" in x for x in lineas)
    assert any(x.startswith("❓ <b>🔵 Computrabajo</b>") for x in lineas)
    assert tarjeta.botones(tj, cb, excepto="magneto") == tarjeta.botones(
        tj, cb, solo="computrabajo"
    )
    assert tarjeta.texto(tj, excepto="magneto") == "\n".join(lineas)


def test_sin_filtro_todas_las_cuentas_como_antes():
    tj = _con_dos_portales()
    assert tarjeta.lineas(tj) == [
        "🔗 <b>Conexión con tus portales</b>",
        "✓ Navegador vinculado",
        "❓ <b>🔵 Computrabajo</b>: sesión iniciada con <b>ana@gmail.com</b>. ¿Es tu cuenta?",
        "✓ 🟢 Magneto · ana@magneto.co",
    ]
    assert len(tarjeta.botones(tj, cb)) == 1


def test_el_paso_5_solo_vincula_el_navegador_y_el_6_pide_iniciar_sesion():
    assert "sesión" not in t.NAVEGADOR and "Paso 5 de 6" in t.NAVEGADOR
    assert "Paso 6 de 6" in t.PLATAFORMAS and "Inicia sesión" in t.PLATAFORMAS


def _en_el_paso(esperada: str | None) -> Tarjeta:
    tj = Tarjeta(navegador=True, paso=True, esperada=esperada)
    for plataforma in ("computrabajo", "magneto", "elempleo"):
        tj.poner_cuenta(plataforma, tarjeta.PENDIENTE)
    return tj


def test_el_paso_lista_las_plataformas_con_la_esperada_resaltada_y_las_demas_opcionales():
    lineas = tarjeta.lineas(_en_el_paso("magneto"))
    assert lineas[1:] == [
        "✓ Navegador vinculado",
        "· 🔵 Computrabajo (opcional): inicia sesión con tu cuenta en ese navegador",
        "👉 <b>🟢 Magneto</b>: inicia sesión con tu cuenta en ese navegador",
        "· 🩵 elempleo (opcional): inicia sesión con tu cuenta en ese navegador",
    ]
    texto = tarjeta.texto(_en_el_paso("magneto"))
    assert texto.startswith(t.PLATAFORMAS) and "Tu vacante es de <b>Magneto</b>" in texto


def test_el_paso_sin_vacante_no_marca_ninguna_como_opcional():
    tj = _en_el_paso(None)
    assert not any("opcional" in x for x in tarjeta.lineas(tj))
    assert t.PLATAFORMAS_SIN_VACANTE in tarjeta.texto(tj)


def test_el_paso_ofrece_omitir_ademas_de_los_botones_de_cuenta():
    tj = _en_el_paso("magneto")
    assert tarjeta.botones(tj, cb) == [[("Omitir por ahora", "cb:omitir_plat")]]
    tj.poner_cuenta("magneto", tarjeta.POR_CONFIRMAR, "ana@gmail.com")
    filas = tarjeta.botones(tj, cb)
    assert filas[0][0] == ("Confirmar Magneto", "cb:cuenta:magneto:si")
    assert filas[-1] == [("Omitir por ahora", "cb:omitir_plat")]


def test_fuera_del_paso_no_hay_explicacion_ni_omitir():
    tj = _en_el_paso("magneto")
    tj.paso = False
    assert t.PLATAFORMAS not in tarjeta.texto(tj)
    assert tarjeta.botones(tj, cb) is None
    # el filtro por portal de la card tampoco lleva el paso ni el botón
    tj.paso = True
    assert tarjeta.botones(tj, cb, solo="magneto") is None
    assert t.PLATAFORMAS not in tarjeta.texto(tj, solo="magneto")


def test_la_linea_de_cuenta_lleva_el_emoji_y_el_boton_no():
    tj = Tarjeta(navegador=True)
    tj.poner_cuenta("elempleo", tarjeta.POR_CONFIRMAR, "ana@gmail.com")
    assert any(x.startswith("❓ <b>🩵 elempleo</b>") for x in tarjeta.lineas(tj))
    assert tarjeta.botones(tj, cb)[0][0][0] == "Confirmar elempleo"


def test_nombre_con_emoji_de_cada_plataforma():
    assert t.nombre_con_emoji("computrabajo") == "🔵 Computrabajo"
    assert t.nombre_con_emoji("magneto") == "🟢 Magneto"
    assert t.nombre_con_emoji("elempleo") == "🩵 elempleo"


def test_nombre_con_emoji_sin_emoji_registrado_o_sin_plataforma():
    assert t.nombre_con_emoji("otra") == "otra"
    assert t.nombre_con_emoji(None) == "" and t.nombre_con_emoji("") == ""


def test_linea_empresa_con_emoji_de_la_plataforma():
    assert t.linea_empresa("Maaji", "magneto") == "Maaji · 🟢 Magneto"
    assert t.linea_empresa(None, "computrabajo") == "🔵 Computrabajo"
    assert t.linea_empresa("Maaji", "otra") == "Maaji · otra"
    assert t.linea_empresa("Maaji", None) == "Maaji"
    assert t.linea_empresa(None, None) is None
