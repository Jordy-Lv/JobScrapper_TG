"""Magneto365: API pública de búsqueda de la web (JSON)."""

from __future__ import annotations

import json
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

from fechas import interpretar_fecha
from fuentes.base import CambioHTML, Fuente, Peticion
from modelo import Vacante

URL_BUSQUEDA = "https://api.magneto365.com/jobs/v1/public/jobs/search"
URL_OFERTA = "https://www.magneto365.com/co/empleos/{slug}"
MAX_DESCRIPCION = 600
MAX_CIUDADES = 3


def _texto_plano(html: str | None) -> str:
    if not html:
        return ""
    return " ".join(BeautifulSoup(html, "lxml").get_text(" ").split())


def _miles(valor: int | float) -> str:
    return f"{int(valor):,}".replace(",", ".")


def _salario(fila: dict) -> str | None:
    if fila.get("toAgree"):
        return None
    unidad = fila.get("currencyUnit") or "$"
    minimo = fila.get("minSalary") or fila.get("salary") or 0
    maximo = fila.get("maxSalary") or 0
    if minimo and maximo and maximo > minimo:
        return f"{unidad}{_miles(minimo)} - {unidad}{_miles(maximo)}"
    if minimo:
        return f"{unidad}{_miles(minimo)}"
    return None


def _ubicacion(ciudades: list[str]) -> str | None:
    ciudades = [c for c in ciudades if c]
    if not ciudades:
        return None
    texto = ", ".join(ciudades[:MAX_CIUDADES])
    if len(ciudades) > MAX_CIUDADES:
        texto += f" y {len(ciudades) - MAX_CIUDADES} más"
    return texto


class Magneto(Fuente):
    nombre = "magneto"
    selectores = [
        "rows[].id",
        "rows[].title",
        "rows[].jobSlug",
        "rows[].companyName",
        "rows[].cities",
        "rows[].publishDate",
    ]

    def construir_peticion(self, keyword: str) -> Peticion:
        return Peticion(
            URL_BUSQUEDA,
            params={
                "device": "desktop",
                "paginator": json.dumps({"page": 1, "pageSize": 20}),
                "order": json.dumps({"field": "publish_date", "order": "DESC"}),
                "queries": json.dumps([{"field": "all", "term": keyword}]),
            },
            cabeceras={"Accept": "application/json"},
        )

    def parsear(self, respuesta: httpx.Response, keyword: str, ahora: datetime) -> list[Vacante]:
        try:
            datos = respuesta.json()
        except ValueError as exc:
            raise CambioHTML("La respuesta no es JSON") from exc
        if not isinstance(datos, dict) or not isinstance(datos.get("rows"), list):
            raise CambioHTML("La respuesta no tiene la lista 'rows'")
        vacantes = []
        for fila in datos["rows"]:
            if not fila.get("id") or not fila.get("title") or not fila.get("jobSlug"):
                continue
            descripcion = _texto_plano(fila.get("description"))
            meses = fila.get("experienceMonthsNumber") or 0
            if meses >= 12:
                # Así la regla de años de experiencia también aplica a Magneto
                descripcion = f"Experiencia requerida: {meses // 12} años. {descripcion}"
            vacantes.append(
                Vacante(
                    fuente=self.nombre,
                    id_fuente=str(fila["id"]),
                    titulo=fila["title"].strip(),
                    empresa=(fila.get("companyName") or "").strip(),
                    url=URL_OFERTA.format(slug=fila["jobSlug"]),
                    keyword=keyword,
                    ubicacion=_ubicacion(fila.get("cities") or []),
                    modalidad="Remoto o híbrido" if fila.get("isRemote") else None,
                    salario=_salario(fila),
                    publicada=interpretar_fecha(fila.get("publishDate"), ahora),
                    descripcion=descripcion[:MAX_DESCRIPCION] or None,
                )
            )
        return vacantes
