"""Enlaces "⚡ Postularme" del canal hacia el bot asistente.

Módulo puro, sin dependencias del asistente: lo usa el buscador al componer las fichas.
"""

from __future__ import annotations

import base64
import hashlib

from buscador_vacantes import config as cfg

LARGO_ID = 12
PREFIJO_VACANTE = "v_"
PREFIJO_BOTON = "pv:"  # callback_data del botón ⚡ en los mensajes del canal


def id_corto(clave: str) -> str:
    """Id estable y opaco de una vacante (12 caracteres base32 en minúscula)."""
    digest = hashlib.sha256(clave.encode()).digest()
    return base64.b32encode(digest).decode().lower()[:LARGO_ID]


def enlace(bot_usuario: str, clave: str) -> str:
    return f"https://t.me/{bot_usuario}?start={PREFIJO_VACANTE}{id_corto(clave)}"


def dato_boton(clave: str) -> str:
    """callback_data del botón ⚡ de una vacante (Telegram admite hasta 64 bytes)."""
    return f"{PREFIJO_BOTON}{id_corto(clave)}"


def bot_para_enlaces(config: cfg.Configuracion) -> str | None:
    """Usuario del bot si el enlace ⚡ está habilitado en el canal; si no, None."""
    asistente = config.asistente
    if asistente and asistente.activo and asistente.enlace_canal and asistente.bot_usuario:
        return asistente.bot_usuario
    return None
