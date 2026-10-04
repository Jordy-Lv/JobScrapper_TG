"""Cliente de DeepSeek compartido: chat JSON, saldo, presupuesto diario, uso y sanitización."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal

import httpx

import config as cfg
from estado import Estado, a_texto, ahora_utc, de_texto
from fechas import ZONA
from registro import enmascarar

Proposito = Literal["clasificador", "reportero", "resumen"]

log = logging.getLogger(__name__)


@dataclass
class RespuestaIA:
    ok: bool
    datos: dict[str, Any] | None = None
    motivo: str | None = None  # por qué no hay respuesta válida, apto para mostrar
    tokens_in: int = 0
    tokens_out: int = 0
    realizada: bool = True  # False si no se llamó a la API (tope, saldo o sin clave)


def sanitizar(texto: str, secretos: Iterable[str] = ()) -> str:
    """Quita secretos conocidos (token, clave, ids de chat) y cualquier cosa con forma de token."""
    return enmascarar(texto, secretos)


class ClienteIA:
    def __init__(
        self,
        config_ia: cfg.IA,
        api_key: str | None,
        estado: Estado,
        *,
        secretos: Iterable[str] = (),
        cliente: httpx.Client | None = None,
        reloj: Callable[[], datetime] = ahora_utc,
    ) -> None:
        self.config = config_ia
        self.api_key = api_key
        self.estado = estado
        self.secretos = [s for s in secretos if s]
        self.reloj = reloj
        self.cliente = cliente or httpx.Client(
            base_url=config_ia.base_url, timeout=config_ia.timeout_s
        )

    def cerrar(self) -> None:
        self.cliente.close()

    def _cabeceras(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    # --- saldo ------------------------------------------------------------------------------

    def saldo(self) -> float | None:
        """Saldo en USD, cacheado en el estado. None si no se pudo consultar."""
        cache = self.estado.kv_obtener("ia_saldo")
        if cache:
            guardado = json.loads(cache)
            ts = de_texto(guardado["ts"])
            if ts and self.reloj() - ts < timedelta(minutes=self.config.saldo_cache_min):
                return guardado["valor"]
        try:
            respuesta = self.cliente.get("/user/balance", headers=self._cabeceras())
            respuesta.raise_for_status()
            infos = respuesta.json().get("balance_infos") or []
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("No se pudo consultar el saldo de DeepSeek: %s", exc)
            return None
        info = next((i for i in infos if i.get("currency") == "USD"), infos[0] if infos else None)
        if info is None:
            return None
        valor = float(info.get("total_balance") or 0)
        self.estado.kv_guardar(
            "ia_saldo", json.dumps({"valor": valor, "ts": a_texto(self.reloj())})
        )
        return valor

    def saldo_bajo(self) -> tuple[bool, float | None]:
        valor = self.saldo()
        return (valor is not None and valor < self.config.saldo_minimo_usd), valor

    # --- presupuesto ------------------------------------------------------------------------

    def llamadas_hoy(self, proposito: Proposito) -> int:
        """Llamadas hechas hoy (día calendario de Colombia) para un propósito."""
        ahora = self.reloj().astimezone(ZONA)
        inicio_dia = ahora.replace(hour=0, minute=0, second=0, microsecond=0)
        return self.estado.cx.execute(
            "SELECT COUNT(*) FROM ia_uso WHERE proposito = ? AND ts >= ?",
            (proposito, a_texto(inicio_dia)),
        ).fetchone()[0]

    def tope(self, proposito: Proposito) -> int:
        return getattr(self.config.presupuesto_dia, proposito)

    def _registrar_uso(self, proposito: str, respuesta: RespuestaIA) -> None:
        with self.estado.transaccion() as cx:
            cx.execute(
                "INSERT INTO ia_uso(ts, proposito, tokens_in, tokens_out, ok, motivo) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    a_texto(self.reloj()),
                    proposito,
                    respuesta.tokens_in,
                    respuesta.tokens_out,
                    int(respuesta.ok),
                    respuesta.motivo,
                ),
            )
        log.info(
            "IA %s: ok=%s tokens_in=%s tokens_out=%s%s",
            proposito,
            respuesta.ok,
            respuesta.tokens_in,
            respuesta.tokens_out,
            f" motivo={respuesta.motivo}" if respuesta.motivo else "",
        )

    # --- chat -------------------------------------------------------------------------------

    def chat_json(
        self,
        proposito: Proposito,
        prompt_sistema: str,
        payload: dict[str, Any],
        *,
        temperatura: float,
        max_tokens: int,
    ) -> RespuestaIA:
        """Una llamada sin reintentos que devuelve un JSON. Nunca lanza excepciones."""
        if not self.api_key:
            return RespuestaIA(False, motivo="sin clave de API", realizada=False)
        if self.llamadas_hoy(proposito) >= self.tope(proposito):
            return RespuestaIA(False, motivo="tope diario alcanzado", realizada=False)
        bajo, valor = self.saldo_bajo()
        if bajo:
            return RespuestaIA(False, motivo="saldo bajo", realizada=False)

        contenido = sanitizar(json.dumps(payload, ensure_ascii=False, default=str), self.secretos)
        cuerpo = {
            "model": self.config.modelo,
            "messages": [
                {"role": "system", "content": prompt_sistema},
                {"role": "user", "content": contenido},
            ],
            "temperature": temperatura,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
            "stream": False,
        }
        respuesta = self._llamar(cuerpo)
        self._registrar_uso(proposito, respuesta)
        return respuesta

    def _llamar(self, cuerpo: dict[str, Any]) -> RespuestaIA:
        try:
            http = self.cliente.post("/chat/completions", json=cuerpo, headers=self._cabeceras())
        except httpx.TimeoutException:
            return RespuestaIA(False, motivo="timeout")
        except httpx.HTTPError as exc:
            return RespuestaIA(False, motivo=f"error de conexión ({type(exc).__name__})")

        if http.status_code == 402:
            return RespuestaIA(False, motivo="saldo insuficiente (HTTP 402)")
        if http.status_code >= 500:
            return RespuestaIA(False, motivo=f"error del servidor (HTTP {http.status_code})")
        if http.status_code != 200:
            return RespuestaIA(False, motivo=f"error HTTP {http.status_code}")

        try:
            datos = http.json()
            uso = datos.get("usage") or {}
            tokens_in = int(uso.get("prompt_tokens") or 0)
            tokens_out = int(uso.get("completion_tokens") or 0)
            texto = datos["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError):
            return RespuestaIA(False, motivo="respuesta inválida")
        try:
            contenido = json.loads(texto)
        except (TypeError, ValueError):
            return RespuestaIA(False, None, "respuesta inválida", tokens_in, tokens_out)
        if not isinstance(contenido, dict):
            return RespuestaIA(False, None, "respuesta inválida", tokens_in, tokens_out)
        return RespuestaIA(True, contenido, None, tokens_in, tokens_out)
