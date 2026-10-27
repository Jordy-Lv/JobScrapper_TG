"""Estado de LinkedIn de cada usuario: aceptación del riesgo, interruptores, pausa y aperturas.

LinkedIn prohíbe automatizar acciones en sus condiciones de uso, así que cada usuario acepta de
forma expresa el riesgo de que restrinjan su cuenta antes de la primera postulación (con la versión
del texto y la fecha). Las aperturas de páginas de LinkedIn se cuentan para el tope diario y la
pausa mínima. Todo se guarda por usuario, sin datos de las vacantes salvo su id.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta

from buscador_vacantes.asistente.datos import BaseAsistente
from buscador_vacantes.comun.estado import a_texto, de_texto
from buscador_vacantes.comun.fechas import ZONA


@dataclass(frozen=True)
class EstadoLinkedin:
    version: int
    aceptado_en: datetime
    sencilla: bool
    externas: bool
    pausado_hasta: datetime | None


class UsuariosLinkedin:
    def __init__(self, base: BaseAsistente) -> None:
        self.base = base

    def estado(self, usuario_id: int) -> EstadoLinkedin | None:
        fila = self.base.cx.execute(
            "SELECT * FROM linkedin_usuarios WHERE usuario_id = ?", (usuario_id,)
        ).fetchone()
        if fila is None:
            return None
        return EstadoLinkedin(
            fila["version"], de_texto(fila["aceptado_en"]), bool(fila["sencilla"]),
            bool(fila["externas"]), de_texto(fila["pausado_hasta"]),
        )  # fmt: skip

    def acepto(self, usuario_id: int, version: int) -> bool:
        """True si el usuario aceptó el riesgo con esta versión del texto (o una posterior)."""
        estado = self.estado(usuario_id)
        return estado is not None and estado.version >= version

    def aceptar(self, usuario_id: int, version: int, ahora: datetime) -> None:
        """Registra la aceptación; los interruptores quedan encendidos la primera vez y se
        conservan al aceptar una versión nueva del texto."""
        with self.base.transaccion() as cx:
            cx.execute(
                "INSERT INTO linkedin_usuarios(usuario_id, version, aceptado_en) VALUES (?, ?, ?) "
                "ON CONFLICT(usuario_id) DO UPDATE SET version = excluded.version, "
                "aceptado_en = excluded.aceptado_en",
                (usuario_id, version, a_texto(ahora)),
            )

    def fijar(
        self, usuario_id: int, *, sencilla: bool | None = None, externas: bool | None = None
    ) -> bool:
        """Cambia un interruptor; False si el usuario no aceptó el riesgo todavía."""
        if self.estado(usuario_id) is None:
            return False
        with self.base.transaccion() as cx:
            if sencilla is not None:
                cx.execute(
                    "UPDATE linkedin_usuarios SET sencilla = ? WHERE usuario_id = ?",
                    (int(sencilla), usuario_id),
                )
            if externas is not None:
                cx.execute(
                    "UPDATE linkedin_usuarios SET externas = ? WHERE usuario_id = ?",
                    (int(externas), usuario_id),
                )
        return True

    # --- pausa por aviso de seguridad -------------------------------------------------------

    def pausar(self, usuario_id: int, hasta: datetime) -> None:
        with self.base.transaccion() as cx:
            cx.execute(
                "UPDATE linkedin_usuarios SET pausado_hasta = ? WHERE usuario_id = ?",
                (a_texto(hasta), usuario_id),
            )

    def pausado_hasta(self, usuario_id: int, ahora: datetime) -> datetime | None:
        """Hasta cuándo está en pausa LinkedIn para el usuario, o None si no lo está."""
        estado = self.estado(usuario_id)
        if estado and estado.pausado_hasta and estado.pausado_hasta > ahora:
            return estado.pausado_hasta
        return None

    # --- aperturas de LinkedIn ----------------------------------------------------------------

    def registrar_apertura(self, usuario_id: int, id_corto: str | None, ahora: datetime) -> None:
        with self.base.transaccion() as cx:
            cx.execute(
                "INSERT INTO linkedin_aperturas(usuario_id, id_corto, ts) VALUES (?, ?, ?)",
                (usuario_id, id_corto, a_texto(ahora)),
            )

    def inicio_dia(self, ahora: datetime) -> datetime:
        return datetime.combine(ahora.astimezone(ZONA).date(), time(0), tzinfo=ZONA)

    def manana(self, ahora: datetime) -> datetime:
        return self.inicio_dia(ahora) + timedelta(days=1)

    def aperturas_hoy(self, usuario_id: int, ahora: datetime) -> int:
        return self.base.cx.execute(
            "SELECT COUNT(*) FROM linkedin_aperturas WHERE usuario_id = ? AND ts >= ?",
            (usuario_id, a_texto(self.inicio_dia(ahora))),
        ).fetchone()[0]

    def ultima_apertura(self, usuario_id: int) -> datetime | None:
        valor = self.base.cx.execute(
            "SELECT MAX(ts) FROM linkedin_aperturas WHERE usuario_id = ?", (usuario_id,)
        ).fetchone()[0]
        return de_texto(valor)
