"""Usuarios del asistente: alta, autorización de datos, membresía del grupo, baja y auditoría.

La consulta a Telegram (getChatMember) la hace el bot; aquí se aplica su resultado.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from pathlib import Path

from buscador_vacantes.asistente.datos import BaseAsistente
from buscador_vacantes.estado import a_texto, de_texto

MOTIVO_FUERA_DEL_GRUPO = "fuera_del_grupo"
MOTIVO_ADMIN = "suspendido_por_admin"
CLAVE_ALTAS_BLOQUEADAS = "altas_bloqueadas"
DIAS_GRACIA_INACTIVIDAD = 30

# Estados de postulación que todavía no se ejecutaron: se cancelan al suspender
PENDIENTES = (
    "en_cola",
    "esperando_navegador",
    "esperando_usuario",
    "esperando_sesion",
    "cuenta_distinta",
)


class EstadoUsuario(StrEnum):
    ALTA = "alta"  # registrándose
    ACTIVO = "activo"
    SUSPENDIDO = "suspendido"
    INACTIVO = "inactivo"  # bloqueó al bot


class Membresia(StrEnum):
    MIEMBRO = "miembro"
    NO_MIEMBRO = "no_miembro"


def interpretar_miembro(status: str, is_member: bool | None = None) -> Membresia:
    """Traduce el estado de getChatMember. `restricted` cuenta solo si sigue en el grupo."""
    if status in ("creator", "administrator", "member"):
        return Membresia.MIEMBRO
    if status == "restricted" and is_member:
        return Membresia.MIEMBRO
    return Membresia.NO_MIEMBRO


@dataclass
class Usuario:
    id: int
    telegram_id: int
    nombre: str | None
    estado: EstadoUsuario
    motivo_estado: str | None
    paso_alta: str | None
    directorio: str
    politica_version: int | None
    miembro_verificado_en: datetime | None
    ultima_actividad: datetime | None
    vacante_pendiente: str | None
    pausado: bool

    @classmethod
    def de_fila(cls, fila: sqlite3.Row) -> Usuario:
        return cls(
            id=fila["id"],
            telegram_id=fila["telegram_id"],
            nombre=fila["nombre"],
            estado=EstadoUsuario(fila["estado"]),
            motivo_estado=fila["motivo_estado"],
            paso_alta=fila["paso_alta"],
            directorio=fila["directorio"],
            politica_version=fila["politica_version"],
            miembro_verificado_en=de_texto(fila["miembro_verificado_en"]),
            ultima_actividad=de_texto(fila["ultima_actividad"]),
            vacante_pendiente=fila["vacante_pendiente"],
            pausado=bool(fila["pausado"]),
        )

    def __repr__(self) -> str:  # sin datos personales en logs
        return f"Usuario(id={self.id}, estado={self.estado})"


class Usuarios:
    def __init__(self, base: BaseAsistente, archivos: Path) -> None:
        self.base = base
        self.archivos = archivos

    # --- consultas -----------------------------------------------------------------

    def obtener(self, telegram_id: int) -> Usuario | None:
        fila = self.base.cx.execute(
            "SELECT * FROM usuarios WHERE telegram_id = ?", (telegram_id,)
        ).fetchone()
        return Usuario.de_fila(fila) if fila else None

    def por_id(self, usuario_id: int) -> Usuario | None:
        fila = self.base.cx.execute("SELECT * FROM usuarios WHERE id = ?", (usuario_id,)).fetchone()
        return Usuario.de_fila(fila) if fila else None

    def todos(self) -> list[Usuario]:
        filas = self.base.cx.execute("SELECT * FROM usuarios ORDER BY id").fetchall()
        return [Usuario.de_fila(f) for f in filas]

    def directorio(self, usuario: Usuario) -> Path:
        return self.archivos / "usuarios" / usuario.directorio

    # --- alta ----------------------------------------------------------------------

    def altas_bloqueadas(self) -> str | None:
        return self.base.kv_obtener(CLAVE_ALTAS_BLOQUEADAS) or None

    def bloquear_altas(self, motivo: str) -> None:
        self.base.kv_guardar(CLAVE_ALTAS_BLOQUEADAS, motivo)

    def desbloquear_altas(self) -> None:
        self.base.kv_guardar(CLAVE_ALTAS_BLOQUEADAS, "")

    def crear(self, telegram_id: int, nombre: str | None, ahora: datetime) -> Usuario:
        """Crea el usuario en estado alta. Solo después de comprobar que es miembro."""
        directorio = uuid.uuid4().hex
        with self.base.transaccion() as cx:
            cx.execute(
                "INSERT INTO usuarios(telegram_id, nombre, estado, paso_alta, directorio, "
                "creado, ultima_actividad, miembro_verificado_en) "
                "VALUES (?, ?, 'alta', 'politica', ?, ?, ?, ?)",
                (telegram_id, nombre, directorio, a_texto(ahora), a_texto(ahora), a_texto(ahora)),
            )
        usuario = self.obtener(telegram_id)
        assert usuario is not None
        ruta = self.directorio(usuario)
        ruta.mkdir(parents=True, exist_ok=True)
        os.chmod(ruta, 0o700)
        return usuario

    def requiere_politica(self, usuario: Usuario, version_vigente: int) -> bool:
        return usuario.politica_version is None or usuario.politica_version < version_vigente

    def aceptar_politica(self, usuario: Usuario, version: int, ahora: datetime) -> None:
        with self.base.transaccion() as cx:
            cx.execute(
                "UPDATE usuarios SET politica_version = ?, politica_aceptada_en = ? WHERE id = ?",
                (version, a_texto(ahora), usuario.id),
            )

    def fijar_paso(self, usuario: Usuario, paso: str | None) -> None:
        with self.base.transaccion() as cx:
            cx.execute("UPDATE usuarios SET paso_alta = ? WHERE id = ?", (paso, usuario.id))

    def completar_alta(self, usuario: Usuario) -> None:
        with self.base.transaccion() as cx:
            cx.execute(
                "UPDATE usuarios SET estado = 'activo', paso_alta = NULL "
                "WHERE id = ? AND estado = 'alta'",
                (usuario.id,),
            )

    def fijar_vacante_pendiente(self, usuario: Usuario, id_corto: str | None) -> None:
        with self.base.transaccion() as cx:
            cx.execute(
                "UPDATE usuarios SET vacante_pendiente = ? WHERE id = ?", (id_corto, usuario.id)
            )

    def tocar_actividad(self, usuario: Usuario, ahora: datetime) -> None:
        with self.base.transaccion() as cx:
            cx.execute(
                "UPDATE usuarios SET ultima_actividad = ?, aviso_inactividad_en = NULL "
                "WHERE id = ?",
                (a_texto(ahora), usuario.id),
            )

    # --- membresía del grupo ---------------------------------------------------------

    def membresia_vigente(self, usuario: Usuario, ahora: datetime, cache_min: float) -> bool:
        """True si la última comprobación positiva es reciente y no hace falta consultar."""
        verificado = usuario.miembro_verificado_en
        return (
            verificado is not None
            and usuario.estado != EstadoUsuario.SUSPENDIDO
            and ahora - verificado < timedelta(minutes=cache_min)
        )

    def aplicar_membresia(self, usuario: Usuario, membresia: Membresia, ahora: datetime) -> Usuario:
        """Suspende a quien salió del grupo (y cancela sus pendientes); reactiva a quien volvió."""
        with self.base.transaccion() as cx:
            if membresia == Membresia.MIEMBRO:
                cx.execute(
                    "UPDATE usuarios SET miembro_verificado_en = ? WHERE id = ?",
                    (a_texto(ahora), usuario.id),
                )
                if (
                    usuario.estado == EstadoUsuario.SUSPENDIDO
                    and usuario.motivo_estado == MOTIVO_FUERA_DEL_GRUPO
                ):
                    nuevo = "alta" if usuario.paso_alta else "activo"
                    cx.execute(
                        "UPDATE usuarios SET estado = ?, motivo_estado = NULL WHERE id = ?",
                        (nuevo, usuario.id),
                    )
            elif usuario.estado != EstadoUsuario.SUSPENDIDO:
                cx.execute(
                    "UPDATE usuarios SET estado = 'suspendido', motivo_estado = ? WHERE id = ?",
                    (MOTIVO_FUERA_DEL_GRUPO, usuario.id),
                )
                self._cancelar_pendientes(cx, usuario.id, MOTIVO_FUERA_DEL_GRUPO, ahora)
        actualizado = self.por_id(usuario.id)
        assert actualizado is not None
        return actualizado

    def _cancelar_pendientes(
        self, cx: sqlite3.Connection, usuario_id: int, motivo: str, ahora: datetime
    ) -> int:
        marcas = ", ".join("?" for _ in PENDIENTES)
        filas = cx.execute(
            f"SELECT id FROM postulaciones WHERE usuario_id = ? AND estado IN ({marcas})",
            (usuario_id, *PENDIENTES),
        ).fetchall()
        for fila in filas:
            cx.execute(
                "UPDATE postulaciones SET estado = 'cancelada', motivo = ?, actualizada = ? "
                "WHERE id = ?",
                (motivo, a_texto(ahora), fila["id"]),
            )
            cx.execute(
                "INSERT INTO postulacion_pasos(postulacion_id, ts, estado, paso, detalle) "
                "VALUES (?, ?, 'cancelada', 'cancelada', ?)",
                (fila["id"], a_texto(ahora), motivo),
            )
        return len(filas)

    # --- administración --------------------------------------------------------------

    def auditar(
        self, actor: int, accion: str, objetivo: str | None, ahora: datetime, detalle=None
    ) -> None:
        with self.base.transaccion() as cx:
            cx.execute(
                "INSERT INTO auditoria(ts, actor, accion, objetivo, detalle) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    a_texto(ahora),
                    actor,
                    accion,
                    objetivo,
                    json.dumps(detalle, ensure_ascii=False) if detalle is not None else None,
                ),
            )

    def suspender(self, usuario: Usuario, actor: int, ahora: datetime) -> None:
        with self.base.transaccion() as cx:
            cx.execute(
                "UPDATE usuarios SET estado = 'suspendido', motivo_estado = ? WHERE id = ?",
                (MOTIVO_ADMIN, usuario.id),
            )
            self._cancelar_pendientes(cx, usuario.id, MOTIVO_ADMIN, ahora)
        self.auditar(actor, "suspender", str(usuario.id), ahora)

    def reactivar(self, usuario: Usuario, actor: int, ahora: datetime) -> None:
        nuevo = "alta" if usuario.paso_alta else "activo"
        with self.base.transaccion() as cx:
            cx.execute(
                "UPDATE usuarios SET estado = ?, motivo_estado = NULL WHERE id = ?",
                (nuevo, usuario.id),
            )
        self.auditar(actor, "reactivar", str(usuario.id), ahora)

    def marcar_inactivo(self, usuario: Usuario) -> None:
        """El usuario bloqueó al bot (Forbidden): no se le envía ni se encola nada más."""
        with self.base.transaccion() as cx:
            cx.execute(
                "UPDATE usuarios SET estado = 'inactivo', motivo_estado = 'bot_bloqueado' "
                "WHERE id = ?",
                (usuario.id,),
            )

    # --- inactividad y baja ------------------------------------------------------------

    def por_avisar_inactividad(self, ahora: datetime, meses: int) -> list[Usuario]:
        limite = a_texto(ahora - timedelta(days=30 * meses))
        filas = self.base.cx.execute(
            "SELECT * FROM usuarios WHERE ultima_actividad < ? AND aviso_inactividad_en IS NULL",
            (limite,),
        ).fetchall()
        return [Usuario.de_fila(f) for f in filas]

    def marcar_aviso_inactividad(self, usuario: Usuario, ahora: datetime) -> None:
        with self.base.transaccion() as cx:
            cx.execute(
                "UPDATE usuarios SET aviso_inactividad_en = ? WHERE id = ?",
                (a_texto(ahora), usuario.id),
            )

    def por_borrar_inactividad(self, ahora: datetime) -> list[Usuario]:
        """Avisados hace más de 30 días sin actividad posterior (tocar_actividad borra el aviso)."""
        limite = a_texto(ahora - timedelta(days=DIAS_GRACIA_INACTIVIDAD))
        filas = self.base.cx.execute(
            "SELECT * FROM usuarios WHERE aviso_inactividad_en IS NOT NULL "
            "AND aviso_inactividad_en < ?",
            (limite,),
        ).fetchall()
        return [Usuario.de_fila(f) for f in filas]

    def borrar(self, usuario: Usuario, ahora: datetime) -> None:
        """Borra en forma definitiva todos sus datos. Solo queda la fecha de la baja."""
        ruta = self.directorio(usuario)
        if ruta.exists():
            shutil.rmtree(ruta)
        with self.base.transaccion() as cx:
            cx.execute("DELETE FROM usuarios WHERE id = ?", (usuario.id,))
            cx.execute("INSERT INTO bajas(ts) VALUES (?)", (a_texto(ahora),))
