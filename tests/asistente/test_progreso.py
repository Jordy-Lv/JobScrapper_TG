from buscador_vacantes.asistente import progreso


def test_etapas_hechas_actual_y_pendientes():
    lineas = progreso.texto("Aprendiz <SENA>", "Euro", 1, 2).split("\n")
    assert lineas[0] == "<b>Aprendiz &lt;SENA&gt;</b>" and lineas[1] == "Euro"
    assert lineas[3] == "✓ Abriendo la oferta"
    assert lineas[4] == "⠹ <b>Preparando tu hoja de vida…</b>"
    assert lineas[5].startswith("<i>· ") and lineas[6].startswith("<i>· ")


def test_sin_empresa_y_el_cuadro_da_la_vuelta():
    assert progreso.texto("X", None, 0, 0).split("\n")[1] == ""
    assert progreso.texto("X", None, 0, 10) == progreso.texto("X", None, 0, 0)


def test_pasos_de_la_extension_a_etapas():
    assert progreso.etapa_de_paso("abrir") == 0
    assert progreso.etapa_de_paso("cv_subir") == 1
    assert progreso.etapa_de_paso("llenado") == 2
    assert progreso.etapa_de_paso("envio_pulsado") == 3
    assert progreso.etapa_de_paso("cv_adjunto") is None
