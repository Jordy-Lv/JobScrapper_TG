"""LinkedIn: API pública para invitados (HTML de tarjetas, sin sesión)."""

from __future__ import annotations

import re
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

from buscador_vacantes.fechas import interpretar_fecha
from buscador_vacantes.fuentes.base import CambioHTML, Fuente, Peticion
from buscador_vacantes.modelo import Vacante

URL_BUSQUEDA = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
URL_OFERTA = "https://co.linkedin.com/jobs/view/{id}"
_URN = re.compile(r"urn:li:jobPosting:(\d+)")


def _texto(nodo) -> str:
    return " ".join(nodo.get_text(" ").split()) if nodo else ""


class LinkedIn(Fuente):
    nombre = "linkedin"
    selectores = [
        "div.base-search-card[data-entity-urn]",
        "h3.base-search-card__title",
        "h4.base-search-card__subtitle a",
        "span.job-search-card__location",
        "time[datetime]",
        "span.job-search-card__salary-info",
    ]

    def construir_peticion(self, keyword: str, pagina: int = 1) -> Peticion:
        return Peticion(
            URL_BUSQUEDA,
            params={
                "keywords": keyword,
                "location": self.opciones.get("location", "Colombia"),
                "f_E": self.opciones.get("f_E", "1,2"),
                "f_TPR": self.opciones.get("f_TPR", "r86400"),
                "start": 0,
            },
        )

    def parsear(self, respuesta: httpx.Response, keyword: str, ahora: datetime) -> list[Vacante]:
        # Sin resultados LinkedIn responde 200 con el cuerpo vacío
        if not respuesta.text.strip():
            return []
        sopa = BeautifulSoup(respuesta.text, "lxml")
        tarjetas = sopa.select(
            "div.base-search-card[data-entity-urn], div.base-card[data-entity-urn]"
        )
        if not tarjetas:
            raise CambioHTML("No se encontraron tarjetas div.base-search-card")
        vacantes = []
        for tarjeta in tarjetas:
            urn = _URN.search(tarjeta.get("data-entity-urn", ""))
            titulo = _texto(tarjeta.select_one("h3.base-search-card__title"))
            if not urn or not titulo:
                continue
            fecha_nodo = tarjeta.select_one("time")
            publicada = None
            if fecha_nodo is not None:
                # "Hace 9 horas" es más preciso que datetime="AAAA-MM-DD"
                publicada = interpretar_fecha(_texto(fecha_nodo), ahora) or interpretar_fecha(
                    fecha_nodo.get("datetime"), ahora
                )
            vacantes.append(
                Vacante(
                    fuente=self.nombre,
                    id_fuente=urn.group(1),
                    titulo=titulo,
                    empresa=_texto(tarjeta.select_one("h4.base-search-card__subtitle")),
                    url=URL_OFERTA.format(id=urn.group(1)),
                    keyword=keyword,
                    ubicacion=_texto(tarjeta.select_one("span.job-search-card__location")) or None,
                    salario=_texto(tarjeta.select_one("span.job-search-card__salary-info")) or None,
                    publicada=publicada,
                )
            )
        return vacantes
