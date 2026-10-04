import json
from datetime import datetime, timedelta

import pytest

from config import cargar_configuracion
from estado import Estado, a_texto
from fechas import ZONA
from ia_cliente import RespuestaIA
from notificador_telegram import ResultadoEnvio
from resumen import Resumen, calcular_metricas

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
        for horas, modo in [(2, "normal"), (4, "normal"), (6, "dry-run")]:
            corrida_id = cx.execute(
                "INSERT INTO corridas(inicio, modo, crudas, descartes_json, duplicadas, dudosas, "
                "ia_aceptadas, ia_rechazadas, pendientes, enviadas) "
                "VALUES (?, ?, 50, ?, 5, 4, 2, 1, 1, 2)",
                (hace(hours=horas), modo,
                 json.dumps({"seniority": 3, "antiguedad": 1, "ubicacion": 0, "no_ti": 20})),
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
    assert "🧹 Descartes: seniority 6 · antigüedad 2 · ubicación 0 · no TI 40" in texto
    assert "🤖 Dudosas: 8 → 4 aceptadas · 2 rechazadas · 1 pendientes" in texto
    assert "elempleo:cambio_html" in texto and "cerrados hoy: 1" in texto
    assert "💡 <b>Recomendaciones</b>\n1. Revisar 'semillero'" in texto


def test_payload_solo_metricas_agregadas(config, estado):
    ia = IAFalsa(RECOMENDACIONES)
    crear(config, estado, ia, NotificadorFalso()).enviar()
    payload = json.dumps(ia.llamadas[0][1])
    assert "semillero" in payload  # dato para recomendar revisar la palabra clave
    assert "https://" not in payload and "-100REAL" not in payload


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
