"""Vinculación de la extensión: códigos temporales de un solo uso y tokens por navegador.

El servidor guarda solo el SHA-256 de cada token. Un token permite ver la cola de su usuario y
reportar resultados; no da acceso a contraseñas ni sesiones (no existen en el servidor).
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from buscador_vacantes.asistente.datos import BaseAsistente
from buscador_vacantes.estado import a_texto, de_texto

VIGENCIA_CODIGO = timedelta(minutes=10)
ALFABETO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # sin 0/O ni 1/I para escribirlo a mano


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def normalizar_codigo(codigo: str) -> str:
    return "".join(c for c in codigo.upper() if c in ALFABETO)


@dataclass
class Navegador:
    id: int
    usuario_id: int
    nombre: str | None
    version: str | None
    ultimo_latido: datetime | None


def crear_codigo(base: BaseAsistente, usuario_id: int, ahora: datetime) -> str:
    """Código de 8 caracteres (se muestra como XXXX-XXXX). Anula los anteriores sin usar."""
    codigo = "".join(secrets.choice(ALFABETO) for _ in range(8))
    with base.transaccion() as cx:
        cx.execute(
            "UPDATE codigos_vinculo SET usado = 1 WHERE usuario_id = ? AND usado = 0",
            (usuario_id,),
        )
        cx.execute(
            "INSERT INTO codigos_vinculo(codigo, usuario_id, creado, vence) VALUES (?, ?, ?, ?)",
            (codigo, usuario_id, a_texto(ahora), a_texto(ahora + VIGENCIA_CODIGO)),
        )
    return codigo


def mostrar_codigo(codigo: str) -> str:
    return f"{codigo[:4]}-{codigo[4:]}"


def canjear(
    base: BaseAsistente, codigo: str, nombre: str | None, version: str | None, ahora: datetime
) -> tuple[str, int] | None:
    """Devuelve (token, usuario_id) o None si el código no existe, venció o ya se usó."""
    codigo = normalizar_codigo(codigo)
    with base.transaccion() as cx:
        fila = cx.execute(
            "SELECT usuario_id, vence, usado FROM codigos_vinculo WHERE codigo = ?", (codigo,)
        ).fetchone()
        if not fila or fila["usado"] or de_texto(fila["vence"]) < ahora:
            return None
        cur = cx.execute(
            "UPDATE codigos_vinculo SET usado = 1 WHERE codigo = ? AND usado = 0", (codigo,)
        )
        if not cur.rowcount:
            return None
        token = secrets.token_urlsafe(32)
        cx.execute(
            "INSERT INTO navegadores(usuario_id, token_hash, nombre, version, creado, "
            "ultimo_latido) VALUES (?, ?, ?, ?, ?, ?)",
            (fila["usuario_id"], hash_token(token), (nombre or "")[:60] or None, version,
             a_texto(ahora), a_texto(ahora)),
        )  # fmt: skip
    return token, fila["usuario_id"]


def autenticar(base: BaseAsistente, token: str) -> Navegador | None:
    fila = base.cx.execute(
        "SELECT n.id, n.usuario_id, n.nombre, n.version, n.ultimo_latido FROM navegadores n "
        "JOIN usuarios u ON u.id = n.usuario_id "
        "WHERE n.token_hash = ? AND n.revocado = 0 AND u.estado IN ('activo', 'alta')",
        (hash_token(token),),
    ).fetchone()
    if not fila:
        return None
    return Navegador(
        fila["id"], fila["usuario_id"], fila["nombre"], fila["version"],
        de_texto(fila["ultimo_latido"]),
    )  # fmt: skip


def navegadores_de(base: BaseAsistente, usuario_id: int) -> list[Navegador]:
    filas = base.cx.execute(
        "SELECT id, usuario_id, nombre, version, ultimo_latido FROM navegadores "
        "WHERE usuario_id = ? AND revocado = 0 ORDER BY id",
        (usuario_id,),
    ).fetchall()
    return [
        Navegador(f["id"], f["usuario_id"], f["nombre"], f["version"], de_texto(f["ultimo_latido"]))
        for f in filas
    ]


def revocar(base: BaseAsistente, usuario_id: int, navegador_id: int | None = None) -> int:
    """Revoca un navegador (o todos los del usuario). Devuelve cuántos."""
    with base.transaccion() as cx:
        if navegador_id is None:
            cur = cx.execute(
                "UPDATE navegadores SET revocado = 1 WHERE usuario_id = ? AND revocado = 0",
                (usuario_id,),
            )
        else:
            cur = cx.execute(
                "UPDATE navegadores SET revocado = 1 WHERE id = ? AND usuario_id = ?",
                (navegador_id, usuario_id),
            )
        return cur.rowcount
