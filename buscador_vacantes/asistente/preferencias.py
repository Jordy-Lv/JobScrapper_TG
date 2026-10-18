"""Preferencias del usuario por portal: el engranaje de cada plataforma en la extensión.

Sin fila guardada rigen los valores por defecto: participa del modo automático del usuario, sin
afinidad mínima propia (usa la del usuario), avisa por Telegram las postulaciones que se
enviaron solas y no pide revisar las respuestas redactadas antes de enviarlas.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from buscador_vacantes.asistente.datos import BaseAsistente
from buscador_vacantes.comun.estado import a_texto


@dataclass
class PreferenciasPortal:
    automatico: bool = True
    umbral: int | None = None
    avisar: bool = True
    revisar_respuestas: bool = False


class Preferencias:
    def __init__(self, base: BaseAsistente) -> None:
        self.base = base

    def obtener(self, usuario_id: int, plataforma: str) -> PreferenciasPortal:
        fila = self.base.cx.execute(
            "SELECT automatico, umbral, avisar, revisar_respuestas FROM preferencias_portal "
            "WHERE usuario_id = ? AND plataforma = ?",
            (usuario_id, plataforma),
        ).fetchone()
        if fila is None:
            return PreferenciasPortal()
        return PreferenciasPortal(
            bool(fila["automatico"]), fila["umbral"], bool(fila["avisar"]),
            bool(fila["revisar_respuestas"]),
        )  # fmt: skip

    def guardar(
        self,
        usuario_id: int,
        plataforma: str,
        ahora: datetime,
        *,
        automatico: bool,
        umbral: int | None,
        avisar: bool,
        revisar_respuestas: bool = False,
    ) -> None:
        with self.base.transaccion() as cx:
            cx.execute(
                "INSERT INTO preferencias_portal(usuario_id, plataforma, automatico, umbral, "
                "avisar, revisar_respuestas, actualizada) VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(usuario_id, plataforma) DO UPDATE SET "
                "automatico = excluded.automatico, umbral = excluded.umbral, "
                "avisar = excluded.avisar, revisar_respuestas = excluded.revisar_respuestas, "
                "actualizada = excluded.actualizada",
                (
                    usuario_id,
                    plataforma,
                    int(automatico),
                    umbral,
                    int(avisar),
                    int(revisar_respuestas),
                    a_texto(ahora),
                ),  # fmt: skip
            )
