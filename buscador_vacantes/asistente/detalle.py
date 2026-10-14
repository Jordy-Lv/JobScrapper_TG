"""Descripción completa de una vacante desde su página pública (bajo demanda, con caché).

Sin iniciar sesión ni evadir nada: un request por dominio cada pocos segundos, se respetan los
cooldowns que el buscador registró por bloqueo y la caché (24 h) se comparte entre usuarios.
Computrabajo, Magneto y elempleo publican los datos estructurados schema.org/JobPosting;
GetOnBoard y LinkedIn tienen un bloque de descripción reconocible; el resto usa el texto visible.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from buscador_vacantes import config as cfg
from buscador_vacantes.asistente.datos import BaseAsistente
from buscador_vacantes.asistente.vacantes import VacanteIndexada
from buscador_vacantes.estado import a_texto, de_texto
from buscador_vacantes.normalizar import normalizar_texto

log = logging.getLogger(__name__)

MAX_DETALLE = 6000
STATUS_BLOQUEO = {403, 429, 999}
TEXTOS_CERRADA = (
    "oferta finalizada",
    "esta oferta ya no esta disponible",
    "esta oferta ha finalizado",
    "ya no acepta postulaciones",
    "la oferta ha expirado",
    "vacante cerrada",
    "no longer accepting applications",
    "esta vacante ya no esta disponible",
)


class EstadoPagina(StrEnum):
    OK = "ok"
    CERRADA = "cerrada"
    BLOQUEADA = "bloqueada"  # 403/429, captcha o la fuente está en cooldown
    SIN_DETALLE = "sin_detalle"  # error de red o página sin descripción reconocible


@dataclass
class Detalle:
    estado: EstadoPagina
    texto: str | None
    # Datos cortos de la oferta (salario, ubicación, fechas) para el resumen de la postulación
    ficha: dict[str, str] | None = None


def _texto(html: str) -> str:
    return " ".join(BeautifulSoup(html or "", "lxml").get_text(" ").split())


def _job_posting(sopa: BeautifulSoup) -> dict | None:
    for script in sopa.find_all("script", type="application/ld+json"):
        try:
            datos = json.loads(script.get_text())
        except ValueError:
            continue
        nodos = datos.get("@graph", [datos]) if isinstance(datos, dict) else datos
        for nodo in nodos if isinstance(nodos, list) else []:
            if isinstance(nodo, dict) and nodo.get("@type") == "JobPosting":
                return nodo
    return None


UNIDADES_SALARIO = {"MONTH": "mensual", "YEAR": "anual", "WEEK": "semanal", "DAY": "diario",
                    "HOUR": "por hora"}  # fmt: skip
TIPOS_EMPLEO = {
    "FULL_TIME": "Tiempo completo", "PART_TIME": "Medio tiempo",
    "CONTRACTOR": "Por prestación de servicios", "TEMPORARY": "Temporal", "INTERN": "Prácticas",
    "VOLUNTEER": "Voluntariado", "PER_DIEM": "Por días",
}  # fmt: skip


def _pesos(valor: object) -> str | None:
    try:
        numero = float(str(valor))
    except ValueError:
        return None
    return "$ " + f"{numero:,.0f}".replace(",", ".") if numero > 0 else None


def _salario(oferta: dict) -> str | None:
    base = oferta.get("baseSalary")
    if not isinstance(base, dict):
        return None
    valor = base.get("value")
    unidad = ""
    if isinstance(valor, dict):
        unidad = UNIDADES_SALARIO.get(str(valor.get("unitText", "")).upper(), "")
        minimo, maximo = _pesos(valor.get("minValue")), _pesos(valor.get("maxValue"))
        if minimo and maximo and minimo != maximo:
            texto = f"{minimo} – {maximo}"
        else:
            texto = _pesos(valor.get("value")) or minimo or maximo
    else:
        texto = _pesos(valor)
    if not texto:
        return None
    return f"{texto} {unidad}".strip()


def _ubicacion(oferta: dict) -> str | None:
    lugares = oferta.get("jobLocation")
    lugares = lugares if isinstance(lugares, list) else [lugares]
    partes: list[str] = []
    for lugar in lugares:
        direccion = lugar.get("address") if isinstance(lugar, dict) else None
        if not isinstance(direccion, dict):
            continue
        for clave in ("addressLocality", "addressRegion"):
            valor = str(direccion.get(clave) or "").strip()
            if valor and valor not in partes:
                partes.append(valor)
    if oferta.get("jobLocationType") == "TELECOMMUTE":
        partes.append("Remoto")
    return ", ".join(partes) or None


def ficha_de(oferta: dict) -> dict[str, str]:
    """Salario, ubicación, tipo de empleo y fechas de un JobPosting, solo lo que traiga."""
    tipos = oferta.get("employmentType")
    tipos = tipos if isinstance(tipos, list) else [tipos]
    tipo = ", ".join(TIPOS_EMPLEO[t] for t in tipos if t in TIPOS_EMPLEO)
    organizacion = oferta.get("hiringOrganization")
    datos = {
        "empresa": organizacion.get("name") if isinstance(organizacion, dict) else None,
        "salario": _salario(oferta),
        "ubicacion": _ubicacion(oferta),
        "tipo": tipo or None,
        "publicada": str(oferta.get("datePosted") or "")[:10] or None,
        "vence": str(oferta.get("validThrough") or "")[:10] or None,
    }
    return {k: str(v) for k, v in datos.items() if v}


def extraer(html: str, url: str, hoy: date) -> Detalle:
    sopa = BeautifulSoup(html, "lxml")
    visible = normalizar_texto(sopa.get_text(" "))
    if any(t in visible for t in TEXTOS_CERRADA):
        return Detalle(EstadoPagina.CERRADA, None)
    if oferta := _job_posting(sopa):
        vence = str(oferta.get("validThrough") or "")[:10]
        if vence and vence < hoy.isoformat():
            return Detalle(EstadoPagina.CERRADA, None)
        texto = _texto(oferta.get("description", ""))
        if texto:
            return Detalle(EstadoPagina.OK, texto[:MAX_DETALLE], ficha_de(oferta) or None)
    host = urlparse(url).hostname or ""
    selectores = {
        # Sin JSON-LD, el texto de la oferta está en los párrafos de div[div-link]; sin esto
        # se leía toda la página (menús, "Ocultaste esta oferta", "Volver al listado"…)
        "computrabajo.com": "div[div-link] p.mbB",
        "getonbrd.com": "div.gb-rich-txt",
        "linkedin.com": "div.description__text, section.show-more-less-html",
    }
    for dominio, selector in selectores.items():
        if host.endswith(dominio):
            bloques = sopa.select(selector)
            texto = " ".join(" ".join(b.get_text(" ").split()) for b in bloques)
            if texto:
                return Detalle(EstadoPagina.OK, texto[:MAX_DETALLE])
    for basura in sopa(["script", "style", "nav", "header", "footer", "noscript"]):
        basura.decompose()
    principal = sopa.find("main") or sopa.body
    texto = " ".join(principal.get_text(" ").split()) if principal else ""
    if len(texto) >= 200:
        return Detalle(EstadoPagina.OK, texto[:MAX_DETALLE])
    return Detalle(EstadoPagina.SIN_DETALLE, None)


class Ritmo:
    """Mínimo de segundos entre requests al mismo dominio (compartido por todo el servicio)."""

    def __init__(self, intervalo_s: float, reloj: Callable[[], float] = time.monotonic,
                 dormir: Callable[[float], Awaitable[None]] = asyncio.sleep) -> None:  # fmt: skip
        self.intervalo = intervalo_s
        self.reloj = reloj
        self.dormir = dormir
        self.ultimo: dict[str, float] = {}
        self.candado = asyncio.Lock()

    async def esperar_turno(self, dominio: str) -> None:
        async with self.candado:
            espera = self.ultimo.get(dominio, -1e9) + self.intervalo - self.reloj()
            if espera > 0:
                await self.dormir(espera)
            self.ultimo[dominio] = self.reloj()


class Detalles:
    def __init__(
        self,
        base: BaseAsistente,
        vacantes_ro: sqlite3.Connection,
        config: cfg.AsistenteDetalle,
        red: cfg.Red,
        *,
        cliente: httpx.AsyncClient | None = None,
        ritmo: Ritmo | None = None,
    ) -> None:
        self.base = base
        self.ro = vacantes_ro
        self.config = config
        self.red = red
        self.ritmo = ritmo or Ritmo(config.intervalo_dominio_s)
        self.cliente = cliente or httpx.AsyncClient(
            timeout=config.timeout_s,
            follow_redirects=True,
            headers={"User-Agent": red.user_agent, "Accept-Language": red.accept_language},
        )

    async def cerrar(self) -> None:
        await self.cliente.aclose()

    def _en_cooldown(self, fuente: str, ahora: datetime) -> bool:
        fila = self.ro.execute(
            "SELECT cooldown_hasta FROM fuentes_estado WHERE fuente = ?", (fuente,)
        ).fetchone()
        hasta = de_texto(fila["cooldown_hasta"]) if fila else None
        return hasta is not None and hasta > ahora

    def _guardar(self, vacante: VacanteIndexada, detalle: Detalle, ahora: datetime) -> None:
        with self.base.transaccion() as cx:
            cx.execute(
                "UPDATE vacantes SET detalle = ?, estado_pagina = ?, detalle_en = ?, "
                "ficha_json = ? WHERE id_corto = ?",
                (detalle.texto, detalle.estado, a_texto(ahora),
                 json.dumps(detalle.ficha, ensure_ascii=False) if detalle.ficha else None,
                 vacante.id_corto),
            )  # fmt: skip
        vacante.detalle, vacante.estado_pagina, vacante.detalle_en, vacante.ficha = (
            detalle.texto, detalle.estado, ahora, detalle.ficha,
        )  # fmt: skip

    async def obtener(self, vacante: VacanteIndexada, ahora: datetime) -> Detalle:
        if vacante.detalle_en and ahora - vacante.detalle_en < timedelta(hours=self.config.cache_h):
            return Detalle(EstadoPagina(vacante.estado_pagina or "sin_detalle"), vacante.detalle,
                           vacante.ficha)  # fmt: skip
        if self._en_cooldown(vacante.fuente, ahora):
            log.info("Detalle de %s omitido: la fuente está en cooldown", vacante.fuente)
            return Detalle(EstadoPagina.BLOQUEADA, None)  # sin caché: se reintenta después
        dominio = urlparse(vacante.url).hostname or ""
        await self.ritmo.esperar_turno(dominio)
        try:
            respuesta = await self.cliente.get(vacante.url)
        except httpx.HTTPError as exc:
            log.info("Detalle de %s no disponible: %s", vacante.clave, type(exc).__name__)
            return Detalle(EstadoPagina.SIN_DETALLE, None)
        if respuesta.status_code == 404 or respuesta.status_code == 410:
            detalle = Detalle(EstadoPagina.CERRADA, None)
        elif respuesta.status_code in STATUS_BLOQUEO:
            detalle = Detalle(EstadoPagina.BLOQUEADA, None)
        elif respuesta.status_code != 200:
            return Detalle(EstadoPagina.SIN_DETALLE, None)
        else:
            detalle = extraer(respuesta.text, str(respuesta.url), ahora.date())
            # Un marcador de desafío solo cuenta si no hay descripción: hay sitios con
            # reCAPTCHA en los formularios de todas sus páginas (Magneto, elempleo)
            texto = respuesta.text.lower()
            if detalle.estado == EstadoPagina.SIN_DETALLE and any(
                m.lower() in texto for m in self.red.marcadores_desafio
            ):
                detalle = Detalle(EstadoPagina.BLOQUEADA, None)
        self._guardar(vacante, detalle, ahora)
        return detalle
