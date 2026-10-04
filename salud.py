"""Heartbeat a healthchecks.io: /start al empezar, URL base al terminar bien y /fail ante error."""

from __future__ import annotations

import logging

import httpx

log = logging.getLogger(__name__)
MAX_CUERPO = 10_000


class Salud:
    def __init__(
        self,
        url: str | None,
        *,
        activo: bool = True,
        timeout_s: float = 10,
        cliente: httpx.Client | None = None,
    ) -> None:
        self.url = url.rstrip("/") if url else None
        self.activo = activo and bool(self.url)
        self.cliente = cliente or httpx.Client(timeout=timeout_s)

    def cerrar(self) -> None:
        self.cliente.close()

    def _ping(self, sufijo: str, cuerpo: str = "") -> bool:
        """Nunca lanza: si el monitoreo no responde, la corrida sigue y queda en el log."""
        if not self.activo:
            return False
        try:
            respuesta = self.cliente.post(f"{self.url}{sufijo}", content=cuerpo[:MAX_CUERPO])
            respuesta.raise_for_status()
            return True
        except httpx.HTTPError as exc:
            log.warning("Ping de salud%s falló: %s", sufijo or " (éxito)", type(exc).__name__)
            return False

    def inicio(self) -> bool:
        return self._ping("/start")

    def exito(self, resumen: str = "") -> bool:
        return self._ping("", resumen)

    def fallo(self, detalle: str = "") -> bool:
        return self._ping("/fail", detalle)
