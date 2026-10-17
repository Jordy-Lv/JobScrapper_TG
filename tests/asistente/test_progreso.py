from buscador_vacantes.asistente import progreso


def test_etapas_hechas_actual_y_pendientes():
    lineas = progreso.texto("Aprendiz <SENA>", "Euro", 1, 2).split("\n")
    assert lineas[0] == "<b>Aprendiz &lt;SENA&gt;</b>" and lineas[1] == "Euro"
    assert "%" in lineas[3] and lineas[4] == ""
    assert lineas[5] == "✓ Abriendo la oferta"
    assert lineas[6] == "⠹ <b>Preparando tu hoja de vida…</b>"
    assert lineas[7].startswith("<i>· ") and lineas[8].startswith("<i>· ")


def test_sin_empresa_y_el_cuadro_da_la_vuelta():
    assert progreso.texto("X", None, 0, 0).split("\n")[1] == ""
    assert progreso.texto("X", None, 0, 10) == progreso.texto("X", None, 0, 0)


def test_pasos_de_la_extension_a_etapas():
    assert progreso.etapa_de_paso("abrir") == 0
    assert progreso.etapa_de_paso("cv_subir") == 1
    assert progreso.etapa_de_paso("llenado") == 2
    assert progreso.etapa_de_paso("envio_pulsado") == 3
    assert progreso.etapa_de_paso("cv_adjunto") is None


def test_barra_en_los_bordes_y_con_bloque_parcial():
    assert progreso.barra(0, 4) == "░░░░"
    assert progreso.barra(100, 4) == "████"
    assert progreso.barra(50, 4) == "██░░"
    assert progreso.barra(62.5, 4) == "██▌░"  # 5 octavos: 2 llenos y 4/8 del tercero
    assert progreso.barra(-5, 4) == "░░░░" and progreso.barra(250, 4) == "████"


def test_la_barra_siempre_mide_lo_mismo():
    for avance in range(0, 101):
        assert len(progreso.barra(avance)) == progreso.ANCHO_BARRA


def test_el_porcentaje_nunca_baja_ni_pasa_de_99():
    anterior = -1
    for etapa in range(len(progreso.ETAPAS)):
        for segundos in (0, 3, 9, 30, 600):
            actual = progreso.porcentaje(etapa, segundos)
            assert anterior <= actual <= 99
            anterior = actual
    assert anterior == 97


def test_etapa_lenta_no_completa_la_etapa_y_el_restante_es_1s():
    assert progreso.porcentaje(0, 600) == 22
    ultima = len(progreso.ETAPAS) - 1
    assert progreso.restante(ultima, 600) == 1
    assert progreso.linea_barra(ultima, 600).endswith("~1 s")


def test_el_restante_baja_con_el_tiempo_y_con_las_etapas():
    assert progreso.restante(0, 0) == 40
    assert progreso.restante(0, 5) == 35
    assert progreso.restante(2, 0) == 20
