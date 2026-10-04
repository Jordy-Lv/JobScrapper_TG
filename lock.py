"""Exclusión mutua entre corridas con fcntl.flock (no bloqueante)."""

from __future__ import annotations

import fcntl
import os
import time
from pathlib import Path
from types import TracebackType


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
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError as exc:
                if time.monotonic() >= limite:
                    os.close(fd)
                    raise CorridaActiva(f"Hay otra corrida activa (lock en {self.ruta})") from exc
                time.sleep(min(1.0, max(limite - time.monotonic(), 0.01)))
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
            fcntl.flock(self._fd, fcntl.LOCK_UN)
            os.close(self._fd)
            self._fd = None
