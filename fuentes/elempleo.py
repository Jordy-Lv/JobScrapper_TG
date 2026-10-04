"""elempleo.com: listado HTML con los datos de cada oferta en data-ga4-offerdata (JSON)."""

from __future__ import annotations

import json
import re
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

from fechas import interpretar_fecha
from fuentes.base import CambioHTML, Fuente, Peticion
from modelo import Vacante
from normalizar import normalizar_texto

URL_BASE = "https://www.elempleo.com"
MAX_DESCRIPCION = 600
SALARIOS_VACIOS = {"a convenir", "salario a convenir", "no especificado", "confidencial", ""}
MODALIDADES = {"presencial": "Presencial", "hibrido": "Híbrido", "remoto": "Remoto"}


def _texto(nodo) -> str:
    return " ".join(nodo.get_text(" ").split()) if nodo else ""


def slug(keyword: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", normalizar_texto(keyword)).strip("-")


def _dato_rotulado(item, rotulo: str) -> str:
    """Valor de los bloques "valor / rótulo" de la columna derecha (Salario, Modalidad…)."""
    for bloque in item.select("div.small"):
        etiqueta = bloque.select_one(".small-text")
        if etiqueta and normalizar_texto(_texto(etiqueta)) == rotulo:
            valor = bloque.find("div")
            return _texto(valor)
    return ""


class Elempleo(Fuente):
    nombre = "elempleo"
    status_sin_resultados = frozenset({404})
    selectores = [
        "div.result-item [data-ga4-offerdata][data-url]",
        "data-ga4-offerdata: id, title, company, location, salary",
        ".js-offer-date",
        "div.small > .small-text 'Modalidad laboral'",
        "li.result-info-hover-li-description",
    ]

    def construir_peticion(self, keyword: str) -> Peticion:
        filtro = self.opciones.get("filtro_fecha", "hace-1-semana")
        return Peticion(f"{URL_BASE}/co/ofertas-empleo/{filtro}/trabajo-{slug(keyword)}")

    def parsear(self, respuesta: httpx.Response, keyword: str, ahora: datetime) -> list[Vacante]:
        sopa = BeautifulSoup(respuesta.text, "lxml")
        items = sopa.select("div.result-item")
        if not items:
            raise CambioHTML("No se encontraron div.result-item")
        vacantes = []
        for item in items:
            nodo = item.select_one("[data-ga4-offerdata][data-url]")
            if nodo is None:
                continue
            try:
                datos = json.loads(nodo["data-ga4-offerdata"])
            except (ValueError, KeyError):
                continue
            if datos.get("section", "SEARCH") != "SEARCH" or not datos.get("id"):
                continue
            ruta = nodo["data-url"]
            salario = (datos.get("salary") or "").strip()
            modalidad = _dato_rotulado(item, "modalidad laboral")
            descripcion = " ".join(
                _texto(li) for li in item.select("li.result-info-hover-li-description")
            )[:MAX_DESCRIPCION]
            vacantes.append(
                Vacante(
                    fuente=self.nombre,
                    id_fuente=str(datos["id"]),
                    titulo=(datos.get("title") or "").strip(),
                    empresa=(datos.get("company") or "").strip(),
                    url=ruta if ruta.startswith("http") else f"{URL_BASE}{ruta}",
                    keyword=keyword,
                    ubicacion=(datos.get("location") or "").strip() or None,
                    modalidad=MODALIDADES.get(normalizar_texto(modalidad), modalidad or None),
                    salario=None if normalizar_texto(salario) in SALARIOS_VACIOS else salario,
                    publicada=interpretar_fecha(_texto(item.select_one(".js-offer-date")), ahora),
                    descripcion=descripcion or None,
                )
            )
        if not vacantes:
            raise CambioHTML("Los result-item no traen data-ga4-offerdata válido")
        return vacantes
