"""GetOnBoard: API pública de búsqueda (JSON)."""

from __future__ import annotations

import json
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

from buscador_vacantes.fechas import desde_epoch
from buscador_vacantes.fuentes.base import CambioHTML, Fuente, Peticion
from buscador_vacantes.modelo import Vacante

URL_BUSQUEDA = "https://www.getonbrd.com/api/v0/search/jobs"
MAX_DESCRIPCION = 600

MODALIDADES = {
    "fully_remote": "Remoto",
    "remote_local": "Remoto",
    "temporarily_remote": "Remoto",
    "hybrid": "Híbrido",
    "no_remote": "Presencial",
}
PAISES = {
    "AR": "Argentina", "BO": "Bolivia", "BR": "Brasil", "CL": "Chile", "CO": "Colombia",
    "CR": "Costa Rica", "EC": "Ecuador", "ES": "España", "GT": "Guatemala", "MX": "México",
    "PA": "Panamá", "PE": "Perú", "PY": "Paraguay", "US": "Estados Unidos", "UY": "Uruguay",
    "VE": "Venezuela",
}  # fmt: skip


def _texto_plano(html: str | None) -> str:
    if not html:
        return ""
    return " ".join(BeautifulSoup(html, "lxml").get_text(" ").split())


def _salario(minimo: int | None, maximo: int | None) -> str | None:
    def miles(valor: int) -> str:
        return f"{valor:,}".replace(",", ".")

    if minimo and maximo and minimo != maximo:
        return f"USD {miles(minimo)} - {miles(maximo)} mensual"
    if minimo or maximo:
        return f"USD {miles(minimo or maximo)} mensual"
    return None


def _ubicacion(atributos: dict, pais_empresa: str | None) -> str:
    modalidad = atributos.get("remote_modality")
    # La API localiza el marcador de remoto según Accept-Language ("Remote" o "Remoto")
    paises = [
        p for p in atributos.get("countries") or [] if p and p.lower() not in ("remote", "remoto")
    ]
    if modalidad == "fully_remote":
        zona = atributos.get("remote_zone")
        return f"Remoto ({zona})" if zona else "Remoto (cualquier país)"
    if modalidad in ("remote_local", "temporarily_remote"):
        if paises:
            return f"Remoto (solo residentes en {', '.join(paises)})"
        nombre = PAISES.get((pais_empresa or "").upper())
        if nombre == "Colombia":
            return "Remoto (Colombia)"
        if nombre:
            return f"Remoto (solo residentes en {nombre})"
        return "Remoto (solo residentes en el país de la empresa)"
    return ", ".join(paises)


class GetOnBoard(Fuente):
    nombre = "getonboard"
    selectores = ["data[].attributes.title", "data[].attributes.seniority", "links.public_url"]

    def construir_peticion(self, keyword: str, pagina: int = 1) -> Peticion:
        return Peticion(
            URL_BUSQUEDA,
            params={
                "query": keyword,
                "per_page": self.opciones.get("por_pagina", 50),
                "page": 1,
                "expand": json.dumps(["company", "seniority"]),
            },
        )

    def parsear(self, respuesta: httpx.Response, keyword: str, ahora: datetime) -> list[Vacante]:
        try:
            datos = respuesta.json()
        except ValueError as exc:
            raise CambioHTML("La respuesta no es JSON") from exc
        if not isinstance(datos, dict) or not isinstance(datos.get("data"), list):
            raise CambioHTML("La respuesta no tiene la lista 'data'")

        seniorities = set(self.opciones.get("seniorities", ["no_experience", "junior"]))
        excluir_ingles = self.opciones.get("excluir_remoto_en_ingles", True)
        vacantes = []
        for item in datos["data"]:
            atributos = item.get("attributes") or {}
            titulo = (atributos.get("title") or "").strip()
            url = (item.get("links") or {}).get("public_url")
            if not titulo or not url or not item.get("id"):
                continue
            seniority = (
                ((atributos.get("seniority") or {}).get("data") or {}).get("attributes") or {}
            ).get("locale_key")
            if seniority not in seniorities:
                continue
            if excluir_ingles and atributos.get("remote") and atributos.get("lang") == "en":
                continue
            empresa = ((atributos.get("company") or {}).get("data") or {}).get("attributes") or {}
            descripcion = _texto_plano(atributos.get("description"))[:MAX_DESCRIPCION]
            vacantes.append(
                Vacante(
                    fuente=self.nombre,
                    id_fuente=str(item["id"]),
                    titulo=titulo,
                    empresa=(empresa.get("name") or "").strip(),
                    url=url,
                    keyword=keyword,
                    ubicacion=_ubicacion(atributos, empresa.get("country")) or None,
                    modalidad=MODALIDADES.get(atributos.get("remote_modality") or ""),
                    salario=_salario(atributos.get("min_salary"), atributos.get("max_salary")),
                    publicada=desde_epoch(atributos.get("published_at")),
                    descripcion=descripcion or None,
                )
            )
        return vacantes
