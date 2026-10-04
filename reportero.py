"""Reportero de incidentes: evidencia sanitizada → diagnóstico IA → mensaje; alerta plana si no."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal, Protocol

from bs4 import BeautifulSoup
from pydantic import BaseModel, ValidationError

import config as cfg
from estado import Estado, a_texto, de_texto
from fechas import ZONA, fecha_relativa
from formato import NOMBRES_FUENTE, empaquetar, escapar
from fuentes.base import Intento, filtrar_cabeceras
from ia_cliente import RespuestaIA
from incidentes import RED, TELEGRAM, Detector, Incidente, ResultadoEvaluacion
from notificador_telegram import Notificador

log = logging.getLogger(__name__)

MAX_INTENTOS = 6
MAX_CAMPO = 600
MAX_SUGERENCIA = 1500


class ClienteChat(Protocol):
    def chat_json(self, proposito, prompt_sistema, payload, *, temperatura, max_tokens): ...

    def saldo(self) -> float | None: ...


class Diagnostico(BaseModel):
    fuente: str = ""
    tipo: str = ""
    severidad: Literal["baja", "media", "alta"]
    causa_probable: str
    evidencia_clave: str
    accion_recomendada: str
    requiere_intervencion: bool
    sugerencia_tecnica: str | None = None


class RespuestaReportero(BaseModel):
    diagnosticos: list[Diagnostico]


@dataclass
class DatosFuente:
    """Lo que el reportero necesita saber de una fuente para armar la evidencia."""

    selectores: list[str]
    presupuesto: int | None


def nombre_fuente(fuente: str) -> str:
    if fuente == TELEGRAM:
        return "Telegram"
    if fuente == RED[0]:
        return "Red del PC"
    return NOMBRES_FUENTE.get(fuente, fuente)


def titulo_incidente(incidente: Incidente) -> str:
    return f"{nombre_fuente(incidente.fuente)} · {incidente.tipo}"


def duracion(desde: datetime, hasta: datetime) -> str:
    minutos = int((hasta - desde) / timedelta(minutes=1))
    if minutos < 60:
        return f"{max(minutos, 1)} min"
    horas = round(minutos / 60)
    if horas < 48:
        return f"{horas} h"
    return f"{round(horas / 24)} días"


def muestra_cuerpo(cuerpo: str, maximo: int) -> str:
    """HTML del cuerpo sin scripts, estilos ni atributos salvo class e id, hasta ``maximo``.

    Se conserva la estructura para que la IA pueda sugerir selectores ante un cambio de HTML.
    """
    if not cuerpo:
        return ""
    if cuerpo.lstrip()[:1] in "{[":
        return cuerpo[:maximo]
    sopa = BeautifulSoup(cuerpo, "lxml")
    for etiqueta in sopa(["script", "style", "noscript", "svg", "head", "link", "meta", "img"]):
        etiqueta.decompose()
    for etiqueta in sopa.find_all(True):
        etiqueta.attrs = {k: v for k, v in etiqueta.attrs.items() if k in ("class", "id")}
    raiz = sopa.body or sopa
    return " ".join(raiz.decode_contents().split())[:maximo]


def _hora(momento: datetime, ahora: datetime) -> str:
    local = momento.astimezone(ZONA)
    return f"{fecha_relativa(local, ahora)} {local:%H:%M}"


class Reportero:
    def __init__(
        self,
        config: cfg.Reportero,
        ia: ClienteChat | None,
        estado: Estado,
        detector: Detector,
        notificador: Notificador,
        chat_id: str,
        datos_fuentes: dict[str, DatosFuente],
        *,
        reloj: Callable[[], datetime] = lambda: datetime.now(ZONA),
    ) -> None:
        self.config = config
        self.ia = ia
        self.estado = estado
        self.detector = detector
        self.notificador = notificador
        self.chat_id = chat_id
        self.datos_fuentes = datos_fuentes
        self.reloj = reloj

    # --- evidencia --------------------------------------------------------------------------

    def _intentos_recientes(self, fuente: str) -> list[dict[str, Any]]:
        filas = self.estado.cx.execute(
            "SELECT ts, url, status, ms, items, tipo_error FROM intentos WHERE fuente = ? "
            "ORDER BY id DESC LIMIT ?",
            (fuente, MAX_INTENTOS),
        ).fetchall()
        return [
            {
                "ts": de_texto(f["ts"]).astimezone(ZONA).isoformat(timespec="minutes"),
                "url": f["url"],
                "status": f["status"],
                "ms": f["ms"],
                "items": f["items"],
                "error": f["tipo_error"],
            }
            for f in reversed(filas)
        ]

    def _volumen_7_dias(self, fuente: str, ahora: datetime) -> list[int]:
        volumen = []
        for dias_atras in range(6, -1, -1):
            fin = ahora - timedelta(days=dias_atras)
            fila = self.estado.cx.execute(
                "SELECT COALESCE(SUM(items), 0) FROM intentos WHERE fuente = ? AND ts > ? "
                "AND ts <= ?",
                (fuente, a_texto(fin - timedelta(days=1)), a_texto(fin)),
            ).fetchone()
            volumen.append(fila[0])
        return volumen

    def _cooldown(self, fuente: str, ahora: datetime) -> str | None:
        fila = self.estado.cx.execute(
            "SELECT cooldown_hasta FROM fuentes_estado WHERE fuente = ?", (fuente,)
        ).fetchone()
        hasta = de_texto(fila["cooldown_hasta"]) if fila else None
        if not hasta or hasta <= ahora:
            return None
        return f"{round((hasta - ahora) / timedelta(hours=1), 1):g} h"

    def evidencia(
        self, incidente: Incidente, intentos_corrida: list[Intento], fuentes_ok: list[str]
    ) -> dict[str, Any]:
        """Evidencia del incidente. Sin tokens, claves, cookies ni ids de chat."""
        ahora = self.reloj()
        fuente = incidente.fuente
        ultimo = next((i for i in reversed(intentos_corrida) if i.fuente == fuente), None)
        datos = self.datos_fuentes.get(fuente, DatosFuente([], None))
        evidencia: dict[str, Any] = {
            "fuente": fuente,
            "tipo": incidente.tipo,
            "abierto_desde": incidente.abierto_desde.astimezone(ZONA).isoformat(timespec="minutes"),
            "dato_principal": incidente.dato,
        }
        if fuente == TELEGRAM:
            evidencia["error_telegram"] = incidente.dato
            return evidencia
        evidencia.update(
            {
                "intentos_recientes": self._intentos_recientes(fuente),
                "headers_respuesta": filtrar_cabeceras(ultimo.cabeceras) if ultimo else {},
                "body_muestra": muestra_cuerpo(
                    ultimo.cuerpo if ultimo else "", self.config.max_muestra_cuerpo
                ),
                "selectores_parser": datos.selectores,
                "volumen_7_dias": self._volumen_7_dias(fuente, ahora),
                "cooldown_actual": self._cooldown(fuente, ahora),
                "presupuesto_requests": datos.presupuesto,
                "otras_fuentes_ok": [f for f in fuentes_ok if f != fuente],
            }
        )
        return evidencia

    # --- mensajes ---------------------------------------------------------------------------

    def _alerta_plana(self, incidente: Incidente, motivo: str) -> str:
        lineas = [f"🚨 Incidente: {escapar(titulo_incidente(incidente))}"]
        dato = escapar(incidente.dato)
        cooldown = self._cooldown(incidente.fuente, self.reloj())
        if cooldown:
            dato = f"{dato} · cooldown {cooldown}" if dato else f"cooldown {cooldown}"
        if dato:
            lineas.append(dato)
        lineas.append(f"Diagnóstico IA no disponible (motivo: {escapar(motivo)})")
        return "\n".join(lineas)

    def _mensaje_diagnostico(self, incidente: Incidente, diag: Diagnostico) -> str:
        ahora = self.reloj()
        cabecera = f"Abierto desde: {_hora(incidente.abierto_desde, ahora)}"
        if cooldown := self._cooldown(incidente.fuente, ahora):
            cabecera += f" · cooldown {cooldown}"
        intervencion = "sí" if diag.requiere_intervencion else "no"
        partes = [
            f"🚨 <b>Incidente: {escapar(titulo_incidente(incidente))}</b> "
            f"(severidad {diag.severidad})",
            cabecera,
            "",
            "🔍 <b>Causa probable</b>",
            escapar(diag.causa_probable[:MAX_CAMPO]),
            "",
            "🛠 <b>Recomendación</b>",
            escapar(diag.accion_recomendada[:MAX_CAMPO]),
            "",
            f"📎 Evidencia: {escapar(diag.evidencia_clave[:MAX_CAMPO])}",
            f"⚠️ Requiere intervención: {intervencion}",
        ]
        sugerencia = (diag.sugerencia_tecnica or "").strip()
        if sugerencia and sugerencia.lower() not in ("null", "none", "n/a"):
            # Se muestra para que el administrador la revise; nunca se aplica sola
            partes += ["", "💡 Sugerencia técnica (revisar antes de aplicar):",
                       f"<pre>{escapar(sugerencia[:MAX_SUGERENCIA])}</pre>"]  # fmt: skip
        return "\n".join(partes)

    def _enviar(self, bloques: list[str]) -> bool:
        ok = True
        for mensaje in empaquetar(bloques):
            envio = self.notificador.enviar_mensaje(self.chat_id, mensaje)
            if not envio.ok:
                ok = False
                log.error("No se pudo enviar el aviso de incidentes: %s", envio.error)
        return ok

    def _aviso_saldo(self, ahora: datetime) -> str | None:
        """Aviso de saldo bajo, como máximo una vez al día."""
        hoy = ahora.astimezone(ZONA).date().isoformat()
        if self.ia is None or self.estado.kv_obtener("ultimo_aviso_saldo") == hoy:
            return None
        valor = self.ia.saldo()
        self.estado.kv_guardar("ultimo_aviso_saldo", hoy)
        return f"💳 Saldo DeepSeek bajo: ${valor:.2f}" if valor is not None else None

    # --- flujo ------------------------------------------------------------------------------

    def _diagnosticar(
        self, nuevos: list[Incidente], intentos: list[Intento], fuentes_ok: list[str]
    ) -> tuple[dict[str, Diagnostico], str | None]:
        """Una sola llamada a la IA para todos los incidentes nuevos de la corrida."""
        if not self.config.activo:
            return {}, "reportero IA desactivado"
        if self.ia is None:
            return {}, "sin clave de API"
        payload = {"incidentes": [self.evidencia(i, intentos, fuentes_ok) for i in nuevos]}
        respuesta: RespuestaIA = self.ia.chat_json(
            "reportero",
            self.config.prompt_sistema,
            payload,
            temperatura=self.config.temperatura,
            max_tokens=self.config.max_tokens * len(nuevos),
        )
        if not respuesta.ok or respuesta.datos is None:
            return {}, respuesta.motivo or "respuesta inválida"
        try:
            diagnosticos = RespuestaReportero.model_validate(respuesta.datos).diagnosticos
        except ValidationError:
            return {}, "respuesta inválida"
        por_clave: dict[str, Diagnostico] = {}
        for posicion, diag in enumerate(diagnosticos):
            clave = f"{diag.fuente}:{diag.tipo}"
            if clave not in {i.clave for i in nuevos} and posicion < len(nuevos):
                clave = nuevos[posicion].clave  # la IA no repitió fuente/tipo: vale el orden
            por_clave[clave] = diag
        return por_clave, None

    def notificar(
        self,
        resultado: ResultadoEvaluacion,
        intentos_corrida: list[Intento],
        fuentes_ok: list[str],
    ) -> None:
        ahora = self.reloj()
        bloques: list[str] = []

        for incidente in resultado.recuperados:
            fin = incidente.cerrado_en or ahora
            if incidente.fuente == RED[0]:
                desde = incidente.abierto_desde.astimezone(ZONA)
                bloques.append(
                    f"⚠️ El PC estuvo sin internet de {desde:%H:%M} a {fin.astimezone(ZONA):%H:%M}"
                    f" ({duracion(incidente.abierto_desde, fin)})"
                )
            else:
                bloques.append(
                    f"✅ {escapar(nombre_fuente(incidente.fuente))} se recuperó tras "
                    f"{duracion(incidente.abierto_desde, fin)} ({escapar(incidente.tipo)})"
                )

        # Sin red no se puede avisar: el aviso sale al volver la conexión
        nuevos = [i for i in resultado.nuevos if i.fuente != RED[0]]
        if nuevos:
            diagnosticos, motivo = self._diagnosticar(nuevos, intentos_corrida, fuentes_ok)
            for incidente in nuevos:
                diag = diagnosticos.get(incidente.clave)
                if diag is not None:
                    bloques.append(self._mensaje_diagnostico(incidente, diag))
                else:
                    bloques.append(self._alerta_plana(incidente, motivo or "respuesta incompleta"))
            if motivo == "saldo bajo" and (aviso := self._aviso_saldo(ahora)):
                bloques.append(aviso)

        for incidente in resultado.recordatorios:
            texto = (
                f"⏰ Sigue abierto desde hace {duracion(incidente.abierto_desde, ahora)}: "
                f"{escapar(titulo_incidente(incidente))}"
            )
            if incidente.dato:
                texto += f"\n{escapar(incidente.dato)}"
            bloques.append(texto)

        if not bloques:
            return
        if self._enviar(bloques):
            for incidente in nuevos + resultado.recordatorios:
                self.detector.marcar_reportado(incidente, ahora)
