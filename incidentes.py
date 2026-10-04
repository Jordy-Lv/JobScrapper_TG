"""Detección determinista de incidentes, apertura, cierre y recordatorios (sin IA)."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import config as cfg
from estado import Estado, a_texto, de_texto

log = logging.getLogger(__name__)

TIPOS = (
    "bloqueo",
    "captcha",
    "cambio_html",
    "sin_resultados",
    "caida_volumen",
    "error_servidor",
    "fallo_envio",
)
RED = ("red", "sin_conexion")
TELEGRAM = "telegram"


@dataclass
class Incidente:
    fuente: str
    tipo: str
    abierto_desde: datetime
    dato: str = ""  # dato principal de la evidencia, apto para la alerta plana
    id: int | None = None
    cerrado_en: datetime | None = None
    ultimo_reporte: datetime | None = None

    @property
    def clave(self) -> str:
        return f"{self.fuente}:{self.tipo}"


@dataclass
class ResultadoEvaluacion:
    nuevos: list[Incidente] = field(default_factory=list)
    recuperados: list[Incidente] = field(default_factory=list)
    recordatorios: list[Incidente] = field(default_factory=list)

    @property
    def vacio(self) -> bool:
        return not (self.nuevos or self.recuperados or self.recordatorios)


@dataclass
class EstadoFuente:
    """Lo que pasó con una fuente en la corrida actual."""

    consultada: bool = False
    exito: bool = False  # al menos una respuesta 2xx sin desafío
    bloqueo: bool = False
    captcha: bool = False
    cambio_html: bool = False


class Detector:
    def __init__(self, estado: Estado, config: cfg.Incidentes) -> None:
        self.estado = estado
        self.config = config

    # --- persistencia -----------------------------------------------------------------------

    def abiertos(self) -> dict[str, Incidente]:
        filas = self.estado.cx.execute(
            "SELECT * FROM incidentes WHERE cerrado_en IS NULL ORDER BY id"
        ).fetchall()
        salida = {}
        for f in filas:
            detalle = json.loads(f["detalle_json"] or "{}")
            incidente = Incidente(
                fuente=f["fuente"],
                tipo=f["tipo"],
                abierto_desde=de_texto(f["abierto_desde"]),
                dato=detalle.get("dato", ""),
                id=f["id"],
                ultimo_reporte=de_texto(f["ultimo_reporte"]),
            )
            salida[incidente.clave] = incidente
        return salida

    def _abrir(self, fuente: str, tipo: str, dato: str, ahora: datetime) -> Incidente:
        incidente = Incidente(fuente, tipo, ahora, dato)
        with self.estado.transaccion() as cx:
            incidente.id = cx.execute(
                "INSERT INTO incidentes(fuente, tipo, abierto_desde, detalle_json) "
                "VALUES (?, ?, ?, ?)",
                (fuente, tipo, a_texto(ahora), json.dumps({"dato": dato}, ensure_ascii=False)),
            ).lastrowid
        log.warning("Incidente abierto: %s (%s)", incidente.clave, dato)
        return incidente

    def _cerrar(self, incidente: Incidente, ahora: datetime) -> None:
        incidente.cerrado_en = ahora
        with self.estado.transaccion() as cx:
            cx.execute(
                "UPDATE incidentes SET cerrado_en = ? WHERE id = ?", (a_texto(ahora), incidente.id)
            )
        log.info("Incidente cerrado: %s", incidente.clave)

    def marcar_reportado(self, incidente: Incidente, ahora: datetime) -> None:
        incidente.ultimo_reporte = ahora
        with self.estado.transaccion() as cx:
            cx.execute(
                "UPDATE incidentes SET ultimo_reporte = ? WHERE id = ?",
                (a_texto(ahora), incidente.id),
            )

    # --- consultas sobre el historial -----------------------------------------------------

    def _corridas_de_fuente(self, fuente: str, cantidad: int) -> list[list]:
        """Intentos agrupados de las últimas corridas en que se consultó la fuente.

        Las corridas sin red y los dry-run no cuentan para las reglas de "corridas seguidas".
        """
        filas = self.estado.cx.execute(
            """
            SELECT i.corrida_id, i.status, i.tipo_error
            FROM intentos i JOIN corridas c ON c.id = i.corrida_id
            WHERE i.fuente = ? AND c.sin_red = 0 AND c.modo != 'dry-run'
              AND i.corrida_id IN (
                SELECT DISTINCT i2.corrida_id FROM intentos i2
                JOIN corridas c2 ON c2.id = i2.corrida_id
                WHERE i2.fuente = ? AND c2.sin_red = 0 AND c2.modo != 'dry-run'
                ORDER BY i2.corrida_id DESC LIMIT ?)
            ORDER BY i.corrida_id DESC
            """,
            (fuente, fuente, cantidad),
        ).fetchall()
        por_corrida: dict[int, list] = {}
        for f in filas:
            por_corrida.setdefault(f["corrida_id"], []).append(f)
        return list(por_corrida.values())

    def _items(self, fuente: str, desde: datetime, hasta: datetime) -> tuple[int, int]:
        """(vacantes crudas, respuestas 2xx) de una fuente en [desde, hasta], sin dry-run.

        Solo una respuesta 2xx cuenta como "la fuente respondió": un bloqueo o un 5xx no es
        "0 resultados" y ya tiene su propio incidente.
        """
        fila = self.estado.cx.execute(
            "SELECT COALESCE(SUM(i.items), 0) AS items, "
            "COUNT(CASE WHEN i.status BETWEEN 200 AND 299 THEN 1 END) AS respuestas "
            "FROM intentos i LEFT JOIN corridas c ON c.id = i.corrida_id "
            "WHERE i.fuente = ? AND i.ts >= ? AND i.ts <= ? "
            "AND COALESCE(c.modo, '') != 'dry-run'",
            (fuente, a_texto(desde), a_texto(hasta)),
        ).fetchone()
        return fila["items"], fila["respuestas"]

    def _primer_intento(self, fuente: str) -> datetime | None:
        fila = self.estado.cx.execute(
            "SELECT MIN(ts) AS ts FROM intentos WHERE fuente = ?", (fuente,)
        ).fetchone()
        return de_texto(fila["ts"])

    def _escalon(self, fuente: str) -> int:
        fila = self.estado.cx.execute(
            "SELECT escalon, cooldown_hasta FROM fuentes_estado WHERE fuente = ?", (fuente,)
        ).fetchone()
        return fila["escalon"] if fila and fila["cooldown_hasta"] else 0

    # --- reglas ---------------------------------------------------------------------------

    def _estado_corrida(self, corrida_id: int, fuente: str) -> EstadoFuente:
        filas = self.estado.cx.execute(
            "SELECT status, tipo_error, desafio FROM intentos WHERE corrida_id = ? AND fuente = ?",
            (corrida_id, fuente),
        ).fetchall()
        resultado = EstadoFuente(consultada=bool(filas))
        for f in filas:
            ok = f["status"] is not None and 200 <= f["status"] < 300 and not f["desafio"]
            resultado.exito |= ok and f["tipo_error"] != "cambio_html"
            resultado.bloqueo |= f["tipo_error"] == "bloqueo"
            resultado.captcha |= bool(f["desafio"])
            resultado.cambio_html |= f["tipo_error"] == "cambio_html"
        return resultado

    def _condiciones(self, fuente: str, actual: EstadoFuente, ahora: datetime) -> dict[str, str]:
        """Tipos de incidente cuya regla se cumple ahora, con su dato principal."""
        condiciones: dict[str, str] = {}
        if actual.consultada:
            recientes = self._corridas_de_fuente(fuente, self.config.corridas_bloqueo)
            seguidas = len(recientes) >= self.config.corridas_bloqueo and all(
                any(f["tipo_error"] == "bloqueo" for f in corrida) for corrida in recientes
            )
            escalon = self._escalon(fuente)
            if actual.bloqueo and (seguidas or escalon >= 1):
                condiciones["bloqueo"] = (
                    f"HTTP 429/403/999 en {self.config.corridas_bloqueo} corridas seguidas"
                    if seguidas
                    else "cooldown escalado a 6 h o más"
                )
            if actual.captcha:
                condiciones["captcha"] = "respuesta 200 con página de desafío anti-bot"
            if actual.cambio_html:
                condiciones["cambio_html"] = "respuesta 200 sin la estructura esperada del listado"

            n = self.config.corridas_error_servidor
            ultimas = self._corridas_de_fuente(fuente, n)
            if len(ultimas) >= n and all(
                any(f["tipo_error"] in ("servidor", "timeout") for f in corrida)
                and not any(f["status"] is not None and f["status"] < 300 for f in corrida)
                for corrida in ultimas
            ):
                condiciones["error_servidor"] = f"HTTP 5xx o timeouts en {n} corridas seguidas"

        items_24h, respuestas_24h = self._items(fuente, ahora - timedelta(hours=24), ahora)
        items_7d, _ = self._items(
            fuente, ahora - timedelta(days=8), ahora - timedelta(hours=24, seconds=1)
        )
        if respuestas_24h and items_24h == 0 and items_7d > 0:
            condiciones["sin_resultados"] = "0 vacantes en 24 h; hubo resultados los 7 días previos"
        primero = self._primer_intento(fuente)
        historia_completa = primero is not None and primero <= ahora - timedelta(days=8)
        promedio = items_7d / 7
        if (
            historia_completa
            and items_24h > 0
            and promedio > 0
            and items_24h < self.config.umbral_caida_volumen * promedio
        ):
            condiciones["caida_volumen"] = (
                f"{items_24h} vacantes en 24 h frente a un promedio de {promedio:.0f} por día"
            )
        return condiciones

    @staticmethod
    def _recuperada(tipo: str, actual: EstadoFuente, condiciones: dict[str, str]) -> bool:
        if tipo in ("sin_resultados", "caida_volumen"):
            return tipo not in condiciones
        if tipo == "cambio_html":
            return actual.consultada and not actual.cambio_html and actual.exito
        # bloqueo, captcha y error_servidor se cierran con una respuesta exitosa
        return actual.exito

    # --- evaluación -------------------------------------------------------------------------

    def evaluar(
        self,
        corrida_id: int,
        ahora: datetime,
        fuentes: list[str],
        *,
        sin_red: bool = False,
        rechazos_envio: list[str] | None = None,
        envio_exitoso: bool = False,
    ) -> ResultadoEvaluacion:
        """Abre, cierra y recuerda incidentes según lo ocurrido en la corrida."""
        resultado = ResultadoEvaluacion()
        abiertos = self.abiertos()
        clave_red = ":".join(RED)

        if sin_red:
            # Sin internet: un único incidente; nada por fuente ni cooldowns
            if clave_red not in abiertos:
                incidente = self._abrir(*RED, "todas las fuentes fallaron por conexión/DNS", ahora)
                resultado.nuevos.append(incidente)
            return resultado
        if clave_red in abiertos:
            incidente = abiertos.pop(clave_red)
            self._cerrar(incidente, ahora)
            resultado.recuperados.append(incidente)

        for fuente in fuentes:
            actual = self._estado_corrida(corrida_id, fuente)
            condiciones = self._condiciones(fuente, actual, ahora)
            for tipo, dato in condiciones.items():
                if f"{fuente}:{tipo}" not in abiertos:
                    resultado.nuevos.append(self._abrir(fuente, tipo, dato, ahora))
            for clave, incidente in list(abiertos.items()):
                if incidente.fuente == fuente and self._recuperada(
                    incidente.tipo, actual, condiciones
                ):
                    self._cerrar(incidente, ahora)
                    resultado.recuperados.append(incidente)
                    del abiertos[clave]

        clave_envio = f"{TELEGRAM}:fallo_envio"
        if rechazos_envio:
            if clave_envio not in abiertos:
                resultado.nuevos.append(
                    self._abrir(TELEGRAM, "fallo_envio", rechazos_envio[0][:300], ahora)
                )
        elif envio_exitoso and clave_envio in abiertos:
            incidente = abiertos.pop(clave_envio)
            self._cerrar(incidente, ahora)
            resultado.recuperados.append(incidente)

        limite = timedelta(hours=self.config.horas_recordatorio)
        for incidente in abiertos.values():
            referencia = incidente.ultimo_reporte or incidente.abierto_desde
            if ahora - referencia >= limite:
                resultado.recordatorios.append(incidente)
        return resultado
