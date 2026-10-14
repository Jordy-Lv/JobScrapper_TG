"""Logging a logs/AAAA-MM-DD.log y stdout (journald), con retención y máscara de secretos."""

from __future__ import annotations

import logging
import re
import sys
from collections.abc import Iterable
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

MASCARA = "***"
FORMATO = "%(asctime)s %(levelname)s %(name)s: %(message)s"

# Patrones que parecen secretos aunque no estén en la lista conocida
PATRONES_SECRETOS = (
    re.compile(r"\d{6,}:[A-Za-z0-9_-]{30,}"),  # token de bot de Telegram
    re.compile(r"sk-[A-Za-z0-9_-]{10,}"),  # clave de API estilo DeepSeek/OpenAI
)
_ARCHIVO_LOG = re.compile(r"^(\d{4}-\d{2}-\d{2})\.log$")


def enmascarar(texto: str, secretos: Iterable[str] = ()) -> str:
    """Reemplaza secretos conocidos y cualquier cosa con forma de token por ***."""
    for secreto in sorted((s for s in secretos if s), key=len, reverse=True):
        texto = texto.replace(secreto, MASCARA)
    for patron in PATRONES_SECRETOS:
        texto = patron.sub(MASCARA, texto)
    return texto


class FormateadorSeguro(logging.Formatter):
    """Formatea el registro completo (incluidas trazas) y luego enmascara secretos."""

    def __init__(self, secretos: Iterable[str] = (), zona: ZoneInfo | None = None) -> None:
        super().__init__(FORMATO)
        self.secretos = list(secretos)
        self.zona = zona

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:  # noqa: N802
        momento = datetime.fromtimestamp(record.created, self.zona)
        return momento.isoformat(timespec="seconds")

    def format(self, record: logging.LogRecord) -> str:
        return enmascarar(super().format(record), self.secretos)


def limpiar_logs(directorio: Path, retencion_dias: int, hoy: date) -> list[Path]:
    """Borra los logs diarios con más de ``retencion_dias`` de antigüedad."""
    borrados = []
    if not directorio.is_dir():
        return borrados
    for archivo in directorio.iterdir():
        coincidencia = _ARCHIVO_LOG.match(archivo.name)
        if not coincidencia:
            continue
        try:
            fecha = date.fromisoformat(coincidencia.group(1))
        except ValueError:
            continue
        if (hoy - fecha).days > retencion_dias:
            archivo.unlink()
            borrados.append(archivo)
    return borrados


def configurar(
    directorio: Path,
    retencion_dias: int,
    secretos: Iterable[str] = (),
    zona: str = "America/Bogota",
    nivel: int = logging.INFO,
) -> Path:
    """Configura el logger raíz y devuelve la ruta del log del día."""
    tz = ZoneInfo(zona)
    hoy = datetime.now(tz).date()
    directorio.mkdir(parents=True, exist_ok=True)
    ruta = directorio / f"{hoy.isoformat()}.log"

    formateador = FormateadorSeguro(secretos, tz)
    raiz = logging.getLogger()
    for handler in list(raiz.handlers):
        raiz.removeHandler(handler)
        handler.close()
    for handler in (
        logging.FileHandler(ruta, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ):
        handler.setFormatter(formateador)
        raiz.addHandler(handler)
    raiz.setLevel(nivel)
    # httpx registra cada URL a nivel INFO; la de Telegram lleva el token
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    for borrado in limpiar_logs(directorio, retencion_dias, hoy):
        logging.getLogger(__name__).info("Log antiguo eliminado: %s", borrado.name)
    return ruta
