"""Computrabajo Colombia: listado HTML de ofertas."""

from __future__ import annotations

import re
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

from buscador_vacantes.fechas import interpretar_fecha
from buscador_vacantes.fuentes.base import CambioHTML, Fuente, Peticion
from buscador_vacantes.modelo import Vacante
from buscador_vacantes.normalizar import normalizar_texto

URL_BASE = "https://co.computrabajo.com"
_ID = re.compile(r"^[A-F0-9]{32}$", re.IGNORECASE)
_SIN_RESULTADOS = "no hay ofertas para el empleo que buscas"
MODALIDADES = {
    "remoto": "Remoto",
    "presencial y remoto": "Híbrido",
    "hibrido": "Híbrido",
    "presencial": "Presencial",
}


def _texto(nodo) -> str:
    return " ".join(nodo.get_text(" ").split()) if nodo else ""


def slug(keyword: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", normalizar_texto(keyword)).strip("-")


class Computrabajo(Fuente):
    nombre = "computrabajo"
    # La página 1 viene ordenada por relevancia, no por fecha: las ofertas recientes
    # también aparecen en las páginas siguientes (``p=N``)
    soporta_paginas = True
    tamano_pagina = 20
    selectores = [
        "article.box_offer[data-id]",
        "h2 a.js-o-link",
        "a[offer-grid-article-company-url]",
        "p.fs16:not(.dFlex) > span.mr10",
        "div.fs13 span.dIB (salario con .i_salary, modalidad)",
        "p.fc_aux (fecha relativa)",
    ]

    def construir_peticion(self, keyword: str, pagina: int = 1) -> Peticion:
        params: dict[str, int] = {"pubdate": self.opciones.get("pubdate", 3)}
        if pagina > 1:
            params["p"] = pagina
        return Peticion(f"{URL_BASE}/trabajo-de-{slug(keyword)}", params=params)

    def parsear(self, respuesta: httpx.Response, keyword: str, ahora: datetime) -> list[Vacante]:
        sopa = BeautifulSoup(respuesta.text, "lxml")
        articulos = sopa.select("article.box_offer[data-id]")
        if not articulos:
            if _SIN_RESULTADOS in normalizar_texto(sopa.get_text(" ")):
                return []
            raise CambioHTML("No se encontraron article.box_offer ni el aviso de sin resultados")
        vacantes = []
        for articulo in articulos:
            id_fuente = articulo.get("data-id", "").upper()
            enlace = articulo.select_one("h2 a.js-o-link") or articulo.select_one("h2 a")
            if not _ID.match(id_fuente) or enlace is None:
                continue
            ruta = enlace.get("href", "").split("#")[0]
            empresa = articulo.select_one("a[offer-grid-article-company-url]")
            if empresa is None:
                # Empresas sin perfil: el nombre va como texto en el párrafo de la empresa,
                # junto a la calificación (span.fx_none), que se descarta
                parrafo = articulo.select_one("p.dFlex")
                if parrafo is not None:
                    for calificacion in parrafo.select("span.fx_none"):
                        calificacion.decompose()
                empresa_texto = _texto(parrafo)
            else:
                empresa_texto = _texto(empresa)
            salario = modalidad = None
            for dato in articulo.select("div.fs13 span.dIB"):
                texto = _texto(dato)
                if dato.select_one(".i_salary"):
                    salario = re.sub(r",00\b", "", texto)
                elif texto:
                    modalidad = MODALIDADES.get(normalizar_texto(texto), texto)
            vacantes.append(
                Vacante(
                    fuente=self.nombre,
                    id_fuente=id_fuente,
                    titulo=_texto(enlace),
                    empresa=empresa_texto,
                    url=ruta if ruta.startswith("http") else f"{URL_BASE}{ruta}",
                    keyword=keyword,
                    ubicacion=_texto(articulo.select_one("p.fs16:not(.dFlex) > span.mr10")) or None,
                    modalidad=modalidad,
                    salario=salario,
                    publicada=interpretar_fecha(_texto(articulo.select_one("p.fc_aux")), ahora),
                )
            )
        return vacantes
