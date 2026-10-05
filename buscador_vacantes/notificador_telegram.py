"""Envío a Telegram: Bot API directa (preferido) o `hermes send` como respaldo."""

from __future__ import annotations

import logging
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import httpx

from buscador_vacantes import config as cfg

log = logging.getLogger(__name__)

API = "https://api.telegram.org"
MAX_ESPERA_429_S = 30


@dataclass
class ResultadoEnvio:
    ok: bool
    message_id: int | None = None
    codigo: int | None = None
    error: str | None = None  # descripción apta para el log y el incidente


# Botones de un mensaje: (texto, callback_data), uno por fila
Botones = list[tuple[str, str]]


class Notificador(Protocol):
    def enviar_mensaje(
        self, chat_id: str, texto_html: str, botones: Botones | None = None
    ) -> ResultadoEnvio: ...

    def enviar_foto(self, chat_id: str, ruta: Path) -> ResultadoEnvio: ...

    def cerrar(self) -> None: ...


class NotificadorBotAPI:
    """Solo métodos de envío: nunca getUpdates ni webhooks, para no interferir con Hermes."""

    def __init__(
        self,
        token: str,
        timeout_s: float = 20,
        *,
        cliente: httpx.Client | None = None,
        dormir: Callable[[float], None] = time.sleep,
    ) -> None:
        self.token = token
        self.dormir = dormir
        self.cliente = cliente or httpx.Client(timeout=timeout_s)

    def cerrar(self) -> None:
        self.cliente.close()

    def _url(self, metodo: str) -> str:
        return f"{API}/bot{self.token}/{metodo}"

    def _interpretar(self, respuesta: httpx.Response) -> ResultadoEnvio:
        try:
            datos = respuesta.json()
        except ValueError:
            datos = {}
        if respuesta.status_code == 200 and datos.get("ok"):
            return ResultadoEnvio(True, message_id=(datos.get("result") or {}).get("message_id"))
        descripcion = datos.get("description") or f"HTTP {respuesta.status_code}"
        if respuesta.status_code == 401:
            descripcion = f"token del bot inválido o revocado (401: {descripcion})"
        return ResultadoEnvio(False, codigo=respuesta.status_code, error=descripcion)

    def _enviar(self, metodo: str, **kwargs) -> ResultadoEnvio:
        for intento in range(2):
            try:
                respuesta = self.cliente.post(self._url(metodo), **kwargs)
            except httpx.HTTPError as exc:
                return ResultadoEnvio(
                    False, error=f"error de conexión con Telegram ({type(exc).__name__})"
                )
            resultado = self._interpretar(respuesta)
            if resultado.codigo != 429 or intento:
                return resultado
            # Límite de envío: esperar lo que pida Telegram (si es razonable) y reintentar una vez
            try:
                espera = int(respuesta.json()["parameters"]["retry_after"])
            except (ValueError, KeyError, TypeError):
                espera = 5
            if espera > MAX_ESPERA_429_S:
                return resultado
            log.warning("Telegram pidió esperar %s s (429)", espera)
            self.dormir(espera)
        return resultado

    def enviar_mensaje(
        self, chat_id: str, texto_html: str, botones: Botones | None = None
    ) -> ResultadoEnvio:
        cuerpo = {
            "chat_id": chat_id,
            "text": texto_html,
            "parse_mode": "HTML",
            "link_preview_options": {"is_disabled": True},
        }
        if botones:
            cuerpo["reply_markup"] = {
                "inline_keyboard": [[{"text": t, "callback_data": d}] for t, d in botones]
            }
        return self._enviar("sendMessage", json=cuerpo)

    def enviar_foto(self, chat_id: str, ruta: Path) -> ResultadoEnvio:
        try:
            contenido = ruta.read_bytes()
        except OSError as exc:
            return ResultadoEnvio(False, error=f"no se pudo leer la imagen {ruta}: {exc}")
        return self._enviar(
            "sendPhoto",
            data={"chat_id": chat_id},
            files={"photo": (ruta.name, contenido, "image/jpeg")},
        )


class NotificadorHermesCLI:
    """Respaldo con `hermes send`; la confirmación es el código de salida."""

    def __init__(self, comando: str = "hermes", timeout_s: float = 60) -> None:
        self.comando = comando
        self.timeout_s = timeout_s

    def cerrar(self) -> None:
        pass

    def _ejecutar(self, chat_id: str, contenido: str) -> ResultadoEnvio:
        try:
            proceso = subprocess.run(
                [self.comando, "send", "-t", f"telegram:{chat_id}", contenido],
                capture_output=True,
                text=True,
                timeout=self.timeout_s,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return ResultadoEnvio(False, error=f"no se pudo ejecutar {self.comando}: {exc}")
        if proceso.returncode == 0:
            return ResultadoEnvio(True)
        salida = (proceso.stderr or proceso.stdout).strip()[:300]
        return ResultadoEnvio(
            False, codigo=proceso.returncode, error=f"{self.comando} send falló: {salida}"
        )

    def enviar_mensaje(
        self, chat_id: str, texto_html: str, botones: Botones | None = None
    ) -> ResultadoEnvio:
        return self._ejecutar(chat_id, texto_html)  # Hermes no envía botones

    def enviar_foto(self, chat_id: str, ruta: Path) -> ResultadoEnvio:
        return self._ejecutar(chat_id, f"MEDIA:{ruta}")


def crear_notificador(telegram: cfg.Telegram, token: str | None) -> Notificador:
    if telegram.modo == "hermes_cli":
        return NotificadorHermesCLI(telegram.hermes_comando)
    if not token:
        raise ValueError("Falta el token del bot para el modo bot_api")
    return NotificadorBotAPI(token, telegram.timeout_s)
