"""Simulación de incidentes: evidencia de ejemplo → reportero completo, sin tocar el estado real."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta

from buscador_vacantes import config as cfg
from buscador_vacantes.estado import Estado, a_texto
from buscador_vacantes.fechas import ZONA
from buscador_vacantes.fuentes.base import Fuente, Intento, TipoError
from buscador_vacantes.ia_cliente import ClienteIA, RespuestaIA
from buscador_vacantes.incidentes import (
    RED,
    TELEGRAM,
    TIPOS,
    Detector,
    Incidente,
    ResultadoEvaluacion,
)
from buscador_vacantes.notificador_telegram import Notificador, ResultadoEnvio
from buscador_vacantes.reportero import DatosFuente, Reportero

FALLAS_IA = {
    "saldo_bajo": RespuestaIA(False, motivo="saldo bajo", realizada=False),
    "api_caida": RespuestaIA(False, motivo="error del servidor (HTTP 503)"),
}

# Por tipo: dato principal, status, tipo de error, cabeceras y cuerpo de ejemplo
EJEMPLOS: dict[str, tuple[str, int | None, TipoError | None, dict[str, str], str]] = {
    "bloqueo": ("HTTP 429/403/999 en 2 corridas seguidas", 429, TipoError.BLOQUEO,
                {"retry-after": "3600", "server": "nginx"},
                "<html><body>Too Many Requests</body></html>"),
    "captcha": ("respuesta 200 con página de desafío anti-bot", 200, TipoError.CAPTCHA,
                {"server": "cloudflare", "cf-ray": "8c1f2e3d4a5b6c7d-BOG"},
                "<html><script src='/cdn-cgi/challenge-platform/h/b/cf-chl'></script>"
                "<body>Verificando que eres humano…</body></html>"),
    "cambio_html": ("respuesta 200 sin la estructura esperada del listado", 200,
                    TipoError.CAMBIO_HTML, {"content-type": "text/html; charset=utf-8"},
                    "<html><body><main class='jobs-v2'><section class='offer-card'>"
                    "<h3 class='offer-card__title'>Practicante de sistemas</h3>"
                    "<span class='offer-card__company'>Empresa X</span></section></main>"
                    "</body></html>"),
    "sin_resultados": ("0 vacantes en 24 h; hubo resultados los 7 días previos", 200, None,
                       {"content-type": "application/json"}, '{"rows": []}'),
    "caida_volumen": ("6 vacantes en 24 h frente a un promedio de 48 por día", 200, None,
                      {"content-type": "text/html"}, "<html><body>2 ofertas</body></html>"),
    "error_servidor": ("HTTP 5xx o timeouts en 3 corridas seguidas", 503, TipoError.SERVIDOR,
                       {"server": "Microsoft-IIS/10.0"},
                       "<html><body>Service Unavailable</body></html>"),
    "fallo_envio": ("Bad Request: can't parse entities: unsupported start tag \"remoto\"",
                    None, None, {}, ""),
}  # fmt: skip


class IAFija:
    """Cliente IA que siempre responde lo mismo (para simular fallas)."""

    def __init__(self, respuesta: RespuestaIA, saldo: float = 0.42) -> None:
        self.respuesta = respuesta
        self._saldo = saldo

    def chat_json(self, *args, **kwargs) -> RespuestaIA:
        return self.respuesta

    def saldo(self) -> float:
        return self._saldo

    def cerrar(self) -> None:
        pass


class NotificadorConsola:
    def __init__(self, salida: Callable[[str], None] = print) -> None:
        self.salida = salida

    def enviar_mensaje(self, chat_id: str, texto_html: str, botones=None) -> ResultadoEnvio:
        extra = "".join(f"\n[{texto}]" for texto, _ in botones or [])
        self.salida(f"--- mensaje para {chat_id} ---\n{texto_html}{extra}\n")
        return ResultadoEnvio(True)

    def enviar_foto(self, chat_id, ruta) -> ResultadoEnvio:
        return ResultadoEnvio(True)

    def cerrar(self) -> None:
        pass


def validar_objetivo(objetivo: str, config: cfg.Configuracion) -> tuple[str, str]:
    fuente, _, tipo = objetivo.partition(":")
    if (fuente, tipo) == RED:
        return fuente, tipo
    if fuente == TELEGRAM and tipo == "fallo_envio":
        return fuente, tipo
    if fuente not in config.fuentes:
        raise ValueError(f"Fuente desconocida: {fuente!r}")
    if tipo not in TIPOS or tipo == "fallo_envio":
        raise ValueError(f"Tipo desconocido: {tipo!r}. Usa uno de {', '.join(TIPOS[:-1])}")
    return fuente, tipo


def simular(
    objetivo: str,
    config: cfg.Configuracion,
    notificador: Notificador,
    chat_id: str,
    fuentes: dict[str, type[Fuente]],
    *,
    api_key: str | None = None,
    falla_ia: str | None = None,
    ahora: datetime | None = None,
) -> Incidente:
    """Corre el reportero sobre un incidente de ejemplo en una base en memoria."""
    fuente, tipo = validar_objetivo(objetivo, config)
    ahora = ahora or datetime.now(ZONA)
    estado = Estado.abrir(":memory:")  # nada toca data/vacantes.db
    try:
        dato, status, tipo_error, cabeceras, cuerpo = EJEMPLOS.get(
            tipo, ("todas las fuentes fallaron por conexión/DNS", None, None, {}, "")
        )
        # Historial de ejemplo: volumen normal los 7 días previos y la falla reciente
        with estado.transaccion() as cx:
            for dias in range(7, 0, -1):
                cx.execute(
                    "INSERT INTO intentos(ts, fuente, keyword, url, status, ms, items) "
                    "VALUES (?, ?, 'practicante sistemas', 'https://ejemplo/buscar', 200, 450, ?)",
                    (a_texto(ahora - timedelta(days=dias)), fuente, 40 + dias),
                )
            if status is not None or tipo_error is not None:
                cx.execute(
                    "INSERT INTO intentos(ts, fuente, keyword, url, status, ms, items, tipo_error) "
                    "VALUES (?, ?, 'aprendiz SENA', 'https://ejemplo/buscar', ?, 380, 0, ?)",
                    (a_texto(ahora), fuente, status, tipo_error.value if tipo_error else None),
                )
            if tipo == "bloqueo":
                cx.execute(
                    "INSERT INTO fuentes_estado(fuente, cooldown_hasta, escalon, "
                    "fallos_consecutivos) VALUES (?, ?, 1, 2)",
                    (fuente, a_texto(ahora + timedelta(hours=6))),
                )
        detector = Detector(estado, config.incidentes)
        desde = ahora - (timedelta(hours=1, minutes=40) if (fuente, tipo) == RED else timedelta())
        incidente = detector._abrir(fuente, tipo, dato, desde)
        intento = Intento(ts=ahora, fuente=fuente, keyword="aprendiz SENA",
                          url="https://ejemplo/buscar", status=status, tipo_error=tipo_error,
                          cabeceras=cabeceras, cuerpo=cuerpo)  # fmt: skip

        if falla_ia:
            ia = IAFija(FALLAS_IA[falla_ia])
        elif api_key:
            ia = ClienteIA(config.ia, api_key, estado)
        else:
            ia = None
        datos = {
            nombre: DatosFuente(clase.selectores, config.fuentes[nombre].presupuesto)
            for nombre, clase in fuentes.items()
            if nombre in config.fuentes
        }
        reportero = Reportero(config.reportero, ia, estado, detector, notificador, chat_id, datos,
                              reloj=lambda: ahora)  # fmt: skip
        if (fuente, tipo) == RED:
            incidente.cerrado_en = ahora
            resultado = ResultadoEvaluacion(recuperados=[incidente])
        else:
            resultado = ResultadoEvaluacion(nuevos=[incidente])
        otras = [n for n in datos if n != fuente][:3]
        reportero.notificar(resultado, [intento], otras)
        if ia is not None:
            ia.cerrar()
        return incidente
    finally:
        estado.cerrar()
