"""Cifrado de datos sensibles de los usuarios (claves de Gemini y correos) con Fernet.

La clave maestra vive en ASISTENTE_CLAVE_CIFRADO (.env). Si se pierde, lo cifrado no se
recupera: cada usuario debe registrar de nuevo su clave de Gemini. Hay que respaldarla.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from buscador_vacantes.asistente.datos import BaseAsistente
from buscador_vacantes.comun.config import ErrorConfiguracion

# (tabla, columna cifrada, columnas de la clave primaria)
COLUMNAS_CIFRADAS = (
    ("usuarios", "gemini_clave", ("id",)),
    ("cuentas_portal", "correo_cifrado", ("usuario_id", "plataforma")),
)


class ClaveInvalida(ErrorConfiguracion):
    """La clave maestra falta, no es una clave Fernet o no descifra los datos guardados."""


def generar_clave() -> str:
    return Fernet.generate_key().decode()


def _fernet(clave: str | None) -> Fernet:
    if not clave:
        raise ClaveInvalida(
            "Falta ASISTENTE_CLAVE_CIFRADO en .env. Genérala con "
            "`uv run buscador.py asistente generar-clave` y respáldala."
        )
    try:
        return Fernet(clave.encode())
    except (ValueError, TypeError) as exc:
        raise ClaveInvalida(
            "ASISTENTE_CLAVE_CIFRADO no es una clave válida (debe ser la que genera "
            "`asistente generar-clave`)"
        ) from exc


class Cifrador:
    def __init__(self, clave: str | None) -> None:
        self._f = _fernet(clave)

    def cifrar(self, texto: str) -> str:
        return self._f.encrypt(texto.encode()).decode()

    def descifrar(self, token: str) -> str:
        try:
            return self._f.decrypt(token.encode()).decode()
        except InvalidToken as exc:
            raise ClaveInvalida(
                "No se pudo descifrar un dato guardado: ASISTENTE_CLAVE_CIFRADO no es la "
                "clave con la que se cifró"
            ) from exc

    def cifrar_bytes(self, contenido: bytes) -> bytes:
        """Cifra un archivo (los documentos del usuario); lo guardado nunca es el PDF en claro."""
        return self._f.encrypt(contenido)

    def descifrar_bytes(self, token: bytes) -> bytes:
        try:
            return self._f.decrypt(token)
        except InvalidToken as exc:
            raise ClaveInvalida(
                "No se pudo descifrar un documento guardado: ASISTENTE_CLAVE_CIFRADO no es la "
                "clave con la que se cifró"
            ) from exc

    def comprobar(self, base: BaseAsistente) -> None:
        """Descifra un dato guardado (si hay) para detectar una clave equivocada al arrancar."""
        for tabla, columna, _ in COLUMNAS_CIFRADAS:
            fila = base.cx.execute(
                f"SELECT {columna} AS valor FROM {tabla} WHERE {columna} IS NOT NULL LIMIT 1"
            ).fetchone()
            if fila:
                self.descifrar(fila["valor"])
        documento = base.cx.execute("SELECT ruta FROM documentos_usuario LIMIT 1").fetchone()
        if documento and Path(documento["ruta"]).is_file():
            self.descifrar_bytes(Path(documento["ruta"]).read_bytes())


def huella(texto: str) -> str:
    """Hash para comparar correos sin descifrarlos (normalizado a minúsculas)."""
    return hashlib.sha256(texto.strip().lower().encode()).hexdigest()


def rotar(base: BaseAsistente, clave_actual: str | None, clave_nueva: str) -> int:
    """Vuelve a cifrar todos los datos con la clave nueva, en una sola transacción.

    Devuelve cuántos valores se rotaron. Si algo falla, no cambia nada.
    """
    actual = _fernet(clave_actual)
    nueva = _fernet(clave_nueva)
    rotador = MultiFernet([nueva, actual])
    total = 0
    nuevos: list[tuple[Path, Path]] = []  # (archivo con la clave nueva, el que reemplaza)
    try:
        with base.transaccion() as cx:
            for tabla, columna, pk in COLUMNAS_CIFRADAS:
                columnas_pk = ", ".join(pk)
                filas = cx.execute(
                    f"SELECT {columnas_pk}, {columna} AS valor FROM {tabla} "
                    f"WHERE {columna} IS NOT NULL"
                ).fetchall()
                for fila in filas:
                    try:
                        rotado = rotador.rotate(fila["valor"].encode()).decode()
                    except InvalidToken as exc:
                        raise ClaveInvalida(
                            f"Un valor de {tabla}.{columna} no se descifra con la clave actual; "
                            "no se rotó nada"
                        ) from exc
                    condicion = " AND ".join(f"{c} = ?" for c in pk)
                    cx.execute(
                        f"UPDATE {tabla} SET {columna} = ? WHERE {condicion}",
                        (rotado, *(fila[c] for c in pk)),
                    )
                    total += 1
            for fila in cx.execute("SELECT ruta FROM documentos_usuario").fetchall():
                ruta = Path(fila["ruta"])
                if not ruta.is_file():
                    continue
                try:
                    rotado = rotador.rotate(ruta.read_bytes())
                except InvalidToken as exc:
                    raise ClaveInvalida(
                        f"El documento {ruta.name} no se descifra con la clave actual; "
                        "no se rotó nada"
                    ) from exc
                nuevo = ruta.with_name(ruta.name + ".nuevo")
                nuevo.write_bytes(rotado)
                nuevos.append((nuevo, ruta))
                total += 1
    except BaseException:
        for nuevo, _ in nuevos:
            nuevo.unlink(missing_ok=True)
        raise
    for nuevo, ruta in nuevos:  # la base ya está confirmada: los archivos pasan a la clave nueva
        nuevo.replace(ruta)
    return total
