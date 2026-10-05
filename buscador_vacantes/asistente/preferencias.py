"""Preferencias del usuario por portal: el engranaje de cada plataforma en la extensión.

Sin fila guardada rigen los valores por defecto: participa del modo automático del usuario, sin
afinidad mínima propia (usa la del usuario) y avisa por Telegram las postulaciones que se
enviaron solas.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from buscador_vacantes.asistente.datos import BaseAsistente
from buscador_vacantes.estado import a_texto


@dataclass
class PreferenciasPortal:
    automatico: bool = True
    umbral: int | None = None
    avisar: bool = True


class Preferencias:
    def __init__(self, base: BaseAsistente) -> None:
        self.base = base

    def obtener(self, usuario_id: int, plataforma: str) -> PreferenciasPortal:
        fila = self.base.cx.execute(
            "SELECT automatico, umbral, avisar FROM preferencias_portal "
            "WHERE usuario_id = ? AND plataforma = ?",
            (usuario_id, plataforma),
        ).fetchone()
        if fila is None:
            return PreferenciasPortal()
        return PreferenciasPortal(bool(fila["automatico"]), fila["umbral"], bool(fila["avisar"]))

    def guardar(
        self,
        usuario_id: int,
        plataforma: str,
        ahora: datetime,
        *,
        automatico: bool,
        umbral: int | None,
        avisar: bool,
    ) -> None:
        with self.base.transaccion() as cx:
            cx.execute(
                "INSERT INTO preferencias_portal(usuario_id, plataforma, automatico, umbral, "
                "avisar, actualizada) VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(usuario_id, plataforma) DO UPDATE SET "
                "automatico = excluded.automatico, umbral = excluded.umbral, "
                "avisar = excluded.avisar, actualizada = excluded.actualizada",
                (usuario_id, plataforma, int(automatico), umbral, int(avisar), a_texto(ahora)),
            )
