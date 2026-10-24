"""Documentos PDF del usuario además del CV (certificado de notas, carta, portafolio…).

Los guarda cifrados con la misma clave maestra que el resto (``cifrado.py``) en la carpeta del
usuario: el archivo en disco nunca es el PDF en claro. Se borran con la cuenta (la carpeta y las
filas en cascada) y el usuario puede verlos o borrarlos cuando quiera. Un formulario que pide un
archivo recibe el documento cuyo tipo corresponde a la etiqueta del campo.
"""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from buscador_vacantes.asistente.cifrado import Cifrador
from buscador_vacantes.asistente.datos import BaseAsistente
from buscador_vacantes.asistente.usuarios import Usuario, Usuarios
from buscador_vacantes.comun.estado import a_texto, de_texto

# Tipos que un formulario puede pedir por su etiqueta; «otro» se guarda con el nombre que el
# usuario le puso y nunca se adjunta solo.
TIPOS_DOCUMENTO = {
    "certificado_notas": "Certificado de notas",
    "carta": "Carta de presentación",
    "portafolio": "Portafolio",
    "otro": "Otro documento",
}
MAX_DOCUMENTOS = 10  # por usuario
MAX_NOMBRE = 60


class ErrorDocumento(ValueError):
    """El documento no se puede guardar; el mensaje se le muestra al usuario."""


@dataclass
class Documento:
    id: int
    usuario_id: int
    tipo: str
    nombre: str
    ruta: Path
    bytes: int
    creado: datetime

    @property
    def etiqueta(self) -> str:
        """Cómo se lista: el tipo, o el nombre que el usuario le dio a uno de tipo «otro»."""
        if self.tipo == "otro":
            return self.nombre
        return TIPOS_DOCUMENTO.get(self.tipo, self.tipo)


class Documentos:
    def __init__(self, base: BaseAsistente, cifrador: Cifrador, usuarios: Usuarios) -> None:
        self.base = base
        self.cifrador = cifrador
        self.usuarios = usuarios

    @staticmethod
    def _documento(fila) -> Documento:
        return Documento(
            fila["id"], fila["usuario_id"], fila["tipo"], fila["nombre"], Path(fila["ruta"]),
            fila["bytes"], de_texto(fila["creado"]),
        )  # fmt: skip

    def listar(self, usuario_id: int) -> list[Documento]:
        filas = self.base.cx.execute(
            "SELECT * FROM documentos_usuario WHERE usuario_id = ? ORDER BY id", (usuario_id,)
        ).fetchall()
        return [self._documento(f) for f in filas]

    def por_tipo(self, usuario_id: int, tipo: str) -> Documento | None:
        """El documento más reciente de ese tipo, o None."""
        fila = self.base.cx.execute(
            "SELECT * FROM documentos_usuario WHERE usuario_id = ? AND tipo = ? "
            "ORDER BY id DESC LIMIT 1",
            (usuario_id, tipo),
        ).fetchone()
        return self._documento(fila) if fila else None

    def obtener(self, usuario_id: int, documento_id: int) -> Documento | None:
        fila = self.base.cx.execute(
            "SELECT * FROM documentos_usuario WHERE id = ? AND usuario_id = ?",
            (documento_id, usuario_id),
        ).fetchone()
        return self._documento(fila) if fila else None

    def leer(self, documento: Documento) -> bytes:
        """El PDF en claro, descifrado del archivo guardado."""
        return self.cifrador.descifrar_bytes(documento.ruta.read_bytes())

    def guardar(
        self, usuario: Usuario, tipo: str, nombre: str, contenido: bytes, ahora: datetime
    ) -> Documento:
        """Guarda el PDF cifrado. Un tipo conocido reemplaza al anterior del mismo tipo; los de
        tipo «otro» se acumulan hasta `MAX_DOCUMENTOS`."""
        if tipo not in TIPOS_DOCUMENTO:
            raise ErrorDocumento("Ese tipo de documento no existe.")
        nombre = " ".join(nombre.split())[:MAX_NOMBRE]
        if tipo == "otro" and not nombre:
            raise ErrorDocumento("Ponle un nombre al documento.")
        anterior = self.por_tipo(usuario.id, tipo) if tipo != "otro" else None
        if anterior is None and len(self.listar(usuario.id)) >= MAX_DOCUMENTOS:
            raise ErrorDocumento(
                f"Ya tienes {MAX_DOCUMENTOS} documentos; borra alguno con /documentos."
            )
        carpeta = self.usuarios.directorio(usuario) / "documentos"
        carpeta.mkdir(parents=True, exist_ok=True)
        os.chmod(carpeta, 0o700)
        ruta = carpeta / f"{secrets.token_hex(8)}.pdf.cif"
        ruta.write_bytes(self.cifrador.cifrar_bytes(contenido))
        os.chmod(ruta, 0o600)
        with self.base.transaccion() as cx:
            cur = cx.execute(
                "INSERT INTO documentos_usuario(usuario_id, tipo, nombre, ruta, bytes, creado) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (usuario.id, tipo, nombre or TIPOS_DOCUMENTO[tipo], str(ruta), len(contenido),
                 a_texto(ahora)),
            )  # fmt: skip
            nuevo = cur.lastrowid
        if anterior is not None:
            self.borrar(usuario.id, anterior.id)
        guardado = self.obtener(usuario.id, nuevo)
        assert guardado is not None
        return guardado

    def borrar(self, usuario_id: int, documento_id: int) -> bool:
        documento = self.obtener(usuario_id, documento_id)
        if documento is None:
            return False
        with self.base.transaccion() as cx:
            cx.execute("DELETE FROM documentos_usuario WHERE id = ?", (documento_id,))
        documento.ruta.unlink(missing_ok=True)
        return True
