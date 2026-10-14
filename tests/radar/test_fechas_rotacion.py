from collections import Counter
from datetime import datetime, timedelta

import pytest

from buscador_vacantes.comun.estado import Estado
from buscador_vacantes.comun.fechas import ZONA, desde_epoch, fecha_relativa, interpretar_fecha
from buscador_vacantes.radar import rotacion

AHORA = datetime(2026, 10, 3, 15, 30, tzinfo=ZONA)


@pytest.mark.parametrize(
    ("texto", "esperada"),
    [
        ("Hace 2 días", datetime(2026, 10, 1).date()),
        ("Publicado hace 3 horas", AHORA.date()),
        ("hace 1 día", datetime(2026, 10, 2).date()),
        ("Hace un día", datetime(2026, 10, 2).date()),
        ("hace 2 semanas", datetime(2026, 9, 19).date()),
        ("Hace más de 30 días", datetime(2026, 9, 3).date()),
        ("hace 45 minutos", AHORA.date()),
        ("Hoy", AHORA.date()),
        ("Ayer", datetime(2026, 10, 2).date()),
        ("Actualizada ayer", datetime(2026, 10, 2).date()),
        ("2026-10-01", datetime(2026, 10, 1).date()),
        ("01/10/2026", datetime(2026, 10, 1).date()),
        ("1 de octubre de 2026", datetime(2026, 10, 1).date()),
        ("30 sep", datetime(2026, 9, 30).date()),
        ("Publicada el 28 de septiembre", datetime(2026, 9, 28).date()),
    ],
)
def test_formatos_de_fecha(texto, esperada):
    fecha = interpretar_fecha(texto, AHORA)
    assert fecha is not None
    assert fecha.tzinfo is not None
    assert fecha.astimezone(ZONA).date() == esperada


def test_hora_relativa_exacta():
    assert interpretar_fecha("hace 3 horas", AHORA) == AHORA - timedelta(hours=3)


def test_iso_con_hora_utc():
    fecha = interpretar_fecha("2026-10-03T02:00:00Z", AHORA)
    assert fecha == datetime(2026, 10, 2, 21, 0, tzinfo=ZONA)


def test_mes_sin_anio_en_enero_es_del_anio_anterior():
    enero = datetime(2027, 1, 2, 9, 0, tzinfo=ZONA)
    assert interpretar_fecha("28 dic", enero).date() == datetime(2026, 12, 28).date()


@pytest.mark.parametrize("texto", [None, "", "Sin fecha", "31/02/2026", "Urgente"])
def test_no_reconocida(texto):
    assert interpretar_fecha(texto, AHORA) is None


def test_epoch():
    assert desde_epoch(1759500000).tzinfo == ZONA
    assert desde_epoch(None) is None


def test_fecha_relativa():
    assert fecha_relativa(AHORA - timedelta(hours=2), AHORA) == "hoy"
    assert fecha_relativa(datetime(2026, 10, 2, 23, 59, tzinfo=ZONA), AHORA) == "ayer"
    assert fecha_relativa(datetime(2026, 9, 28, 8, 0, tzinfo=ZONA), AHORA) == "hace 5 días"
    assert fecha_relativa(None, AHORA) is None


@pytest.fixture
def estado():
    e = Estado.abrir(":memory:")
    yield e
    e.cerrar()


NUCLEO = [f"n{i}" for i in range(8)]
COLA = [f"c{i}" for i in range(90)]


def correr(estado, fuente="linkedin", presupuesto=3, reservado=1, nucleo=NUCLEO, cola=COLA):
    lote = rotacion.calcular_lote(estado, fuente, nucleo, cola, presupuesto, reservado)
    rotacion.avanzar_lote(estado, fuente, lote, len(nucleo), len(cola))
    return lote


def test_nucleo_frecuente(estado):
    corridas = [correr(estado) for _ in range(45)]
    assert all(len(lote) == 3 for lote in corridas)
    nucleo = [c.keyword for lote in corridas for c in lote if c.grupo == rotacion.NUCLEO]
    # Cada consulta núcleo se repite cada 8 corridas
    assert nucleo[:16] == NUCLEO + NUCLEO
    cola = [c.keyword for lote in corridas for c in lote if c.grupo == rotacion.COLA_LARGA]
    # La cola larga completa se recorre en 45 corridas
    assert Counter(cola) == Counter(COLA)


def test_avance_de_la_rotacion(estado):
    with estado.transaccion() as cx:
        cx.execute("INSERT INTO rotacion VALUES ('linkedin', 'cola_larga', 4)")
    lote = correr(estado)
    assert [c.keyword for c in lote if c.grupo == rotacion.COLA_LARGA] == ["c4", "c5"]
    assert rotacion.obtener_indice(estado, "linkedin", rotacion.COLA_LARGA) == 6
    siguiente = rotacion.calcular_lote(estado, "linkedin", NUCLEO, COLA, 3, 1)
    assert [c.keyword for c in siguiente if c.grupo == rotacion.COLA_LARGA] == ["c6", "c7"]


def test_fin_de_la_lista(estado):
    with estado.transaccion() as cx:
        cx.execute("INSERT INTO rotacion VALUES ('linkedin', 'cola_larga', 89)")
    lote = correr(estado)
    assert [c.keyword for c in lote if c.grupo == rotacion.COLA_LARGA] == ["c89", "c0"]
    assert rotacion.obtener_indice(estado, "linkedin", rotacion.COLA_LARGA) == 1


def test_avanza_solo_lo_ejecutado(estado):
    lote = rotacion.calcular_lote(estado, "linkedin", NUCLEO, COLA, 3, 1)
    rotacion.avanzar_lote(estado, "linkedin", lote[:2], len(NUCLEO), len(COLA))
    assert rotacion.obtener_indice(estado, "linkedin", rotacion.NUCLEO) == 1
    assert rotacion.obtener_indice(estado, "linkedin", rotacion.COLA_LARGA) == 1


def test_rotacion_independiente_por_fuente(estado):
    correr(estado, "linkedin")
    lote = correr(estado, "computrabajo", presupuesto=4)
    assert [c.keyword for c in lote] == ["n0", "c0", "c1", "c2"]


def test_grupo_vacio_cede_presupuesto(estado):
    lote = correr(estado, presupuesto=3, reservado=1, cola=[])
    assert [c.keyword for c in lote] == ["n0", "n1", "n2"]
    lote = correr(estado, "otra", presupuesto=3, reservado=1, nucleo=[], cola=["a", "b"])
    assert [c.keyword for c in lote] == ["a", "b"]


def test_nucleo_paginado(estado):
    lote = rotacion.calcular_lote(estado, "computrabajo", NUCLEO, COLA, 8, 2, 3)
    assert [(c.keyword, c.pagina) for c in lote if c.grupo == rotacion.NUCLEO] == [
        ("n0", 1), ("n0", 2), ("n0", 3), ("n1", 1), ("n1", 2), ("n1", 3),
    ]  # fmt: skip
    assert [(c.keyword, c.pagina) for c in lote if c.grupo == rotacion.COLA_LARGA] == [
        ("c0", 1), ("c1", 1),
    ]  # fmt: skip


def test_nucleo_paginado_avanza_por_palabra_clave(estado):
    lote = rotacion.calcular_lote(estado, "computrabajo", NUCLEO, COLA, 8, 2, 3)
    rotacion.avanzar_lote(estado, "computrabajo", lote, len(NUCLEO), len(COLA))
    assert rotacion.obtener_indice(estado, "computrabajo", rotacion.NUCLEO) == 2
    assert rotacion.obtener_indice(estado, "computrabajo", rotacion.COLA_LARGA) == 2
    siguiente = rotacion.calcular_lote(estado, "computrabajo", NUCLEO, COLA, 8, 2, 3)
    assert [c.keyword for c in siguiente if c.grupo == rotacion.NUCLEO][::3] == ["n2", "n3"]


def test_paginas_cortadas_no_frenan_la_rotacion(estado):
    # Solo se ejecutó la página 1 de cada palabra clave (las demás se cortaron)
    lote = rotacion.calcular_lote(estado, "computrabajo", NUCLEO, COLA, 8, 2, 3)
    ejecutadas = [c for c in lote if c.pagina == 1]
    rotacion.avanzar_lote(estado, "computrabajo", ejecutadas, len(NUCLEO), len(COLA))
    assert rotacion.obtener_indice(estado, "computrabajo", rotacion.NUCLEO) == 2


def test_cola_vacia_cede_presupuesto_a_palabras_paginadas(estado):
    lote = rotacion.calcular_lote(estado, "x", NUCLEO, [], 8, 2, 3)
    assert len(lote) == 6  # 8 // 3 = 2 palabras clave completas
    assert {c.keyword for c in lote} == {"n0", "n1"}


# --- turnos de consultas combinadas ---------------------------------------------------------


def turnos(estado, cantidad, grupos_nucleo, grupos_cola, variantes=2, cola_cada=4, paginas=2):
    """Corre ``cantidad`` turnos ejecutando todo lo que piden; devuelve lo que fue cada uno."""
    salida = []
    for _ in range(cantidad):
        turno = rotacion.calcular_turno(
            estado, "linkedin", grupos_nucleo, grupos_cola, variantes, cola_cada, paginas
        )
        rotacion.avanzar_turno(
            estado, "linkedin", turno, turno.lote, len(grupos_nucleo), len(grupos_cola),
            variantes, cola_cada,
        )  # fmt: skip
        salida.append(turno)
    return salida


def test_turnos_ocho_corridas_dan_seis_de_nucleo_y_dos_de_cola(estado):
    corridas = turnos(estado, 8, ["N"], ["C0", "C1", "C2"])
    assert [t.cola for t in corridas] == [False, False, False, True] * 2
    assert [t.lote[0].keyword for t in corridas if t.cola] == ["C0", "C0"]
    assert sum(not t.cola for t in corridas) == 6


def test_turnos_alternan_las_variantes(estado):
    corridas = turnos(estado, 8, ["N"], ["C0", "C1"])
    assert [t.variante for t in corridas if not t.cola] == [0, 1, 0, 1, 0, 1]
    assert [t.variante for t in corridas if t.cola] == [0, 1]


def test_turnos_con_dos_grupos_de_nucleo_pasan_por_todas_las_parejas(estado):
    corridas = [t for t in turnos(estado, 40, ["N0", "N1"], ["C0"]) if not t.cola]
    parejas = [(t.lote[0].keyword, t.variante) for t in corridas]
    assert set(parejas[:4]) == {("N0", 0), ("N0", 1), ("N1", 0), ("N1", 1)}
    assert parejas[:4] == parejas[4:8]  # el ciclo se repite


def test_turnos_la_cola_recorre_grupos_y_variantes(estado):
    corridas = [t for t in turnos(estado, 4 * 6, ["N"], ["C0", "C1", "C2"]) if t.cola]
    parejas = [(t.lote[0].keyword, t.variante) for t in corridas]
    assert len(set(parejas)) == 6 and set(parejas) == {
        (g, v) for g in ("C0", "C1", "C2") for v in (0, 1)
    }


def test_turnos_el_nucleo_pide_dos_paginas_y_la_cola_una(estado):
    nucleo, cola = turnos(estado, 4, ["N"], ["C0"])[2:4]
    assert not nucleo.cola and [(c.pagina, c.grupo) for c in nucleo.lote] == [
        (1, rotacion.NUCLEO), (2, rotacion.NUCLEO)
    ]  # fmt: skip
    assert cola.cola and [(c.pagina, c.grupo) for c in cola.lote] == [(1, rotacion.COLA_LARGA)]


def test_turnos_sin_ejecutar_no_avanzan_nada(estado):
    antes = rotacion.calcular_turno(estado, "linkedin", ["N"], ["C"], 2, 4, 2)
    rotacion.avanzar_turno(estado, "linkedin", antes, [], 1, 1, 2, 4)  # nada se ejecutó
    despues = rotacion.calcular_turno(estado, "linkedin", ["N"], ["C"], 2, 4, 2)
    assert despues == antes
    assert estado.cx.execute("SELECT COUNT(*) FROM rotacion").fetchone()[0] == 0


def test_turnos_avanzan_aunque_la_consulta_haya_sido_bloqueada(estado):
    turno = rotacion.calcular_turno(estado, "linkedin", ["N"], ["C"], 2, 4, 2)
    rotacion.avanzar_turno(estado, "linkedin", turno, turno.lote[:1], 1, 1, 2, 4)
    siguiente = rotacion.calcular_turno(estado, "linkedin", ["N"], ["C"], 2, 4, 2)
    assert siguiente.variante == 1 and siguiente != turno


def test_turnos_sin_variantes_usan_la_unica_posicion(estado):
    corridas = turnos(estado, 6, ["N0", "N1"], ["C"], variantes=0)
    assert {t.variante for t in corridas} == {0}
    assert [t.lote[0].keyword for t in corridas if not t.cola] == ["N0", "N1", "N0", "N1", "N0"]


def test_turnos_no_tocan_la_rotacion_por_palabra_clave(estado):
    turnos(estado, 8, ["N"], ["C"])
    grupos = {f["grupo"] for f in estado.cx.execute("SELECT grupo FROM rotacion")}
    assert grupos == {"turno", "turno_nucleo", "turno_cola"}


def test_turnos_el_contador_se_ajusta_si_cambia_cola_cada(estado):
    turnos(estado, 2, ["N"], ["C"], cola_cada=4)  # el contador queda en 2
    siguiente = rotacion.calcular_turno(estado, "linkedin", ["N"], ["C"], 2, 3, 2)
    assert siguiente.cola  # con ciclos de 3, la posición 2 es la de la cola


def test_turnos_un_grupo_vacio_cede_su_turno(estado):
    assert all(t.cola for t in turnos(estado, 5, [], ["C0"]))
    assert not any(t.cola for t in turnos(estado, 8, ["N"], []))
