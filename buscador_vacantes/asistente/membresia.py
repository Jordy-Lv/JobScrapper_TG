"""Comprobación de membresía en el grupo privado con getChatMember (python-telegram-bot).

El bot asistente debe ser administrador del grupo (sin permisos): Telegram solo deja consultar
la membresía de otros a un administrador. Si la consulta falla por permisos, se bloquean las
altas nuevas, los usuarios existentes quedan como están y se avisa al administrador.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from telegram.error import BadRequest, Forbidden, TelegramError

from buscador_vacantes.asistente.usuarios import Membresia, Usuario, Usuarios, interpretar_miembro

log = logging.getLogger(__name__)

MOTIVO_SIN_PERMISOS = (
    "No se puede comprobar la membresía del grupo: el bot asistente no es administrador del "
    "grupo o el id del grupo es incorrecto."
)


class SinPermisos(Exception):
    """Telegram no permite consultar la membresía (el bot no es administrador del grupo)."""


@dataclass
class Comprobador:
    bot: Any  # telegram.Bot (o un doble en las pruebas)
    chat_id: str | int
    usuarios: Usuarios
    cache_min: float
    avisar_dueno: Callable[[str], Awaitable[None]]

    async def consultar(self, telegram_id: int) -> Membresia:
        try:
            miembro = await self.bot.get_chat_member(self.chat_id, telegram_id)
        except (Forbidden, BadRequest) as exc:
            texto = str(exc).lower()
            if "user not found" in texto or "participant_id_invalid" in texto:
                return Membresia.NO_MIEMBRO
            await self._sin_permisos(exc)
            raise SinPermisos(str(exc)) from exc
        status = getattr(miembro, "status", "")
        return interpretar_miembro(status, getattr(miembro, "is_member", None))

    async def _sin_permisos(self, exc: TelegramError) -> None:
        if self.usuarios.altas_bloqueadas():
            return  # ya se avisó
        log.error("getChatMember falló por permisos: %s", exc)
        self.usuarios.bloquear_altas(MOTIVO_SIN_PERMISOS)
        await self.avisar_dueno(f"⚠️ {MOTIVO_SIN_PERMISOS} Las altas nuevas quedan bloqueadas.")

    async def es_miembro_nuevo(self, telegram_id: int) -> bool:
        """Para una persona sin cuenta: no se guarda nada si no es miembro."""
        if self.usuarios.altas_bloqueadas():
            raise SinPermisos(self.usuarios.altas_bloqueadas())
        membresia = await self.consultar(telegram_id)
        if membresia == Membresia.MIEMBRO:
            self.usuarios.desbloquear_altas()
        return membresia == Membresia.MIEMBRO

    async def comprobar(
        self, usuario: Usuario, ahora: datetime, *, forzar: bool = False
    ) -> Usuario:
        """En cada ⚡ (con caché) o en la tarea diaria (forzar). Aplica suspensión o reactivación.

        Si no hay permisos para consultar, el usuario queda como estaba.
        """
        if not forzar and self.usuarios.membresia_vigente(usuario, ahora, self.cache_min):
            return usuario
        try:
            membresia = await self.consultar(usuario.telegram_id)
        except SinPermisos:
            return usuario
        except TelegramError as exc:  # red u otro error transitorio: no se cambia nada
            log.warning("No se pudo comprobar la membresía: %s", exc)
            return usuario
        self.usuarios.desbloquear_altas()
        return self.usuarios.aplicar_membresia(usuario, membresia, ahora)

    async def comprobar_todos(self, ahora: datetime) -> dict[str, int]:
        """Tarea diaria: comprueba a todos los usuarios no inactivos."""
        cuenta = {"miembros": 0, "suspendidos": 0, "sin_cambio": 0}
        for usuario in self.usuarios.todos():
            if usuario.estado == "inactivo":
                continue
            antes = usuario.estado
            despues = await self.comprobar(usuario, ahora, forzar=True)
            if despues.estado == "suspendido" and antes != "suspendido":
                cuenta["suspendidos"] += 1
            elif despues.miembro_verificado_en == ahora:
                cuenta["miembros"] += 1
            else:
                cuenta["sin_cambio"] += 1
        return cuenta
