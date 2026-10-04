"""Clase base de las fuentes: cliente HTTP, ritmo, presupuesto, desafíos, cooldown e intentos."""

from __future__ import annotations

import logging
import random
import re
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

import httpx

import config as cfg
from estado import Estado, a_texto, de_texto
from modelo import Vacante
from rotacion import Consulta

STATUS_BLOQUEO = {403, 429, 999}
CABECERAS_PERMITIDAS = {"retry-after", "server", "content-type", "cf-ray"}
MAX_CUERPO_GUARDADO = 50_000


class TipoError(StrEnum):
    BLOQUEO = "bloqueo"
    CAPTCHA = "captcha"
    CAMBIO_HTML = "cambio_html"
    SERVIDOR = "servidor"
    TIMEOUT = "timeout"
    CONEXION = "conexion"  # error de conexión o DNS: posible falla de red local
    TRANSPORTE = "transporte"
    HTTP = "http"


class CambioHTML(Exception):
    """El parser no encuentra la estructura esperada en una respuesta normal."""


@dataclass
class Peticion:
    url: str
    metodo: str = "GET"
    params: dict[str, Any] | None = None
    json: Any = None
    cabeceras: dict[str, str] | None = None


@dataclass
class Intento:
    ts: datetime
    fuente: str
    keyword: str
    url: str
    status: int | None = None
    ms: int = 0
    items: int = 0
    tipo_error: TipoError | None = None
    desafio: bool = False
    cabeceras: dict[str, str] = field(default_factory=dict)
    cuerpo: str = ""
    detalle: str | None = None

    @property
    def con_respuesta(self) -> bool:
        return self.status is not None


@dataclass
class ResultadoFuente:
    fuente: str
    vacantes: list[Vacante] = field(default_factory=list)
    intentos: list[Intento] = field(default_factory=list)
    ejecutadas: list[Consulta] = field(default_factory=list)
    cooldown_hasta: datetime | None = None


def filtrar_cabeceras(cabeceras: httpx.Headers | dict[str, str]) -> dict[str, str]:
    return {
        k.lower(): v
        for k, v in cabeceras.items()
        if k.lower() in CABECERAS_PERMITIDAS or k.lower().startswith("x-ratelimit-")
    }


def _es_html(respuesta: httpx.Response) -> bool:
    tipo = respuesta.headers.get("content-type", "").lower()
    return "html" in tipo or (not tipo and respuesta.text.lstrip()[:1] == "<")


class Fuente(ABC):
    """Una fuente define cómo construir la petición de una palabra clave y cómo parsearla."""

    nombre: str = ""
    selectores: list[str] = []

    def __init__(
        self,
        config_fuente: cfg.Fuente,
        config_red: cfg.Red,
        estado: Estado,
        corrida_id: int | None = None,
        *,
        cliente: httpx.Client | None = None,
        dormir: Callable[[float], None] = time.sleep,
        aleatorio: Callable[[float, float], float] = random.uniform,
        reloj: Callable[[], datetime] | None = None,
    ) -> None:
        self.config = config_fuente
        self.red = config_red
        self.estado = estado
        self.corrida_id = corrida_id
        self.opciones = config_fuente.opciones
        self.dormir = dormir
        self.aleatorio = aleatorio
        self.reloj = reloj or (lambda: datetime.now().astimezone())
        self.log = logging.getLogger(f"fuentes.{self.nombre}")
        self.cliente = cliente or httpx.Client(
            headers={
                "User-Agent": config_red.user_agent,
                "Accept-Language": config_red.accept_language,
            },
            timeout=config_red.timeout_s,
            follow_redirects=True,
        )
        self._marcadores = re.compile(
            "|".join(re.escape(m.lower()) for m in config_red.marcadores_desafio) or r"(?!x)x"
        )

    # --- a implementar por cada fuente ---------------------------------------------------

    @abstractmethod
    def construir_peticion(self, keyword: str) -> Peticion: ...

    @abstractmethod
    def parsear(self, respuesta: httpx.Response, keyword: str, ahora: datetime) -> list[Vacante]:
        """Devuelve las vacantes; lanza CambioHTML si falta la estructura esperada."""

    # --- estado de la fuente ------------------------------------------------------------

    def _fila_estado(self) -> dict[str, Any]:
        fila = self.estado.cx.execute(
            "SELECT * FROM fuentes_estado WHERE fuente = ?", (self.nombre,)
        ).fetchone()
        if fila:
            return dict(fila)
        return {
            "fuente": self.nombre,
            "cooldown_hasta": None,
            "escalon": 0,
            "fallos_consecutivos": 0,
            "ultimo_exito": None,
        }

    def _guardar_estado(self, fila: dict[str, Any]) -> None:
        with self.estado.transaccion() as cx:
            cx.execute(
                """
                INSERT INTO fuentes_estado(fuente, cooldown_hasta, escalon, fallos_consecutivos,
                                           ultimo_exito)
                VALUES (:fuente, :cooldown_hasta, :escalon, :fallos_consecutivos, :ultimo_exito)
                ON CONFLICT(fuente) DO UPDATE SET
                    cooldown_hasta = excluded.cooldown_hasta,
                    escalon = excluded.escalon,
                    fallos_consecutivos = excluded.fallos_consecutivos,
                    ultimo_exito = excluded.ultimo_exito
                """,
                fila,
            )

    def cooldown_vigente(self, ahora: datetime) -> datetime | None:
        hasta = de_texto(self._fila_estado()["cooldown_hasta"])
        return hasta if hasta and hasta > ahora else None

    def aplicar_cooldown(self, ahora: datetime) -> datetime:
        """2 h la primera vez, 6 h la segunda consecutiva y 24 h desde la tercera."""
        fila = self._fila_estado()
        escalones = self.red.cooldown_horas
        escalon = min(fila["fallos_consecutivos"], len(escalones) - 1)
        hasta = ahora + timedelta(hours=escalones[escalon])
        fila.update(
            cooldown_hasta=a_texto(hasta),
            escalon=escalon,
            fallos_consecutivos=fila["fallos_consecutivos"] + 1,
        )
        self._guardar_estado(fila)
        self.log.warning("%s en cooldown %s h hasta %s", self.nombre, escalones[escalon], hasta)
        return hasta

    def registrar_exito(self, ahora: datetime) -> None:
        fila = self._fila_estado()
        fila.update(
            cooldown_hasta=None, escalon=0, fallos_consecutivos=0, ultimo_exito=a_texto(ahora)
        )
        self._guardar_estado(fila)

    def _registrar_intento(self, intento: Intento) -> None:
        with self.estado.transaccion() as cx:
            cx.execute(
                """
                INSERT INTO intentos(ts, corrida_id, fuente, keyword, url, status, ms, items,
                                     tipo_error, desafio)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    a_texto(intento.ts),
                    self.corrida_id,
                    intento.fuente,
                    intento.keyword,
                    intento.url,
                    intento.status,
                    intento.ms,
                    intento.items,
                    intento.tipo_error.value if intento.tipo_error else None,
                    int(intento.desafio),
                ),
            )

    # --- ejecución ------------------------------------------------------------------------

    def _hacer_request(self, peticion: Peticion) -> httpx.Response:
        return self.cliente.request(
            peticion.metodo,
            peticion.url,
            params=peticion.params,
            json=peticion.json,
            headers=peticion.cabeceras,
        )

    def consultar(self, consulta: Consulta) -> tuple[Intento, list[Vacante]]:
        """Hace un request, lo clasifica y lo registra. Nunca lanza excepciones de red."""
        ahora = self.reloj()
        peticion = self.construir_peticion(consulta.keyword)
        intento = Intento(ts=ahora, fuente=self.nombre, keyword=consulta.keyword, url=peticion.url)
        vacantes: list[Vacante] = []
        inicio = time.monotonic()
        try:
            respuesta = self._hacer_request(peticion)
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            intento.tipo_error, intento.detalle = TipoError.CONEXION, repr(exc)
        except httpx.TimeoutException as exc:
            intento.tipo_error, intento.detalle = TipoError.TIMEOUT, repr(exc)
        except httpx.HTTPError as exc:
            intento.tipo_error, intento.detalle = TipoError.TRANSPORTE, repr(exc)
        else:
            intento.url = str(respuesta.url)
            intento.status = respuesta.status_code
            intento.cabeceras = filtrar_cabeceras(respuesta.headers)
            intento.cuerpo = respuesta.text[:MAX_CUERPO_GUARDADO]
            vacantes = self._clasificar_respuesta(respuesta, intento, consulta.keyword, ahora)
        intento.ms = int((time.monotonic() - inicio) * 1000)
        intento.items = len(vacantes)
        self._registrar_intento(intento)
        self.log.info(
            "%s %r → %s %s ms, %s items%s",
            self.nombre,
            consulta.keyword,
            intento.status or "-",
            intento.ms,
            intento.items,
            f" [{intento.tipo_error}]" if intento.tipo_error else "",
        )
        return intento, vacantes

    def _clasificar_respuesta(
        self, respuesta: httpx.Response, intento: Intento, keyword: str, ahora: datetime
    ) -> list[Vacante]:
        status = respuesta.status_code
        if status in STATUS_BLOQUEO:
            intento.tipo_error = TipoError.BLOQUEO
            return []
        if status >= 500:
            intento.tipo_error = TipoError.SERVIDOR
            return []
        if status >= 400 or status < 200:
            intento.tipo_error = TipoError.HTTP
            return []
        # Las páginas de desafío son HTML; en JSON la palabra "challenge" puede ser contenido
        if _es_html(respuesta) and self._marcadores.search(respuesta.text.lower()):
            intento.tipo_error, intento.desafio = TipoError.CAPTCHA, True
            return []
        try:
            return self.parsear(respuesta, keyword, ahora)
        except CambioHTML as exc:
            intento.tipo_error, intento.detalle = TipoError.CAMBIO_HTML, str(exc)
        except Exception as exc:  # noqa: BLE001 - un parser roto no debe tumbar la corrida
            intento.tipo_error, intento.detalle = TipoError.CAMBIO_HTML, repr(exc)
            self.log.exception("Error parseando %s", self.nombre)
        return []

    def ejecutar(self, lote: list[Consulta]) -> ResultadoFuente:
        """Recorre el lote respetando presupuesto y pausas. Se detiene ante un bloqueo."""
        resultado = ResultadoFuente(self.nombre)
        for numero, consulta in enumerate(lote[: self.config.presupuesto]):
            if numero:
                self.dormir(self.aleatorio(self.red.pausa_min_s, self.red.pausa_max_s))
            intento, vacantes = self.consultar(consulta)
            resultado.intentos.append(intento)
            resultado.ejecutadas.append(consulta)
            resultado.vacantes.extend(vacantes)
            if intento.tipo_error in (TipoError.BLOQUEO, TipoError.CAPTCHA):
                resultado.cooldown_hasta = self.aplicar_cooldown(intento.ts)
                break
            if intento.status is not None and 200 <= intento.status < 300:
                self.registrar_exito(intento.ts)
        return resultado

    def cerrar(self) -> None:
        self.cliente.close()
