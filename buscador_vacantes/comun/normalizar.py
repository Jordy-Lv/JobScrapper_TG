"""Normalización de texto para filtros y huellas de deduplicación."""

from __future__ import annotations

import hashlib
import html
import re
import unicodedata

_ESPACIOS = re.compile(r"\s+")
_NO_ALFANUM = re.compile(r"[^a-z0-9]+")

# Sufijos societarios y palabras que no distinguen a una empresa
_SUFIJOS_EMPRESA = re.compile(
    r"\b(s\s?a\s?s|s\s?a|ltda|limitada|s\s?en\s?c|e\s?u|s\s?c\s?a|inc|llc|corp|corporation"
    r"|sucursal|de colombia|colombia)\b"
)
# Empresas anónimas: la huella no puede usarse para cruzar fuentes
_EMPRESA_GENERICA = re.compile(
    r"confidencial|importante empresa|reconocida empresa|empresa del sector|empresa lider"
)


def normalizar_texto(texto: str | None) -> str:
    """Minúsculas, sin entidades HTML, sin tildes ni diacríticos y con espacios colapsados."""
    if not texto:
        return ""
    descompuesto = unicodedata.normalize("NFKD", html.unescape(texto).lower())
    sin_tildes = "".join(c for c in descompuesto if not unicodedata.combining(c))
    return _ESPACIOS.sub(" ", sin_tildes).strip()


def _solo_palabras(texto: str) -> str:
    return _ESPACIOS.sub(" ", _NO_ALFANUM.sub(" ", texto)).strip()


def normalizar_titulo(titulo: str | None) -> str:
    return _solo_palabras(normalizar_texto(titulo))


def normalizar_empresa(empresa: str | None) -> str:
    base = _solo_palabras(normalizar_texto(empresa))
    return _ESPACIOS.sub(" ", _SUFIJOS_EMPRESA.sub(" ", base)).strip()


def huella(titulo: str | None, empresa: str | None, clave: str) -> str:
    """Huella de título + empresa normalizados.

    Si la empresa está vacía o es anónima ("Importante empresa del sector"), dos vacantes
    distintas compartirían huella; en ese caso la huella se basa en la clave de la fuente.
    """
    empresa_norm = normalizar_empresa(empresa)
    if not empresa_norm or _EMPRESA_GENERICA.search(empresa_norm):
        base = f"clave|{clave}"
    else:
        base = f"{normalizar_titulo(titulo)}|{empresa_norm}"
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:20]


def compilar_terminos(terminos: list[str]) -> re.Pattern[str] | None:
    """Compila términos a una regex con límites de palabra sobre texto normalizado.

    Usa lookarounds alfanuméricos en lugar de ``\\b`` para que términos como ``.net``,
    ``c#`` o ``c++`` también funcionen, y acepta el plural de los términos de más de 3 letras.
    Devuelve None si la lista está vacía.
    """
    normalizados = sorted(
        {normalizar_texto(t) for t in terminos if t.strip()}, key=len, reverse=True
    )
    if not normalizados:
        return None

    def patron(termino: str) -> str:
        base = re.escape(termino).replace(r"\ ", r"\s+")
        # Plural opcional ("practicantes", "pasantias"); no en términos cortos como "it" → "its"
        if len(termino) > 3 and termino[-1].isalpha():
            base += "(?:es|s)?"
        return base

    alternativas = "|".join(patron(t) for t in normalizados)
    return re.compile(rf"(?<![a-z0-9])(?:{alternativas})(?![a-z0-9])")


def coincidencias(patron: re.Pattern[str] | None, texto_normalizado: str) -> list[str]:
    if patron is None:
        return []
    return [m.group(0) for m in patron.finditer(texto_normalizado)]
