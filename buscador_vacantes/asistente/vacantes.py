"""Índice de las vacantes publicadas en el canal (id corto del enlace ⚡ → vacante).

Lee `vistas` de vacantes.db en solo lectura: el esquema del buscador no cambia.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import urlparse

from buscador_vacantes.asistente.datos import BaseAsistente
from buscador_vacantes.asistente.enlaces import id_corto
from buscador_vacantes.estado import a_texto, de_texto

CLAVE_MARCA = "indice_enviada_hasta"

# Dominio → plataforma con postulación automática
PLATAFORMAS = {"computrabajo.com": "computrabajo", "magneto365.com": "magneto"}


def plataforma_de_url(url: str) -> str | None:
    host = (urlparse(url).hostname or "").lower()
    for dominio, plataforma in PLATAFORMAS.items():
        if host == dominio or host.endswith("." + dominio):
            return plataforma
    return None


@dataclass
class VacanteIndexada:
    id_corto: str
    clave: str
    fuente: str
    plataforma: str | None
    url: str
    titulo: str | None
    empresa: str | None
    enviada_en: datetime | None
    detalle: str | None = None
    estado_pagina: str | None = None
    detalle_en: datetime | None = None

    @classmethod
    def de_fila(cls, f: sqlite3.Row) -> VacanteIndexada:
        return cls(
            f["id_corto"], f["clave"], f["fuente"], f["plataforma"], f["url"], f["titulo"],
            f["empresa"], de_texto(f["enviada_en"]), f["detalle"], f["estado_pagina"],
            de_texto(f["detalle_en"]),
        )  # fmt: skip

    @property
    def resumen(self) -> str:
        """Título, empresa y descripción: el texto de la vacante para la IA y la afinidad."""
        partes = [self.titulo or "", self.empresa or "", self.detalle or ""]
        return "\n".join(p for p in partes if p)


class Indice:
    def __init__(self, base: BaseAsistente, vacantes_ro: sqlite3.Connection, retencion_dias: int):
        self.base = base
        self.ro = vacantes_ro
        self.retencion = timedelta(days=retencion_dias)

    def indexar(self, ahora: datetime) -> int:
        """Agrega las vacantes enviadas al canal desde la última marca. Devuelve cuántas."""
        desde = self.base.kv_obtener(CLAVE_MARCA) or a_texto(ahora - self.retencion)
        filas = self.ro.execute(
            "SELECT clave, fuente, titulo, empresa, url, categoria, enviada_en FROM vistas "
            "WHERE enviada_en IS NOT NULL AND enviada_en > ? ORDER BY enviada_en",
            (desde,),
        ).fetchall()
        nuevas = 0
        with self.base.transaccion() as cx:
            for f in filas:
                if not f["url"]:
                    continue
                cur = cx.execute(
                    "INSERT OR IGNORE INTO vacantes(id_corto, clave, fuente, plataforma, url, "
                    "titulo, empresa, categoria, enviada_en, indexada_en) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (id_corto(f["clave"]), f["clave"], f["fuente"], plataforma_de_url(f["url"]),
                     f["url"], f["titulo"], f["empresa"], f["categoria"], f["enviada_en"],
                     a_texto(ahora)),
                )  # fmt: skip
                nuevas += cur.rowcount
            if filas:
                cx.execute(
                    "INSERT INTO kv(clave, valor) VALUES (?, ?) "
                    "ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor",
                    (CLAVE_MARCA, filas[-1]["enviada_en"]),
                )
            # Retención: las vacantes viejas sin postulaciones salen del índice
            cx.execute(
                "DELETE FROM vacantes WHERE enviada_en < ? AND id_corto NOT IN "
                "(SELECT id_corto FROM postulaciones WHERE id_corto IS NOT NULL)",
                (a_texto(ahora - self.retencion),),
            )
        return nuevas

    def obtener(self, id_corto_: str) -> VacanteIndexada | None:
        fila = self.base.cx.execute(
            "SELECT * FROM vacantes WHERE id_corto = ?", (id_corto_,)
        ).fetchone()
        return VacanteIndexada.de_fila(fila) if fila else None

    def resolver(self, id_corto_: str, ahora: datetime) -> VacanteIndexada | None:
        """Busca el id del enlace; si no está, reindexa una vez (la vacante puede ser recién
        publicada) antes de responder que no existe. Las de más días que la retención, no."""
        vacante = self.obtener(id_corto_)
        if vacante is None:
            self.indexar(ahora)
            vacante = self.obtener(id_corto_)
        if vacante and vacante.enviada_en and ahora - vacante.enviada_en > self.retencion:
            return None
        return vacante
