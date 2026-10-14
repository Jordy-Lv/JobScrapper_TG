"""Clase base de las fuentes: cliente HTTP, ritmo, presupuesto, desafíos, cooldown e intentos."""

from __future__ import annotations

import logging
import random
import re
import ssl
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from enum import StrEnum
from typing import Any

import httpx

from buscador_vacantes import config as cfg
from buscador_vacantes.estado import Estado, a_texto, de_texto
from buscador_vacantes.modelo import Vacante
from buscador_vacantes.rotacion import Consulta

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


class ResultadoDetalle(StrEnum):
    OK = "ok"  # hay descripción
    CERRADA = "cerrada"  # la oferta ya no existe (404 o 410)
    BLOQUEADA = "bloqueada"  # 403, 429, 999 o desafío: aplica el cooldown de la fuente
    FALLO = "fallo"  # temporal: la oferta se reintenta más tarde


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
class RespuestaDetalle:
    resultado: ResultadoDetalle
    texto: str | None = None
    error: str | None = None  # motivo del fallo, para la cola
    cooldown_hasta: datetime | None = None
    intento: Intento | None = None


@dataclass
class ResultadoFuente:
    fuente: str
    vacantes: list[Vacante] = field(default_factory=list)
    intentos: list[Intento] = field(default_factory=list)
    ejecutadas: list[Consulta] = field(default_factory=list)
    cooldown_hasta: datetime | None = None


def segundos_retry_after(valor: str | None, ahora: datetime) -> float | None:
    """Segundos de la cabecera Retry-After (número o fecha HTTP); ``None`` si no se entiende."""
    if not valor or not valor.strip():
        return None
    valor = valor.strip()
    try:
        segundos = float(valor)
    except ValueError:
        try:
            fecha = parsedate_to_datetime(valor)
        except (TypeError, ValueError):
            return None
        if fecha.tzinfo is None:
            fecha = fecha.replace(tzinfo=UTC)
        segundos = (fecha - ahora).total_seconds()
    return segundos if 0 < segundos < float("inf") else None


def _recortar(texto: str, maximo: int = 80) -> str:
    """Las consultas combinadas con OR son largas: el log solo muestra el comienzo."""
    return texto if len(texto) <= maximo else texto[: maximo - 1] + "…"


def filtrar_cabeceras(cabeceras: httpx.Headers | dict[str, str]) -> dict[str, str]:
    return {
        k.lower(): v
        for k, v in cabeceras.items()
        if k.lower() in CABECERAS_PERMITIDAS or k.lower().startswith("x-ratelimit-")
    }


class Fuente(ABC):
    """Una fuente define cómo construir la petición de una palabra clave y cómo parsearla."""

    nombre: str = ""
    selectores: list[str] = []
    # Códigos HTTP que la fuente usa para "sin resultados" (p. ej. elempleo responde 404)
    status_sin_resultados: frozenset[int] = frozenset()
    # Paginación de las consultas del núcleo: una página con menos de ``tamano_pagina``
    # vacantes es la última y no se piden las siguientes
    soporta_paginas: bool = False
    tamano_pagina: int = 20
    # Fuentes que no usan la rotación de palabras clave (p. ej. el SPE con su filtro de
    # prácticas): la corrida pide las páginas 1..presupuesto con esta consulta
    consulta_fija: str | None = None
    # Variante de búsqueda de esta corrida (una de opciones.variantes, elegida por la corrida
    # en orden circular); la fuente que la soporta la combina con sus opciones
    variante: dict[str, Any] | None = None
    # Posición de la variante en opciones.variantes; forma parte de la clave de los sondeos
    variante_id: int = 0
    # False en un dry-run: la fuente no escribe estado (sondeos, ritmo) que mueva corridas reales
    persistir_estado: bool = True
    # La fuente sabe leer la página de detalle de una oferta (``obtener_detalle``)
    soporta_detalle: bool = False

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
            verify=self.verificacion_tls(),
        )
        self._marcadores = re.compile(
            "|".join(re.escape(m.lower()) for m in config_red.marcadores_desafio) or r"(?!x)x"
        )

    # --- a implementar por cada fuente ---------------------------------------------------

    def pagina_completa(self, vacantes: list[Vacante]) -> bool:
        """Si la última página leída venía llena (puede haber más páginas)."""
        return len(vacantes) >= self.tamano_pagina

    def verificacion_tls(self) -> ssl.SSLContext | bool:
        """Verificación TLS del cliente. Nunca se desactiva; una fuente puede ampliar la cadena."""
        return True

    @abstractmethod
    def construir_peticion(self, keyword: str, pagina: int = 1) -> Peticion: ...

    @abstractmethod
    def parsear(self, respuesta: httpx.Response, keyword: str, ahora: datetime) -> list[Vacante]:
        """Devuelve las vacantes; lanza CambioHTML si falta la estructura esperada."""

    def peticion_detalle(self, vacante: Vacante) -> Peticion:
        raise NotImplementedError(f"{self.nombre} no obtiene el detalle de las ofertas")

    def extraer_detalle(self, respuesta: httpx.Response) -> str | None:
        """Descripción de la página de detalle; ``None`` si no se reconoce."""
        raise NotImplementedError(f"{self.nombre} no obtiene el detalle de las ofertas")

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

    def aplicar_cooldown(self, ahora: datetime, minimo_s: float | None = None) -> datetime:
        """2 h la primera vez, 6 h la segunda consecutiva y 24 h desde la tercera.

        ``minimo_s`` (el Retry-After del bloqueo) alarga el cooldown si supera al escalón, con el
        tope ``red.retry_after_max_h``.
        """
        fila = self._fila_estado()
        escalones = self.red.cooldown_horas
        escalon = min(fila["fallos_consecutivos"], len(escalones) - 1)
        duracion = timedelta(hours=escalones[escalon])
        if minimo_s:
            pedido = timedelta(seconds=min(minimo_s, self.red.retry_after_max_h * 3600))
            duracion = max(duracion, pedido)
        hasta = ahora + duracion
        fila.update(
            cooldown_hasta=a_texto(hasta),
            escalon=escalon,
            fallos_consecutivos=fila["fallos_consecutivos"] + 1,
        )
        self._guardar_estado(fila)
        self.log.warning(
            "%s en cooldown %.4g h hasta %s", self.nombre, duracion.total_seconds() / 3600, hasta
        )
        return hasta

    def registrar_exito(self, ahora: datetime) -> None:
        fila = self._fila_estado()
        fila.update(
            cooldown_hasta=None, escalon=0, fallos_consecutivos=0, ultimo_exito=a_texto(ahora)
        )
        self._guardar_estado(fila)

    # --- ritmo adaptativo ------------------------------------------------------------------

    def _clave_ritmo(self, campo: str) -> str:
        return f"ritmo:{self.nombre}:{campo}"

    def _nivel_ritmo(self) -> int:
        try:
            nivel = int(self.estado.kv_obtener(self._clave_ritmo("nivel")) or 0)
        except ValueError:
            nivel = 0
        return max(0, min(nivel, len(self.config.ritmo.intervalos_min) - 1))

    def ritmo_espera(self, ahora: datetime) -> float | None:
        """Minutos del intervalo vigente si todavía no toca consultar la fuente; si toca, ``None``.

        Sin ``ritmo`` en la configuración, la fuente se consulta en cada corrida. La tolerancia
        absorbe la demora aleatoria del timer.
        """
        if self.config.ritmo is None:
            return None
        ultima = de_texto(self.estado.kv_obtener(self._clave_ritmo("ultima")))
        if ultima is None:
            return None
        intervalo = self.config.ritmo.intervalos_min[self._nivel_ritmo()]
        transcurrido = (ahora - ultima).total_seconds() / 60
        return intervalo if transcurrido < intervalo - self.config.ritmo.tolerancia_min else None

    def ritmo_adaptado(self) -> bool:
        """Si un bloqueo reciente subió el intervalo mínimo entre peticiones de la fuente."""
        return self.config.ritmo is not None and self._nivel_ritmo() > 0

    def _actualizar_ritmo(self, intento: Intento, bloqueo: bool, exito: bool) -> None:
        """Anota la petición; sube de nivel con un bloqueo y baja tras varias exitosas seguidas."""
        ritmo = self.config.ritmo
        if ritmo is None or not self.persistir_estado:
            return
        estado = self.estado
        estado.kv_guardar(self._clave_ritmo("ultima"), a_texto(intento.ts))
        nivel = self._nivel_ritmo()
        limpias = int(estado.kv_obtener(self._clave_ritmo("limpias")) or 0)
        if bloqueo:
            nivel, limpias = min(nivel + 1, len(ritmo.intervalos_min) - 1), 0
            self.log.warning(
                "%s: ritmo adaptado a %g min entre peticiones",
                self.nombre,
                ritmo.intervalos_min[nivel],
            )
        elif exito:
            limpias += 1
            if nivel > 0 and limpias >= ritmo.limpias_para_bajar:
                nivel, limpias = nivel - 1, 0
                self.log.info(
                    "%s: ritmo recuperado a %g min entre peticiones",
                    self.nombre,
                    ritmo.intervalos_min[nivel],
                )
            elif nivel == 0:
                limpias = 0
        estado.kv_guardar(self._clave_ritmo("nivel"), str(nivel))
        estado.kv_guardar(self._clave_ritmo("limpias"), str(limpias))

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
        peticion = self.construir_peticion(consulta.keyword, consulta.pagina)
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
            "%s %r%s → %s %s ms, %s items%s",
            self.nombre,
            _recortar(consulta.keyword),
            f" p{consulta.pagina}" if consulta.pagina > 1 else "",
            intento.status or "-",
            intento.ms,
            intento.items,
            f" [{intento.tipo_error}]" if intento.tipo_error else "",
        )
        return intento, vacantes

    def pausar_detalle(self) -> None:
        """Pausa propia del detalle entre dos peticiones (más lenta que la de la búsqueda)."""
        detalle = self.config.detalle
        if detalle is not None:
            self.dormir(self.aleatorio(detalle.pausa_min_s, detalle.pausa_max_s))

    def obtener_detalle(self, vacante: Vacante) -> RespuestaDetalle:
        """Pide la página de detalle de una oferta. Nunca lanza excepciones de red.

        Cada petición queda registrada como un intento de la fuente (``keyword = "detalle <id>"``).
        Un bloqueo aplica el cooldown de la fuente y sube su ritmo adaptativo, igual que en la
        búsqueda; la corrida debe dejar de pedir detalles.
        """
        if not self.soporta_detalle:
            raise NotImplementedError(f"{self.nombre} no obtiene el detalle de las ofertas")
        ahora = self.reloj()
        peticion = self.peticion_detalle(vacante)
        intento = Intento(
            ts=ahora, fuente=self.nombre, keyword=f"detalle {vacante.id_fuente}", url=peticion.url
        )
        respuesta_detalle = RespuestaDetalle(ResultadoDetalle.FALLO, intento=intento)
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
            self._clasificar_detalle(respuesta, intento, respuesta_detalle)
        intento.ms = int((time.monotonic() - inicio) * 1000)
        if intento.tipo_error:
            respuesta_detalle.error = str(intento.tipo_error)
        self._registrar_intento(intento)
        self.log.info(
            "%s detalle %s → %s %s ms, %s%s",
            self.nombre,
            vacante.id_fuente,
            intento.status or "-",
            intento.ms,
            respuesta_detalle.resultado.value,
            f" [{intento.tipo_error}]" if intento.tipo_error else "",
        )
        if respuesta_detalle.resultado == ResultadoDetalle.BLOQUEADA:
            espera = segundos_retry_after(intento.cabeceras.get("retry-after"), intento.ts)
            respuesta_detalle.cooldown_hasta = self.aplicar_cooldown(intento.ts, espera)
            self._actualizar_ritmo(intento, bloqueo=True, exito=False)
        return respuesta_detalle

    def _clasificar_detalle(
        self, respuesta: httpx.Response, intento: Intento, resultado: RespuestaDetalle
    ) -> None:
        status = respuesta.status_code
        if status in (404, 410):
            resultado.resultado = ResultadoDetalle.CERRADA
        elif status in STATUS_BLOQUEO:
            intento.tipo_error = TipoError.BLOQUEO
            resultado.resultado = ResultadoDetalle.BLOQUEADA
        elif status >= 500:
            intento.tipo_error = TipoError.SERVIDOR
        elif status >= 400 or status < 200:
            intento.tipo_error = TipoError.HTTP
        else:
            texto = self.extraer_detalle(respuesta)
            if texto:
                resultado.resultado, resultado.texto = ResultadoDetalle.OK, texto
            elif self._marcadores.search(respuesta.text.lower()):
                intento.tipo_error, intento.desafio = TipoError.CAPTCHA, True
                resultado.resultado = ResultadoDetalle.BLOQUEADA
            else:
                intento.tipo_error = TipoError.CAMBIO_HTML
                intento.detalle = "la página de detalle no trae un bloque de descripción"

    def _clasificar_respuesta(
        self, respuesta: httpx.Response, intento: Intento, keyword: str, ahora: datetime
    ) -> list[Vacante]:
        status = respuesta.status_code
        if status in self.status_sin_resultados:
            return []
        if status in STATUS_BLOQUEO:
            intento.tipo_error = TipoError.BLOQUEO
            return []
        if status >= 500:
            intento.tipo_error = TipoError.SERVIDOR
            return []
        if status >= 400 or status < 200:
            intento.tipo_error = TipoError.HTTP
            return []
        # Se parsea primero: un marcador de desafío solo cuenta si falta el listado, porque
        # hay sitios con reCAPTCHA en formularios de todas sus páginas (elempleo)
        try:
            return self.parsear(respuesta, keyword, ahora)
        except CambioHTML as exc:
            intento.tipo_error, intento.detalle = TipoError.CAMBIO_HTML, str(exc)
        except Exception as exc:  # noqa: BLE001 - un parser roto no debe tumbar la corrida
            intento.tipo_error, intento.detalle = TipoError.CAMBIO_HTML, repr(exc)
            self.log.exception("Error parseando %s", self.nombre)
        if self._marcadores.search(respuesta.text.lower()):
            intento.tipo_error, intento.desafio = TipoError.CAPTCHA, True
        return []

    def ejecutar(self, lote: list[Consulta]) -> ResultadoFuente:
        """Recorre el lote respetando presupuesto y pausas. Se detiene ante un bloqueo.

        Las páginas siguientes de una palabra clave se omiten si la anterior falló o vino
        incompleta (era la última página).
        """
        resultado = ResultadoFuente(self.nombre)
        sin_mas_paginas: set[str] = set()
        # La pausa propia de la fuente manda sobre la global
        pausa_min, pausa_max = self.config.pausa_min_s, self.config.pausa_max_s
        if pausa_min is None or pausa_max is None:
            pausa_min, pausa_max = self.red.pausa_min_s, self.red.pausa_max_s
        for consulta in lote[: self.config.presupuesto]:
            if consulta.pagina > 1 and consulta.keyword in sin_mas_paginas:
                continue
            if resultado.intentos:
                self.dormir(self.aleatorio(pausa_min, pausa_max))
            intento, vacantes = self.consultar(consulta)
            resultado.intentos.append(intento)
            resultado.ejecutadas.append(consulta)
            resultado.vacantes.extend(vacantes)
            if intento.tipo_error in (TipoError.BLOQUEO, TipoError.CAPTCHA):
                espera = segundos_retry_after(intento.cabeceras.get("retry-after"), intento.ts)
                resultado.cooldown_hasta = self.aplicar_cooldown(intento.ts, espera)
                self._actualizar_ritmo(intento, bloqueo=True, exito=False)
                break
            if intento.tipo_error or not self.pagina_completa(vacantes):
                sin_mas_paginas.add(consulta.keyword)
            exito = intento.status is not None and (
                200 <= intento.status < 300 or intento.status in self.status_sin_resultados
            )
            if exito:
                self.registrar_exito(intento.ts)
            self._actualizar_ritmo(intento, bloqueo=False, exito=exito and not intento.tipo_error)
        self.al_terminar(resultado)
        return resultado

    def al_terminar(self, resultado: ResultadoFuente) -> None:
        """Gancho al terminar de recorrer el lote, también tras un bloqueo."""
        return None

    def cerrar(self) -> None:
        self.cliente.close()
