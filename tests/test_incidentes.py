from datetime import UTC, datetime, timedelta

import pytest

from config import cargar_configuracion
from estado import Estado, a_texto
from incidentes import Detector

T0 = datetime(2026, 10, 3, 10, 0, tzinfo=UTC)


@pytest.fixture
def estado():
    e = Estado.abrir(":memory:")
    yield e
    e.cerrar()


@pytest.fixture
def detector(estado):
    return Detector(estado, cargar_configuracion().incidentes)


def corrida(estado, ts, intentos, sin_red=False):
    """Inserta una corrida con sus intentos: (fuente, status, tipo_error, items, desafio)."""
    with estado.transaccion() as cx:
        corrida_id = cx.execute(
            "INSERT INTO corridas(inicio, modo, sin_red) VALUES (?, 'normal', ?)",
            (a_texto(ts), int(sin_red)),
        ).lastrowid
        for fuente, status, tipo_error, items, *resto in intentos:
            cx.execute(
                "INSERT INTO intentos(ts, corrida_id, fuente, status, items, tipo_error, desafio) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (a_texto(ts), corrida_id, fuente, status, items, tipo_error,
                 int(resto[0]) if resto else 0),
            )  # fmt: skip
    return corrida_id


def claves(incidentes):
    return [i.clave for i in incidentes]


def test_cambio_html_abre_no_repite_y_cierra(estado, detector):
    c1 = corrida(estado, T0, [("computrabajo", 200, "cambio_html", 0)])
    r1 = detector.evaluar(c1, T0, ["computrabajo"])
    assert claves(r1.nuevos) == ["computrabajo:cambio_html"]
    assert r1.nuevos[0].dato

    c2 = corrida(estado, T0 + timedelta(minutes=30), [("computrabajo", 200, "cambio_html", 0)])
    assert detector.evaluar(c2, T0 + timedelta(minutes=30), ["computrabajo"]).vacio

    c3 = corrida(estado, T0 + timedelta(hours=1), [("computrabajo", 200, None, 20)])
    r3 = detector.evaluar(c3, T0 + timedelta(hours=1), ["computrabajo"])
    assert claves(r3.recuperados) == ["computrabajo:cambio_html"]
    assert r3.recuperados[0].cerrado_en == T0 + timedelta(hours=1)
    assert detector.abiertos() == {}


def test_error_de_servidor_en_3_corridas_seguidas(estado, detector):
    for n in range(3):
        ts = T0 + timedelta(minutes=30 * n)
        c = corrida(estado, ts, [("elempleo", 503, "servidor", 0)])
        resultado = detector.evaluar(c, ts, ["elempleo"])
        if n < 2:
            assert resultado.nuevos == []
    assert claves(resultado.nuevos) == ["elempleo:error_servidor"]


def test_timeouts_tambien_cuentan_y_un_exito_corta_la_racha(estado, detector):
    corrida(estado, T0, [("magneto", None, "timeout", 0)])
    corrida(estado, T0 + timedelta(minutes=30), [("magneto", 200, None, 5)])
    c = corrida(estado, T0 + timedelta(hours=1), [("magneto", 503, "servidor", 0)])
    assert detector.evaluar(c, T0 + timedelta(hours=1), ["magneto"]).nuevos == []


def test_bloqueo_en_2_corridas_seguidas(estado, detector):
    c1 = corrida(estado, T0, [("linkedin", 429, "bloqueo", 0)])
    assert detector.evaluar(c1, T0, ["linkedin"]).nuevos == []
    # Una corrida sin red en medio no rompe la racha
    corrida(estado, T0 + timedelta(hours=1), [("linkedin", None, "conexion", 0)], sin_red=True)
    c2 = corrida(estado, T0 + timedelta(hours=2), [("linkedin", 429, "bloqueo", 0)])
    resultado = detector.evaluar(c2, T0 + timedelta(hours=2), ["linkedin"])
    assert claves(resultado.nuevos) == ["linkedin:bloqueo"]


def test_bloqueo_por_cooldown_escalado(estado, detector):
    with estado.transaccion() as cx:
        cx.execute(
            "INSERT INTO fuentes_estado(fuente, cooldown_hasta, escalon, fallos_consecutivos) "
            "VALUES ('linkedin', ?, 1, 2)",
            (a_texto(T0 + timedelta(hours=6)),),
        )
    c = corrida(estado, T0, [("linkedin", 999, "bloqueo", 0)])
    resultado = detector.evaluar(c, T0, ["linkedin"])
    assert claves(resultado.nuevos) == ["linkedin:bloqueo"]
    assert "6 h" in resultado.nuevos[0].dato


def test_bloqueo_sigue_abierto_en_cooldown_y_se_cierra_con_exito(estado, detector):
    corrida(estado, T0, [("linkedin", 429, "bloqueo", 0)])
    c = corrida(estado, T0 + timedelta(hours=2), [("linkedin", 429, "bloqueo", 0)])
    detector.evaluar(c, T0 + timedelta(hours=2), ["linkedin"])
    # En cooldown la fuente no se consulta: el incidente sigue abierto
    c = corrida(estado, T0 + timedelta(hours=3), [("magneto", 200, None, 5)])
    assert detector.evaluar(c, T0 + timedelta(hours=3), ["linkedin", "magneto"]).vacio
    c = corrida(estado, T0 + timedelta(hours=8), [("linkedin", 200, None, 10)])
    resultado = detector.evaluar(c, T0 + timedelta(hours=8), ["linkedin"])
    assert claves(resultado.recuperados) == ["linkedin:bloqueo"]


def test_captcha(estado, detector):
    c = corrida(estado, T0, [("computrabajo", 200, "captcha", 0, True)])
    assert claves(detector.evaluar(c, T0, ["computrabajo"]).nuevos) == ["computrabajo:captcha"]


def test_sin_resultados_en_24h(estado, detector):
    corrida(estado, T0 - timedelta(days=3), [("magneto", 200, None, 25)])
    corrida(estado, T0 - timedelta(hours=10), [("magneto", 200, None, 0)])
    c = corrida(estado, T0, [("magneto", 200, None, 0)])
    assert claves(detector.evaluar(c, T0, ["magneto"]).nuevos) == ["magneto:sin_resultados"]
    c = corrida(estado, T0 + timedelta(minutes=30), [("magneto", 200, None, 4)])
    resultado = detector.evaluar(c, T0 + timedelta(minutes=30), ["magneto"])
    assert claves(resultado.recuperados) == ["magneto:sin_resultados"]


def test_fuente_nueva_sin_historial_no_abre_sin_resultados(estado, detector):
    c = corrida(estado, T0, [("magneto", 200, None, 0)])
    assert detector.evaluar(c, T0, ["magneto"]).vacio


def test_caida_de_volumen(estado, detector):
    for dia in range(2, 10):
        corrida(estado, T0 - timedelta(days=dia), [("elempleo", 200, None, 70)])
    c = corrida(estado, T0, [("elempleo", 200, None, 10)])
    resultado = detector.evaluar(c, T0, ["elempleo"])
    assert claves(resultado.nuevos) == ["elempleo:caida_volumen"]
    assert "10 vacantes" in resultado.nuevos[0].dato


def test_volumen_normal_no_abre(estado, detector):
    for dia in range(2, 10):
        corrida(estado, T0 - timedelta(days=dia), [("elempleo", 200, None, 70)])
    c = corrida(estado, T0, [("elempleo", 200, None, 60)])
    assert detector.evaluar(c, T0, ["elempleo"]).vacio


def test_fallo_de_envio(estado, detector):
    c = corrida(estado, T0, [])
    resultado = detector.evaluar(c, T0, [], rechazos_envio=["Bad Request: can't parse entities"])
    assert claves(resultado.nuevos) == ["telegram:fallo_envio"]
    c = corrida(estado, T0 + timedelta(minutes=30), [])
    resultado = detector.evaluar(c, T0 + timedelta(minutes=30), [], envio_exitoso=True)
    assert claves(resultado.recuperados) == ["telegram:fallo_envio"]


def test_sin_red_solo_abre_un_incidente(estado, detector):
    intentos = [("linkedin", None, "conexion", 0), ("magneto", None, "conexion", 0)]
    c = corrida(estado, T0, intentos, sin_red=True)
    resultado = detector.evaluar(c, T0, ["linkedin", "magneto"], sin_red=True)
    assert claves(resultado.nuevos) == ["red:sin_conexion"]
    c = corrida(estado, T0 + timedelta(minutes=30), intentos, sin_red=True)
    assert detector.evaluar(c, T0 + timedelta(minutes=30), ["linkedin"], sin_red=True).vacio
    # Vuelve la red: se cierra con apertura y cierre
    c = corrida(estado, T0 + timedelta(hours=1, minutes=40), [("linkedin", 200, None, 10)])
    resultado = detector.evaluar(c, T0 + timedelta(hours=1, minutes=40), ["linkedin"])
    assert claves(resultado.recuperados) == ["red:sin_conexion"]
    recuperado = resultado.recuperados[0]
    assert recuperado.cerrado_en - recuperado.abierto_desde == timedelta(hours=1, minutes=40)
    assert resultado.nuevos == []


def test_recordatorio_cada_24h(estado, detector):
    c = corrida(estado, T0, [("computrabajo", 200, "cambio_html", 0)])
    [incidente] = detector.evaluar(c, T0, ["computrabajo"]).nuevos
    detector.marcar_reportado(incidente, T0)
    c = corrida(estado, T0 + timedelta(hours=23), [("computrabajo", 200, "cambio_html", 0)])
    assert detector.evaluar(c, T0 + timedelta(hours=23), ["computrabajo"]).recordatorios == []
    c = corrida(estado, T0 + timedelta(hours=24), [("computrabajo", 200, "cambio_html", 0)])
    resultado = detector.evaluar(c, T0 + timedelta(hours=24), ["computrabajo"])
    assert claves(resultado.recordatorios) == ["computrabajo:cambio_html"]
    detector.marcar_reportado(resultado.recordatorios[0], T0 + timedelta(hours=24))
    c = corrida(estado, T0 + timedelta(hours=25), [("computrabajo", 200, "cambio_html", 0)])
    assert detector.evaluar(c, T0 + timedelta(hours=25), ["computrabajo"]).recordatorios == []


def test_bloqueo_no_es_sin_resultados(estado, detector):
    corrida(estado, T0 - timedelta(days=3), [("linkedin", 200, None, 25)])
    corrida(estado, T0 - timedelta(hours=10), [("linkedin", 429, "bloqueo", 0)])
    c = corrida(estado, T0, [("linkedin", 429, "bloqueo", 0)])
    nuevos = claves(detector.evaluar(c, T0, ["linkedin"]).nuevos)
    assert "linkedin:sin_resultados" not in nuevos
    assert "linkedin:bloqueo" in nuevos


def test_dry_run_no_cuenta_para_las_rachas(estado, detector):
    with estado.transaccion() as cx:
        corrida_id = cx.execute(
            "INSERT INTO corridas(inicio, modo) VALUES (?, 'dry-run')", (a_texto(T0),)
        ).lastrowid
        cx.execute(
            "INSERT INTO intentos(ts, corrida_id, fuente, status, tipo_error, items) "
            "VALUES (?, ?, 'linkedin', 429, 'bloqueo', 0)",
            (a_texto(T0), corrida_id),
        )
    c = corrida(estado, T0 + timedelta(hours=2), [("linkedin", 429, "bloqueo", 0)])
    assert detector.evaluar(c, T0 + timedelta(hours=2), ["linkedin"]).nuevos == []
