"""Destinos de las vacantes de LinkedIn: limpiar la URL de destino y clasificarla por familia.

Funciones puras, sin red: las usa la medición de destinos (`medir-destinos-linkedin`) y el
clasificador de destino de la postulación en LinkedIn (`postular-linkedin`).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from urllib.parse import parse_qsl, unquote, urlencode, urlparse, urlunparse

PROPIO = "propio"  # familia de un destino que no coincide con ningún patrón
_PARAMETROS_RASTREO = {"trk", "refid", "trackingid"}
_ENVOLTORIOS = ("/safety/go", "externalapply")  # enlaces de LinkedIn que traen el destino en `url`


def limpiar_destino(url: str) -> str:
    """El destino real de una URL: desenvuelve el `url=` de LinkedIn y quita los parámetros de
    rastreo (`trk`, `refId`, `trackingId` y `utm_*`)."""
    url = (url or "").strip()
    partes = urlparse(url)
    if "linkedin.com" in (partes.hostname or "") and any(
        e in partes.path.lower() for e in _ENVOLTORIOS
    ):
        interno = dict(parse_qsl(partes.query)).get("url")
        if interno:
            return limpiar_destino(unquote(interno) if "%" in interno[:12] else interno)
    if partes.scheme not in ("http", "https"):
        return url
    consulta = [
        (k, v)
        for k, v in parse_qsl(partes.query, keep_blank_values=True)
        if k.lower() not in _PARAMETROS_RASTREO and not k.lower().startswith("utm_")
    ]
    return urlunparse(partes._replace(query=urlencode(consulta)))


def familia_de(url: str, familias: Mapping[str, Iterable[str]]) -> str:
    """La familia de ATS del host de `url` (host igual al patrón o terminado en `.patrón`), o
    `propio`. Gana el patrón más largo: `pandape.computrabajo.com` antes que `computrabajo.com`."""
    host = (urlparse(url or "").hostname or "").lower().removeprefix("www.")
    if not host:
        return PROPIO
    patrones = sorted(
        ((p.lower().strip("."), f) for f, ps in familias.items() for p in ps),
        key=lambda par: len(par[0]),
        reverse=True,
    )
    for patron, familia in patrones:
        if host == patron or host.endswith("." + patron):
            return familia
    return PROPIO
