import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx

from buscador_vacantes.config import cargar_configuracion
from buscador_vacantes.estado import Estado, a_texto
from buscador_vacantes.fechas import ZONA
from buscador_vacantes.fuentes.base import Intento, TipoError
from buscador_vacantes.ia_cliente import ClienteIA, RespuestaIA
from buscador_vacantes.incidentes import Detector, Incidente, ResultadoEvaluacion
from buscador_vacantes.notificador_telegram import ResultadoEnvio
from buscador_vacantes.reportero import DatosFuente, Reportero, duracion, muestra_cuerpo

AHORA = datetime(2026, 10, 3, 15, 30, tzinfo=ZONA)
TOKEN = "123456789:AAFakeTokenFakeTokenFakeTokenFake12"
CHAT = "-1004429829042"
CLAVE = "sk-clave-de-prueba-123456"


class NotificadorFalso:
    def __init__(self, ok=True):
        self.mensajes = []
        self.ok = ok

    def enviar_mensaje(self, chat_id, texto):
        self.mensajes.append((chat_id, texto))
        return ResultadoEnvio(self.ok, error=None if self.ok else "fallo")

    def enviar_foto(self, chat_id, ruta):
        return ResultadoEnvio(True)

    def cerrar(self):
        pass


class IAFalsa:
    def __init__(self, respuesta, saldo=25.0):
        self.respuesta = respuesta
        self._saldo = saldo
        self.payloads = []

    def chat_json(self, proposito, prompt, payload, **kwargs):
        self.payloads.append(payload)
        return self.respuesta(payload) if callable(self.respuesta) else self.respuesta

    def saldo(self):
        return self._saldo


def diagnostico(fuente="linkedin", tipo="bloqueo", **cambios):
    base = {
        "fuente": fuente, "tipo": tipo, "severidad": "alta",
        "causa_probable": "HTTP 429 con retry-after de 1 h: LinkedIn limitó la IP.",
        "evidencia_clave": "4 intentos seguidos con 429 · otras fuentes OK",
        "accion_recomendada": "Bajar el presupuesto de LinkedIn de 3 a 2 requests.",
        "requiere_intervencion": False, "sugerencia_tecnica": None,
    }  # fmt: skip
    base.update(cambios)
    return base


@pytest.fixture
def estado():
    e = Estado.abrir(":memory:")
    yield e
    e.cerrar()


@pytest.fixture
def config():
    return cargar_configuracion()


def crear(config, estado, ia, notificador=None):
    datos = {"linkedin": DatosFuente(["div.base-search-card"], 3),
             "magneto": DatosFuente(["rows[].id"], 3)}  # fmt: skip
    return Reportero(
        config.reportero, ia, estado, Detector(estado, config.incidentes),
        notificador or NotificadorFalso(), CHAT, datos, reloj=lambda: AHORA,
    )  # fmt: skip


def abrir(
    estado,
    fuente="linkedin",
    tipo="bloqueo",
    dato="HTTP 429 en 2 corridas seguidas",
    desde=AHORA - timedelta(hours=1),
):
    with estado.transaccion() as cx:
        id_ = cx.execute(
            "INSERT INTO incidentes(fuente, tipo, abierto_desde, detalle_json) VALUES (?,?,?,?)",
            (fuente, tipo, a_texto(desde), json.dumps({"dato": dato})),
        ).lastrowid
    return Incidente(fuente, tipo, desde, dato, id=id_)


def intento_bloqueado():
    return Intento(
        ts=AHORA, fuente="linkedin", keyword="practicante",
        url="https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords=x",
        status=429, items=0, tipo_error=TipoError.BLOQUEO,
        cabeceras={"retry-after": "3600", "server": "LinkedIn", "set-cookie": "li_at=secreto",
                   "authorization": f"Bearer {CLAVE}", "x-ratelimit-remaining": "0"},
        cuerpo=f"<html><script>var t='{TOKEN}'</script><body>Too many requests</body></html>",
    )  # fmt: skip


def test_mensaje_de_diagnostico(config, estado):
    with estado.transaccion() as cx:
        cx.execute("INSERT INTO fuentes_estado(fuente, cooldown_hasta, escalon) VALUES (?,?,1)",
                   ("linkedin", a_texto(AHORA + timedelta(hours=6))))  # fmt: skip
    incidente = abrir(estado)
    ia = IAFalsa(RespuestaIA(True, {"diagnosticos": [diagnostico()]}))
    notificador = NotificadorFalso()
    crear(config, estado, ia, notificador).notificar(
        ResultadoEvaluacion(nuevos=[incidente]), [intento_bloqueado()], ["computrabajo"]
    )
    [(chat, texto)] = notificador.mensajes
    assert chat == CHAT
    assert "🚨 <b>Incidente: LinkedIn · bloqueo</b> (severidad alta)" in texto
    assert "Abierto desde: hoy 14:30 · cooldown 6 h" in texto
    assert "🔍 <b>Causa probable</b>" in texto and "limitó la IP" in texto
    assert "🛠 <b>Recomendación</b>" in texto and "de 3 a 2 requests" in texto
    assert "📎 Evidencia: 4 intentos seguidos" in texto
    assert "⚠️ Requiere intervención: no" in texto
    assert "<pre>" not in texto
    # Queda marcado como reportado: no se vuelve a pedir diagnóstico
    fila = estado.cx.execute("SELECT ultimo_reporte FROM incidentes").fetchone()
    assert fila[0] is not None


def test_sugerencia_de_selectores_en_bloque_de_codigo(config, estado):
    incidente = abrir(estado, "magneto", "cambio_html", "respuesta 200 sin estructura")
    diag = diagnostico("magneto", "cambio_html", sugerencia_tecnica="rows → data.items[] <nuevo>")
    notificador = NotificadorFalso()
    ia = IAFalsa(RespuestaIA(True, {"diagnosticos": [diag]}))
    crear(config, estado, ia, notificador).notificar(
        ResultadoEvaluacion(nuevos=[incidente]), [], []
    )
    texto = notificador.mensajes[0][1]
    assert "<pre>rows → data.items[] &lt;nuevo&gt;</pre>" in texto
    assert "revisar antes de aplicar" in texto


def test_evidencia_sanitizada_y_completa(config, estado):
    incidente = abrir(estado)
    with estado.transaccion() as cx:
        cx.execute(
            "INSERT INTO intentos(ts, fuente, url, status, ms, items) "
            "VALUES (?, 'linkedin', 'https://x', 429, 300, 0)",
            (a_texto(AHORA),),
        )
    evidencia = crear(config, estado, None).evidencia(
        incidente, [intento_bloqueado()], ["computrabajo", "linkedin"]
    )
    assert evidencia["headers_respuesta"] == {
        "retry-after": "3600", "server": "LinkedIn", "x-ratelimit-remaining": "0"
    }  # fmt: skip
    assert "Too many requests" in evidencia["body_muestra"]
    assert "<script" not in evidencia["body_muestra"] and TOKEN not in evidencia["body_muestra"]
    assert evidencia["selectores_parser"] == ["div.base-search-card"]
    assert len(evidencia["volumen_7_dias"]) == 7
    assert evidencia["presupuesto_requests"] == 3
    assert evidencia["otras_fuentes_ok"] == ["computrabajo"]
    assert evidencia["intentos_recientes"][0]["status"] == 429
    texto = json.dumps(evidencia)
    assert CHAT not in texto and "li_at" not in texto and CLAVE not in texto


@respx.mock
def test_payload_enviado_a_deepseek_sin_secretos(config, estado):
    incidente = abrir(estado)
    respx.get("https://api.deepseek.com/user/balance").mock(return_value=httpx.Response(
        200, json={"balance_infos": [{"currency": "USD", "total_balance": "20"}]}))  # fmt: skip
    ruta = respx.post("https://api.deepseek.com/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": json.dumps({"diagnosticos": [diagnostico()]})}}
                ],
                "usage": {"prompt_tokens": 900, "completion_tokens": 150},
            },
        )  # fmt: skip
    )
    ia = ClienteIA(config.ia, CLAVE, estado, secretos=[CLAVE, TOKEN, CHAT],
                   reloj=lambda: AHORA.astimezone(UTC))  # fmt: skip
    intento = intento_bloqueado()
    intento.cuerpo = f"token {TOKEN} chat {CHAT}"
    crear(config, estado, ia).notificar(ResultadoEvaluacion(nuevos=[incidente]), [intento], [])
    enviado = ruta.calls[0].request.content.decode()
    for secreto in (TOKEN, CHAT, CLAVE, "li_at"):
        assert secreto not in enviado
    assert "linkedin" in enviado
    assert estado.cx.execute("SELECT proposito FROM ia_uso").fetchone()[0] == "reportero"
    ia.cerrar()


def test_varios_incidentes_una_llamada_un_mensaje(config, estado):
    nuevos = [abrir(estado), abrir(estado, "magneto", "cambio_html", "sin estructura")]
    ia = IAFalsa(RespuestaIA(True, {"diagnosticos": [
        diagnostico(), diagnostico("magneto", "cambio_html", severidad="media")]}))  # fmt: skip
    notificador = NotificadorFalso()
    crear(config, estado, ia, notificador).notificar(ResultadoEvaluacion(nuevos=nuevos), [], [])
    assert len(ia.payloads) == 1 and len(ia.payloads[0]["incidentes"]) == 2
    [(_, texto)] = notificador.mensajes
    assert "LinkedIn · bloqueo" in texto and "Magneto · cambio_html" in texto


def test_saldo_bajo_alerta_plana_y_aviso_una_vez_al_dia(config, estado):
    ia = IAFalsa(RespuestaIA(False, motivo="saldo bajo", realizada=False), saldo=0.4)
    notificador = NotificadorFalso()
    reportero = crear(config, estado, ia, notificador)
    reportero.notificar(ResultadoEvaluacion(nuevos=[abrir(estado)]), [], [])
    texto = notificador.mensajes[0][1]
    assert "🚨 Incidente: LinkedIn · bloqueo" in texto
    assert "HTTP 429 en 2 corridas seguidas" in texto
    assert "Diagnóstico IA no disponible (motivo: saldo bajo)" in texto
    assert "💳 Saldo DeepSeek bajo: $0.40" in texto
    reportero.notificar(ResultadoEvaluacion(nuevos=[abrir(estado, "magneto", "captcha")]), [], [])
    assert "💳" not in notificador.mensajes[1][1]


@pytest.mark.parametrize(
    ("respuesta", "motivo"),
    [
        (RespuestaIA(False, motivo="respuesta inválida"), "respuesta inválida"),
        (RespuestaIA(True, {"diagnosticos": [{"severidad": "altísima"}]}), "respuesta inválida"),
        (RespuestaIA(False, motivo="tope diario alcanzado", realizada=False),
         "tope diario alcanzado"),
        (RespuestaIA(False, motivo="error del servidor (HTTP 503)"),
         "error del servidor (HTTP 503)"),
    ],
)  # fmt: skip
def test_alerta_plana_de_respaldo(config, estado, respuesta, motivo):
    notificador = NotificadorFalso()
    crear(config, estado, IAFalsa(respuesta), notificador).notificar(
        ResultadoEvaluacion(nuevos=[abrir(estado)]), [], []
    )
    assert f"Diagnóstico IA no disponible (motivo: {motivo})" in notificador.mensajes[0][1]


def test_aviso_de_recuperacion_sin_ia(config, estado):
    incidente = abrir(estado, desde=AHORA - timedelta(hours=5))
    incidente.cerrado_en = AHORA
    ia = IAFalsa(RespuestaIA(True, {}))
    notificador = NotificadorFalso()
    crear(config, estado, ia, notificador).notificar(
        ResultadoEvaluacion(recuperados=[incidente]), [], []
    )
    assert notificador.mensajes[0][1] == "✅ LinkedIn se recuperó tras 5 h (bloqueo)"
    assert ia.payloads == []


def test_red_recuperada_con_apertura_y_cierre(config, estado):
    desde = datetime(2026, 10, 3, 10, 0, tzinfo=ZONA)
    incidente = Incidente("red", "sin_conexion", desde, "", id=1,
                          cerrado_en=desde + timedelta(hours=1, minutes=40))  # fmt: skip
    notificador = NotificadorFalso()
    crear(config, estado, None, notificador).notificar(
        ResultadoEvaluacion(recuperados=[incidente]), [], []
    )
    assert notificador.mensajes[0][1] == "⚠️ El PC estuvo sin internet de 10:00 a 11:40 (2 h)"


def test_sin_red_no_intenta_avisar(config, estado):
    ia, notificador = IAFalsa(RespuestaIA(True, {})), NotificadorFalso()
    incidente = Incidente("red", "sin_conexion", AHORA, "sin conexión", id=1)
    crear(config, estado, ia, notificador).notificar(
        ResultadoEvaluacion(nuevos=[incidente]), [], []
    )
    assert notificador.mensajes == [] and ia.payloads == []


def test_recordatorio_plano(config, estado):
    incidente = abrir(estado, desde=AHORA - timedelta(hours=26))
    ia, notificador = IAFalsa(RespuestaIA(True, {})), NotificadorFalso()
    crear(config, estado, ia, notificador).notificar(
        ResultadoEvaluacion(recordatorios=[incidente]), [], []
    )
    texto = notificador.mensajes[0][1]
    assert texto.startswith("⏰ Sigue abierto desde hace 26 h: LinkedIn · bloqueo")
    assert ia.payloads == []


def test_la_ia_no_modifica_configuracion_ni_cooldowns(config, estado):
    antes = (estado.cx.execute("SELECT COUNT(*) FROM fuentes_estado").fetchone()[0],
             config.fuentes["linkedin"].presupuesto)  # fmt: skip
    diag = diagnostico(accion_recomendada="Bajar el presupuesto de LinkedIn a 1")
    crear(config, estado, IAFalsa(RespuestaIA(True, {"diagnosticos": [diag]}))).notificar(
        ResultadoEvaluacion(nuevos=[abrir(estado)]), [], []
    )
    despues = (estado.cx.execute("SELECT COUNT(*) FROM fuentes_estado").fetchone()[0],
               cargar_configuracion().fuentes["linkedin"].presupuesto)  # fmt: skip
    assert antes == despues


def test_utilidades():
    assert duracion(AHORA, AHORA + timedelta(minutes=20)) == "20 min"
    assert duracion(AHORA, AHORA + timedelta(hours=5, minutes=10)) == "5 h"
    assert duracion(AHORA, AHORA + timedelta(days=3)) == "3 días"
    assert muestra_cuerpo('{"a": 1}', 100) == '{"a": 1}'
    assert (
        muestra_cuerpo("<style>x</style><p style='a'>hola  mundo</p>", 100) == "<p>hola mundo</p>"
    )
    html = "<html><body><div class='offer' data-x='1' onclick='y()'>A</div><script>z</script>"
    assert muestra_cuerpo(html, 100) == '<div class="offer">A</div>'
