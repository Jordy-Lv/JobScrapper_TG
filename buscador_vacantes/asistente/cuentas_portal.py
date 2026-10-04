"""Cuenta de cada portal asociada a cada usuario (por su correo).

Antes de postular, la extensión informa el correo de la sesión abierta. Solo se postula si
coincide con la cuenta que el usuario confirmó; el correo de otra persona nunca se guarda.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from buscador_vacantes.asistente.cifrado import Cifrador, huella
from buscador_vacantes.asistente.datos import BaseAsistente
from buscador_vacantes.estado import a_texto


class EstadoCuenta(StrEnum):
    OK = "ok"  # coincide con la cuenta confirmada
    POR_CONFIRMAR = "por_confirmar"  # primera vez: el usuario debe confirmar el correo
    DISTINTA = "distinta"  # la sesión abierta es de otra cuenta
    SIN_CORREO = "sin_correo"  # no se pudo leer el correo de la página


@dataclass
class Verificacion:
    estado: EstadoCuenta
    plataforma: str
    asociado: str | None = None  # correo confirmado del usuario
    encontrado_oculto: str | None = None  # correo de la sesión, enmascarado
    nuevo: bool = False  # se acaba de registrar como por confirmar (avisar una vez)


def enmascarar_correo(correo: str) -> str:
    """l***@hotmail.com"""
    usuario, _, dominio = correo.strip().partition("@")
    return f"{usuario[:1]}***@{dominio}" if dominio else "***"


class CuentasPortal:
    def __init__(self, base: BaseAsistente, cifrador: Cifrador) -> None:
        self.base = base
        self.cifrador = cifrador

    def asociado(self, usuario_id: int, plataforma: str) -> tuple[str, str] | None:
        """(correo, estado) de la cuenta asociada, o None."""
        fila = self.base.cx.execute(
            "SELECT correo_cifrado, estado FROM cuentas_portal "
            "WHERE usuario_id = ? AND plataforma = ?",
            (usuario_id, plataforma),
        ).fetchone()
        if not fila:
            return None
        return self.cifrador.descifrar(fila["correo_cifrado"]), fila["estado"]

    def todas(self, usuario_id: int) -> dict[str, tuple[str, str]]:
        filas = self.base.cx.execute(
            "SELECT plataforma FROM cuentas_portal WHERE usuario_id = ?", (usuario_id,)
        ).fetchall()
        return {f["plataforma"]: self.asociado(usuario_id, f["plataforma"]) for f in filas}

    def verificar(
        self, usuario_id: int, plataforma: str, correo: str | None, ahora: datetime
    ) -> Verificacion:
        if not correo or "@" not in correo:
            return Verificacion(EstadoCuenta.SIN_CORREO, plataforma)
        fila = self.base.cx.execute(
            "SELECT correo_cifrado, correo_hash, estado FROM cuentas_portal "
            "WHERE usuario_id = ? AND plataforma = ?",
            (usuario_id, plataforma),
        ).fetchone()
        if fila is None:
            self._guardar(usuario_id, plataforma, correo, "pendiente", ahora)
            return Verificacion(
                EstadoCuenta.POR_CONFIRMAR, plataforma, asociado=correo.strip(), nuevo=True
            )
        asociado = self.cifrador.descifrar(fila["correo_cifrado"])
        if fila["correo_hash"] == huella(correo):
            estado = (
                EstadoCuenta.OK if fila["estado"] == "confirmada" else EstadoCuenta.POR_CONFIRMAR
            )
            return Verificacion(estado, plataforma, asociado=asociado)
        if fila["estado"] == "pendiente":
            # Aún sin confirmar: se propone la cuenta que tiene la sesión ahora
            self._guardar(usuario_id, plataforma, correo, "pendiente", ahora)
            return Verificacion(
                EstadoCuenta.POR_CONFIRMAR, plataforma, asociado=correo.strip(), nuevo=True
            )
        return Verificacion(
            EstadoCuenta.DISTINTA, plataforma, asociado=asociado,
            encontrado_oculto=enmascarar_correo(correo),
        )  # fmt: skip

    def confirmar(self, usuario_id: int, plataforma: str, ahora: datetime) -> bool:
        with self.base.transaccion() as cx:
            cur = cx.execute(
                "UPDATE cuentas_portal SET estado = 'confirmada', confirmada_en = ? "
                "WHERE usuario_id = ? AND plataforma = ?",
                (a_texto(ahora), usuario_id, plataforma),
            )
            return bool(cur.rowcount)

    def reemplazar(self, usuario_id: int, plataforma: str, correo: str, ahora: datetime) -> None:
        """'Es mi cuenta nueva, usarla': el correo de la sesión pasa a ser el asociado."""
        self._guardar(usuario_id, plataforma, correo, "confirmada", ahora)

    def olvidar(self, usuario_id: int, plataforma: str) -> None:
        with self.base.transaccion() as cx:
            cx.execute(
                "DELETE FROM cuentas_portal WHERE usuario_id = ? AND plataforma = ?",
                (usuario_id, plataforma),
            )

    def _guardar(
        self, usuario_id: int, plataforma: str, correo: str, estado: str, ahora: datetime
    ) -> None:
        confirmada = a_texto(ahora) if estado == "confirmada" else None
        with self.base.transaccion() as cx:
            cx.execute(
                "INSERT INTO cuentas_portal(usuario_id, plataforma, correo_cifrado, correo_hash, "
                "estado, confirmada_en) VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(usuario_id, plataforma) DO UPDATE SET "
                "correo_cifrado = excluded.correo_cifrado, correo_hash = excluded.correo_hash, "
                "estado = excluded.estado, confirmada_en = excluded.confirmada_en",
                (usuario_id, plataforma, self.cifrador.cifrar(correo.strip()), huella(correo),
                 estado, confirmada),
            )  # fmt: skip
