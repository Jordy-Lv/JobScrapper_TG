import json
from datetime import datetime, timedelta

import pytest

from buscador_vacantes.config import cargar_configuracion
from buscador_vacantes.estado import Estado, a_texto
from buscador_vacantes.fechas import ZONA
from buscador_vacantes.ia_cliente import RespuestaIA
from buscador_vacantes.notificador_telegram import ResultadoEnvio
from buscador_vacantes.resumen import Resumen, calcular_metricas

AHORA = datetime(2026, 10, 4, 8, 0, tzinfo=ZONA)


class NotificadorFalso:
    def __init__(self):
        self.mensajes = []

    def enviar_mensaje(self, chat_id, texto):
        self.mensajes.append((chat_id, texto))
        return ResultadoEnvio(True)

    def enviar_foto(self, chat_id, ruta):
        return ResultadoEnvio(True)

    def cerrar(self):
        pass


class IAFalsa:
    def __init__(self, respuesta):
        self.respuesta = respuesta
        self.llamadas = []

    def chat_json(self, proposito, prompt, payload, **kwargs):
        self.llamadas.append((proposito, payload))
        return self.respuesta

    def saldo(self):
        return 10.0


RECOMENDACIONES = RespuestaIA(True, {
    "titular": "Día estable con 3 vacantes enviadas",
    "recomendaciones": ["Revisar 'semillero': 0 resultados en 7 días en todas las fuentes."],
})  # fmt: skip


@pytest.fixture
def estado():
    e = Estado.abrir(":memory:")
    hace = lambda **kw: a_texto(AHORA - timedelta(**kw))  # noqa: E731
    with e.transaccion() as cx:
        for clave, fuente, categoria, horas in [
            ("linkedin:1", "linkedin", "practicas", 3), ("linkedin:2", "linkedin", "desarrollo", 5),
            ("magneto:9", "magneto", "practicas", 10), ("computrabajo:X", "computrabajo", None, 30),
        ]:  # fmt: skip
            cx.execute(
                "INSERT INTO vistas(clave, huella, fuente, categoria, primera_vez, enviada_en) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (clave, clave, fuente, categoria, hace(hours=horas), hace(hours=horas)),
            )
        # (horas, modo, prácticas recategorizadas, prácticas rechazadas por el guardarraíl)
        for horas, modo, recategorizadas, rechazadas in [
            (2, "normal", 3, 1), (4, "normal", 1, 0), (6, "dry-run", 9, 9)
        ]:  # fmt: skip
            corrida_id = cx.execute(
                "INSERT INTO corridas(inicio, modo, crudas, descartes_json, duplicadas, dudosas, "
                "ia_aceptadas, ia_rechazadas, pendientes, enviadas, practicas_recategorizadas, "
                "practicas_rechazadas) VALUES (?, ?, 50, ?, 5, 4, 2, 1, 1, 2, ?, ?)",
                (hace(hours=horas), modo,
                 json.dumps({"seniority": 3, "antiguedad": 1, "ubicacion": 0, "no_ti": 20,
                             "presencial_fuera": 15, "call_center": 2}),
                 recategorizadas, rechazadas),
            ).lastrowid  # fmt: skip
            for keyword, items in [("semillero", 0), ("practicante TI", 12)]:
                cx.execute(
                    "INSERT INTO intentos(ts, corrida_id, fuente, keyword, url, status, items) "
                    "VALUES (?, ?, 'linkedin', ?, 'https://x', 200, ?)",
                    (hace(hours=horas), corrida_id, keyword, items),
                )
        cx.execute("INSERT INTO incidentes(fuente, tipo, abierto_desde) VALUES "
                   "('elempleo', 'cambio_html', ?)", (hace(hours=12),))  # fmt: skip
        cx.execute("INSERT INTO incidentes(fuente, tipo, abierto_desde, cerrado_en) VALUES "
                   "('linkedin', 'bloqueo', ?, ?)", (hace(hours=20), hace(hours=15)))  # fmt: skip
        cx.execute("INSERT INTO ia_uso(ts, proposito, tokens_in, tokens_out, ok) VALUES "
                   "(?, 'clasificador', 1200, 300, 1)", (hace(hours=2),))  # fmt: skip
    yield e
    e.cerrar()


@pytest.fixture
def config():
    return cargar_configuracion().resumen


def crear(config, estado, ia, notificador, **kwargs):
    return Resumen(config, ia, estado, notificador, "-100REAL", reloj=lambda: AHORA, **kwargs)


def test_metricas_de_24h(estado):
    m = calcular_metricas(estado, AHORA)
    assert m.enviadas == 3  # la de hace 30 h queda fuera
    assert dict(m.enviadas_por_fuente) == {"linkedin": 2, "magneto": 1}
    assert dict(m.enviadas_por_categoria) == {"practicas": 2, "desarrollo": 1}
    assert m.corridas == 2  # el dry-run no cuenta
    assert m.crudas == 100 and m.duplicadas == 10 and m.dudosas == 8
    assert (m.ia_aceptadas, m.ia_rechazadas, m.pendientes) == (4, 2, 1)
    assert m.descartes["no_ti"] == 40
    assert m.descartes["presencial_fuera"] == 30 and m.descartes["call_center"] == 4
    assert (m.practicas_recategorizadas, m.practicas_rechazadas) == (4, 1)
    assert m.requests_por_fuente["linkedin"] == 4
    assert m.incidentes_abiertos == ["elempleo:cambio_html"]
    assert m.incidentes_cerrados == ["linkedin:bloqueo"]
    assert m.ia_llamadas["clasificador"] == 1 and m.tokens_in == 1200
    assert m.keywords_sin_resultados_7d == ["semillero"]


def test_resumen_activado_una_llamada_y_un_envio(config, estado):
    ia, notificador = IAFalsa(RECOMENDACIONES), NotificadorFalso()
    assert crear(config, estado, ia, notificador).enviar()
    assert len(ia.llamadas) == 1 and ia.llamadas[0][0] == "resumen"
    [(chat, texto)] = notificador.mensajes
    assert chat == "-100REAL"
    assert "📊 <b>Resumen diario · 4 oct</b>" in texto
    assert "<i>Día estable con 3 vacantes enviadas</i>" in texto
    assert "📨 Enviadas: 3 (LinkedIn 2 · Magneto 1)" in texto
    assert "🗂 Por categoría: Prácticas 2 · Desarrollo 1" in texto
    assert (
        "🧹 Descartes: lista negra 0 · seniority 6 · antigüedad 2 · ubicación 0 · "
        "presencial fuera de la ciudad base 30 · call center no remoto 4 · no TI 40"
    ) in texto
    assert "🛡️ Guardarraíl de prácticas: 4 recategorizadas · 1 rechazada" in texto
    assert "🤖 Dudosas: 8 → 4 aceptadas · 2 rechazadas · 1 pendientes" in texto
    assert "elempleo:cambio_html" in texto and "cerrados hoy: 1" in texto
    assert "💡 <b>Recomendaciones</b>\n1. Revisar 'semillero'" in texto


def test_payload_solo_metricas_agregadas(config, estado):
    ia = IAFalsa(RECOMENDACIONES)
    crear(config, estado, ia, NotificadorFalso()).enviar()
    payload = json.dumps(ia.llamadas[0][1])
    assert "semillero" in payload  # dato para recomendar revisar la palabra clave
    assert "https://" not in payload and "-100REAL" not in payload
    metricas = ia.llamadas[0][1]["metricas"]
    assert metricas["guardarrail_practicas"] == {"recategorizadas": 4, "rechazadas": 1}
    assert metricas["descartes_por_regla"]["presencial_fuera"] == 30
    assert metricas["descartes_por_regla"]["call_center"] == 4


def test_resumen_ya_enviado_hoy(config, estado):
    crear(config, estado, IAFalsa(RECOMENDACIONES), NotificadorFalso()).enviar()
    ia, notificador = IAFalsa(RECOMENDACIONES), NotificadorFalso()
    assert not crear(config, estado, ia, notificador).enviar()
    assert notificador.mensajes == [] and ia.llamadas == []


def test_resumen_desactivado(config, estado):
    ia, notificador = IAFalsa(RECOMENDACIONES), NotificadorFalso()
    desactivado = config.model_copy(update={"activo": False})
    assert not crear(desactivado, estado, ia, notificador).enviar()
    assert notificador.mensajes == [] and ia.llamadas == []


@pytest.mark.parametrize(
    ("respuesta", "motivo"),
    [
        (
            RespuestaIA(False, motivo="error del servidor (HTTP 503)"),
            "error del servidor (HTTP 503)",
        ),
        (RespuestaIA(False, motivo="saldo bajo", realizada=False), "saldo bajo"),
        (RespuestaIA(True, {"titular": "x", "recomendaciones": []}), "respuesta inválida"),
    ],
)
def test_respaldo_sin_ia(config, estado, respuesta, motivo):
    notificador = NotificadorFalso()
    assert crear(config, estado, IAFalsa(respuesta), notificador).enviar()
    texto = notificador.mensajes[0][1]
    assert "📨 Enviadas: 3" in texto and "🧹 Descartes" in texto
    assert f"Recomendaciones IA no disponibles (motivo: {motivo})" in texto
    assert "💡" not in texto


def test_dry_run_no_registra_el_envio(config, estado):
    crear(config, estado, IAFalsa(RECOMENDACIONES), NotificadorFalso()).enviar(registrar=False)
    assert estado.kv_obtener("ultimo_resumen") is None


def test_chat_de_prueba_no_bloquea_el_resumen_real(config, estado):
    crear(config, estado, IAFalsa(RECOMENDACIONES), NotificadorFalso(), prueba=True).enviar()
    notificador = NotificadorFalso()
    assert crear(config, estado, IAFalsa(RECOMENDACIONES), notificador).enviar()


def test_resumen_de_prueba_cuenta_los_envios_de_prueba(config, estado):
    with estado.transaccion() as cx:
        cx.execute("INSERT INTO vistas(clave, huella, fuente, categoria, primera_vez, prueba_en) "
                   "VALUES ('magneto:5', 'h5', 'magneto', 'qa', ?, ?)",
                   (a_texto(AHORA - timedelta(hours=1)),) * 2)  # fmt: skip
    assert calcular_metricas(estado, AHORA, prueba=True).enviadas == 1
    assert calcular_metricas(estado, AHORA).enviadas == 3
    # Tras promover-prueba, lo de la fase de prueba no cuenta como enviado al canal
    estado.promover_prueba()
    assert calcular_metricas(estado, AHORA).enviadas == 3


def test_guardarrail_sin_correcciones_se_muestra_en_cero(config, estado):
    with estado.transaccion() as cx:
        cx.execute("UPDATE corridas SET practicas_recategorizadas = 0, practicas_rechazadas = 0")
    notificador = NotificadorFalso()
    crear(config, estado, IAFalsa(RECOMENDACIONES), notificador).enviar()
    assert (
        "🛡️ Guardarraíl de prácticas: 0 recategorizadas · 0 rechazadas" in notificador.mensajes[0][1]
    )


def test_metricas_de_detalle(estado):
    with estado.transaccion() as cx:
        # Las dos corridas normales de las últimas 24 h; el dry-run no cuenta
        normales = cx.execute("SELECT id FROM corridas WHERE modo = 'normal' ORDER BY id")
        ids = [f[0] for f in normales]
        cx.execute(
            "UPDATE corridas SET detalles_pedidos = 40, detalles_fallidos = 3, "
            "detalles_recuperadas = 6, detalles_cerradas = 2, detalles_vencidas = 1 WHERE id = ?",
            (ids[0],),
        )
        cx.execute(
            "UPDATE corridas SET detalles_pedidos = 20, detalles_fallidos = 1, "
            "detalles_recuperadas = 3, detalles_cerradas = 0, detalles_vencidas = 0 WHERE id = ?",
            (ids[1],),
        )
        cx.execute("UPDATE corridas SET detalles_pedidos = 99 WHERE modo = 'dry-run'")
        for n in range(3):
            cx.execute(
                "INSERT INTO pendientes_detalle(clave, huella, vacante_json, desde) "
                "VALUES (?, ?, '{}', ?)",
                (f"linkedin:{n}", f"h{n}", a_texto(AHORA)),
            )
    m = calcular_metricas(estado, AHORA)
    assert (m.detalles_pedidos, m.detalles_fallidos, m.detalles_recuperadas) == (60, 4, 9)
    assert (m.detalles_cerradas, m.detalles_vencidas, m.detalles_en_cola) == (2, 1, 3)
    assert m.para_ia()["detalle_de_ofertas"] == {
        "pedidos": 60, "fallidos": 4, "recuperadas": 9, "cerradas": 2, "vencidas": 1, "en_cola": 3,
    }  # fmt: skip


def test_el_resumen_muestra_la_linea_de_detalle_de_linkedin(config, estado):
    with estado.transaccion() as cx:
        cx.execute(
            "UPDATE corridas SET detalles_pedidos = 30, detalles_fallidos = 2, "
            "detalles_recuperadas = 4, detalles_vencidas = 1, detalles_cerradas = 1 "
            "WHERE modo = 'normal'"
        )
        cx.execute(
            "INSERT INTO pendientes_detalle(clave, huella, vacante_json, desde) "
            "VALUES ('linkedin:1', 'h', '{}', ?)",
            (a_texto(AHORA),),
        )
    notificador, ia = NotificadorFalso(), IAFalsa(RECOMENDACIONES)
    crear(config, estado, ia, notificador).enviar()
    texto = notificador.mensajes[0][1]
    assert (
        "Detalle de LinkedIn: 60 pedidos · 4 fallidos · 8 recuperadas · 1 en cola · 2 vencidas"
        in texto
    )
    assert ia.llamadas[0][1]["metricas"]["detalle_de_ofertas"]["en_cola"] == 1


def test_el_detalle_sin_actividad_se_muestra_en_cero(config, estado):
    notificador = NotificadorFalso()
    crear(config, estado, IAFalsa(RECOMENDACIONES), notificador).enviar()
    assert (
        "Detalle de LinkedIn: 0 pedidos · 0 fallidos · 0 recuperadas · 0 en cola · 0 vencidas"
        in notificador.mensajes[0][1]
    )


def test_las_peticiones_de_detalle_no_cuentan_como_palabras_sin_resultados(estado):
    with estado.transaccion() as cx:
        for horas in (1, 2, 3):
            cx.execute(
                "INSERT INTO intentos(ts, corrida_id, fuente, keyword, url, status, items) "
                "VALUES (?, 1, 'linkedin', 'detalle 123', 'https://x', 200, 0)",
                (a_texto(AHORA - timedelta(hours=horas)),),
            )
    assert calcular_metricas(estado, AHORA).keywords_sin_resultados_7d == ["semillero"]
