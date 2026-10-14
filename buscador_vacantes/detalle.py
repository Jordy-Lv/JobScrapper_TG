"""Lectura y recorte de la descripción de una oferta (página de detalle)."""

from __future__ import annotations

import re
from functools import lru_cache

from bs4 import BeautifulSoup

from buscador_vacantes.normalizar import compilar_terminos, normalizar_texto

# Bloque de descripción de la página de invitados de LinkedIn
SELECTORES_DESCRIPCION = "div.description__text, section.show-more-less-html"
MAX_EXTRA_MODALIDAD = 1000  # caracteres que se añaden con las frases de modalidad del final
MAX_FRASE = 300  # una frase más larga se recorta alrededor del término de modalidad
_FRASES = re.compile(r"(?<=[.!?;:])\s+")
_ESPACIOS = re.compile(r"\s+")


def limpiar_texto(texto: str) -> str:
    return _ESPACIOS.sub(" ", texto).strip()


def extraer_descripcion(html: str) -> str | None:
    """Texto limpio del bloque de descripción; ``None`` si el HTML no lo trae o está vacío."""
    bloque = BeautifulSoup(html, "lxml").select_one(SELECTORES_DESCRIPCION)
    if bloque is None:
        return None
    return limpiar_texto(bloque.get_text(" ")) or None


@lru_cache(maxsize=8)
def _patron(terminos: tuple[str, ...]) -> re.Pattern[str] | None:
    return compilar_terminos(list(terminos))


def _hasta_palabra(texto: str, maximo: int) -> str:
    """Los primeros ``maximo`` caracteres sin partir la última palabra."""
    if len(texto) <= maximo:
        return texto
    corte = texto[:maximo]
    if not texto[maximo].isspace():
        corte = corte.rpartition(" ")[0] or corte
    return corte.rstrip()


def _ventana(frase: str, patron: re.Pattern[str]) -> str:
    """La frase, o si es muy larga, el tramo alrededor de su primer término de modalidad."""
    if len(frase) <= MAX_FRASE:
        return frase
    encontrada = patron.search(normalizar_texto(frase))
    centro = encontrada.start() if encontrada else 0
    inicio = max(0, centro - MAX_FRASE // 2)
    tramo = frase[inicio : inicio + MAX_FRASE]
    if inicio > 0:
        tramo = tramo.partition(" ")[2] or tramo
    return _hasta_palabra(tramo, MAX_FRASE)


def recortar_descripcion(texto: str, maximo: int, terminos_modalidad: list[str]) -> str:
    """Primeros ``maximo`` caracteres y, hasta ``MAX_EXTRA_MODALIDAD`` más, las frases posteriores
    que mencionan la modalidad (remoto, híbrido o presencial).

    Así lo que decide la modalidad no se pierde si está al final del anuncio. Nunca parte una
    palabra por la mitad.
    """
    texto = limpiar_texto(texto)
    if len(texto) <= maximo:
        return texto
    inicio = _hasta_palabra(texto, maximo)
    patron = _patron(tuple(terminos_modalidad))
    if patron is None:
        return inicio
    extra: list[str] = []
    usado = 0
    for frase in _FRASES.split(texto[len(inicio) :].strip()):
        if not patron.search(normalizar_texto(frase)):
            continue
        frase = _ventana(frase, patron)
        if usado + len(frase) + 1 > MAX_EXTRA_MODALIDAD:
            break
        extra.append(frase)
        usado += len(frase) + 1
    return f"{inicio} … {' '.join(extra)}" if extra else inicio
