"""Exclusión mutua entre corridas con fcntl.flock (no bloqueante).

En Windows, donde no existe fcntl, se usa msvcrt.locking: solo para desarrollo y pruebas.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from types import TracebackType

if sys.platform == "win32":
    import msvcrt

    def _bloquear(fd: int) -> None:
        os.lseek(fd, 0, os.SEEK_SET)
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            raise BlockingIOError(str(exc)) from exc

    def _liberar(fd: int) -> None:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)

else:
    import fcntl

    def _bloquear(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _liberar(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_UN)


class CorridaActiva(Exception):
    """Ya hay otra corrida en curso."""


class Lock:
    """Con ``esperar_s`` > 0 reintenta hasta ese tiempo antes de rendirse (resumen diario)."""

    def __init__(self, ruta: Path, esperar_s: float = 0) -> None:
        self.ruta = ruta
        self.esperar_s = esperar_s
        self._fd: int | None = None

    def __enter__(self) -> Lock:
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.ruta, os.O_RDWR | os.O_CREAT, 0o600)
        limite = time.monotonic() + self.esperar_s
        while True:
            try:
                _bloquear(fd)
                break
            except BlockingIOError as exc:
                if time.monotonic() >= limite:
                    os.close(fd)
                    raise CorridaActiva(f"Hay otra corrida activa (lock en {self.ruta})") from exc
                time.sleep(min(1.0, max(limite - time.monotonic(), 0.01)))
        if sys.platform != "win32":
            # En Windows la región bloqueada impide truncar: el pid es solo informativo
            os.ftruncate(fd, 0)
            os.write(fd, str(os.getpid()).encode())
        self._fd = fd
        return self

    def __exit__(
        self,
        tipo: type[BaseException] | None,
        valor: BaseException | None,
        traza: TracebackType | None,
    ) -> None:
        if self._fd is not None:
            _liberar(self._fd)
            os.close(self._fd)
            self._fd = None
