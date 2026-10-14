"""Fechas de publicación en español → datetime en hora de Colombia, y fechas relativas."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from buscador_vacantes.normalizar import normalizar_texto

ZONA = ZoneInfo("America/Bogota")

MESES = {
    "enero": 1, "ene": 1, "january": 1, "jan": 1,
    "febrero": 2, "feb": 2, "february": 2,
    "marzo": 3, "mar": 3, "march": 3,
    "abril": 4, "abr": 4, "april": 4, "apr": 4,
    "mayo": 5, "may": 5,
    "junio": 6, "jun": 6, "june": 6,
    "julio": 7, "jul": 7, "july": 7,
    "agosto": 8, "ago": 8, "august": 8, "aug": 8,
    "septiembre": 9, "setiembre": 9, "sep": 9, "sept": 9, "set": 9, "september": 9,
    "octubre": 10, "oct": 10, "october": 10,
    "noviembre": 11, "nov": 11, "november": 11,
    "diciembre": 12, "dic": 12, "december": 12, "dec": 12,
}  # fmt: skip

_RELATIVA = re.compile(
    r"hace\s+(?:mas\s+de\s+)?(\d+|un|una)\s*"
    r"(segundos?|minutos?|min|horas?|h|dias?|semanas?|mes(?:es)?)\b"
)
_ISO = re.compile(r"(\d{4})-(\d{2})-(\d{2})(?:[t ](\d{2}):(\d{2})(?::(\d{2}))?)?")
_NUMERICA = re.compile(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})\b")
_TEXTUAL = re.compile(r"\b(\d{1,2})\s+(?:de\s+)?([a-z]{3,10})\.?(?:\s+(?:de\s+|del\s+)?(\d{4}))?\b")


def ahora_colombia() -> datetime:
    return datetime.now(ZONA)


def _unidad(texto: str) -> timedelta:
    if texto.startswith("seg"):
        return timedelta(seconds=1)
    if texto.startswith("min"):
        return timedelta(minutes=1)
    if texto.startswith("h"):
        return timedelta(hours=1)
    if texto.startswith("semana"):
        return timedelta(weeks=1)
    if texto.startswith("mes"):
        return timedelta(days=30)
    return timedelta(days=1)


def _fecha_local(anio: int, mes: int, dia: int) -> datetime | None:
    try:
        return datetime(anio, mes, dia, 12, 0, tzinfo=ZONA)
    except ValueError:
        return None


def desde_epoch(segundos: float | int | None) -> datetime | None:
    if not segundos:
        return None
    return datetime.fromtimestamp(float(segundos), ZONA)


def interpretar_fecha(texto: str | None, ahora: datetime | None = None) -> datetime | None:
    """Convierte textos como "Hace 2 días", "ayer", "2026-10-01" o "1 de octubre" a datetime.

    Las fechas sin hora quedan a las 12:00 de Colombia. Devuelve None si no se reconoce.
    """
    if not texto:
        return None
    ahora = (ahora or ahora_colombia()).astimezone(ZONA)
    t = normalizar_texto(texto)

    if re.search(r"\b(hoy|today|justo ahora|recien publicad[ao]|ahora mismo)\b", t):
        return ahora
    if re.search(r"\b(ayer|yesterday)\b", t):
        return ahora - timedelta(days=1)
    if re.search(r"\bantier|anteayer\b", t):
        return ahora - timedelta(days=2)

    relativa = _RELATIVA.search(t)
    if relativa:
        cantidad = 1 if relativa.group(1) in ("un", "una") else int(relativa.group(1))
        return ahora - cantidad * _unidad(relativa.group(2))

    iso = _ISO.search(t)
    if iso:
        anio, mes, dia = (int(x) for x in iso.group(1, 2, 3))
        if iso.group(4):
            try:
                return datetime.fromisoformat(texto.strip().replace("Z", "+00:00")).astimezone(ZONA)
            except ValueError:
                pass
        return _fecha_local(anio, mes, dia)

    numerica = _NUMERICA.search(t)
    if numerica:
        dia, mes, anio = (int(x) for x in numerica.groups())
        if anio < 100:
            anio += 2000
        return _fecha_local(anio, mes, dia)

    for textual in _TEXTUAL.finditer(t):
        mes = MESES.get(textual.group(2))
        if not mes:
            continue
        dia = int(textual.group(1))
        anio = int(textual.group(3)) if textual.group(3) else ahora.year
        fecha = _fecha_local(anio, mes, dia)
        # "28 dic" leído en enero corresponde al año anterior
        if fecha and not textual.group(3) and fecha > ahora + timedelta(days=1):
            fecha = _fecha_local(anio - 1, mes, dia)
        return fecha
    return None


def fecha_relativa(publicada: datetime | None, ahora: datetime | None = None) -> str | None:
    """ "hoy", "ayer" o "hace N días" según el calendario de Colombia."""
    if publicada is None:
        return None
    ahora = (ahora or ahora_colombia()).astimezone(ZONA)
    dias = (ahora.date() - publicada.astimezone(ZONA).date()).days
    if dias <= 0:
        return "hoy"
    if dias == 1:
        return "ayer"
    return f"hace {dias} días"
