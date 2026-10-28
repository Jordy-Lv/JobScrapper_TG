"""Lectores de esquema de los ATS: el formulario de una postulación leído antes de abrir la página.

Cada familia publica su formulario por una fuente pública (la API de tableros de Greenhouse, la
consulta GraphQL de la página de Ashby, la definición embebida de Typeform y el HTML de Lever). Las
funciones `traducir_*` son puras (JSON o HTML → `list[Pregunta]`, con `nombre` igual a la clave que
la extensión verá en la página); `LectorEsquemas` las une con `httpx` y la pausa mínima por dominio.
Nada se envía y no hay sesión: si la lectura falla, la postulación sigue como un formulario
desconocido.
"""

from __future__ import annotations

import html
import json
import logging
import re
from dataclasses import fields
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
from bs4 import BeautifulSoup, Tag

from buscador_vacantes.asistente.detalle import Ritmo
from buscador_vacantes.asistente.respuestas import Pregunta

log = logging.getLogger(__name__)

FAMILIAS_CON_LECTOR = ("greenhouse", "ashby", "lever", "typeform")
# Campos de `Pregunta` que entiende el modelo `Campo` de la API (el esquema que se guarda)
_CAMPOS_GUARDADOS = {f.name for f in fields(Pregunta)} - {"campo_receta"}
_MAX_TEXTO, _MAX_AYUDA, _MAX_NOMBRE, _MAX_OPCIONES = 1000, 500, 200, 100

_ETIQUETAS = re.compile(r"<[^>]+>")
_UUID = r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}"

URL_GREENHOUSE_API = "https://boards-api.greenhouse.io/v1/boards/{tablero}/jobs/{id}"
URL_ASHBY = "https://jobs.ashbyhq.com/api/non-user-graphql?op=ApiJobPosting"
CONSULTA_ASHBY = (
    "query ApiJobPosting($organizationHostedJobsPageName: String!, $jobPostingId: String!) {"
    " jobPosting(organizationHostedJobsPageName: $organizationHostedJobsPageName,"
    " jobPostingId: $jobPostingId) { id title applicationForm { id sections { title fieldEntries {"
    " id isRequired descriptionHtml field } } } } }"
)  # `field` es un JSON sin subcampos: trae `path`, `title`, `type` y `selectableValues`


def familia_con_lector(familia: str) -> bool:
    return familia in FAMILIAS_CON_LECTOR


# --- construcción de preguntas ----------------------------------------------------------------


def _texto_plano(valor: Any) -> str | None:
    """El texto de un fragmento HTML sin etiquetas, o None si queda vacío."""
    if not isinstance(valor, str):
        return None
    limpio = " ".join(html.unescape(_ETIQUETAS.sub(" ", valor)).split())
    return limpio or None


def _pregunta(
    texto: Any,
    tipo: str,
    *,
    nombre: Any = None,
    opciones: list[Any] | None = None,
    obligatoria: bool = True,
    ayuda: Any = None,
) -> Pregunta | None:
    texto = _texto_plano(texto)
    if not texto:
        return None
    etiquetas = [t for o in (opciones or []) if (t := _texto_plano(o))][:_MAX_OPCIONES]
    return Pregunta(
        texto=texto[:_MAX_TEXTO],
        tipo=tipo,
        opciones=etiquetas,
        obligatoria=bool(obligatoria),
        nombre=str(nombre)[:_MAX_NOMBRE] if nombre else None,
        ayuda=(_texto_plano(ayuda) or "")[:_MAX_AYUDA] or None,
    )


def a_campos(preguntas: list[Pregunta]) -> list[dict]:
    """Las preguntas como dicts del modelo `Campo`, para guardarlas como esquema de la vacante."""
    return [
        {k: v for k, v in vars(p).items() if k in _CAMPOS_GUARDADOS and v not in (None, [], "")}
        | {"texto": p.texto, "obligatoria": p.obligatoria}
        for p in preguntas
    ]


# --- Greenhouse -------------------------------------------------------------------------------

_TIPOS_GREENHOUSE = {
    "input_text": "texto",
    "textarea": "texto",
    "input_file": "archivo",
    "multi_value_single_select": "opciones",
    "multi_value_multi_select": "opciones",
}
_REDUNDANTES_GREENHOUSE = {"resume_text", "cover_letter_text"}  # el CV va por el archivo


def traducir_greenhouse(datos: dict) -> list[Pregunta]:
    """Preguntas de la API de tableros (`?questions=true`): `questions` y `location_questions`.
    Las demográficas y de cumplimiento (EEOC) son voluntarias y no se responden."""
    preguntas = []
    grupos = (datos.get("questions") or []) + (datos.get("location_questions") or [])
    for pregunta in grupos:
        for campo in pregunta.get("fields") or []:
            nombre, tipo_api = campo.get("name"), campo.get("type")
            if tipo_api not in _TIPOS_GREENHOUSE or nombre in _REDUNDANTES_GREENHOUSE:
                continue  # input_hidden y tipos desconocidos
            tipo = _TIPOS_GREENHOUSE[tipo_api]
            if tipo == "texto" and nombre == "email":
                tipo = "correo"
            elif tipo == "texto" and nombre == "phone":
                tipo = "telefono"
            nueva = _pregunta(
                pregunta.get("label"),
                tipo,
                nombre=nombre,
                opciones=[v.get("label") for v in campo.get("values") or []],
                obligatoria=pregunta.get("required", False),
                ayuda=pregunta.get("description"),
            )
            if nueva:
                preguntas.append(nueva)
    return preguntas


# --- Ashby ------------------------------------------------------------------------------------

_TIPOS_ASHBY = {
    "String": "texto",
    "LongText": "texto",
    "Location": "texto",
    "Email": "correo",
    "Phone": "telefono",
    "File": "archivo",
    "Number": "numero",
    "Date": "fecha",
    "Boolean": "opciones",
    "ValueSelect": "opciones",
    "MultiValueSelect": "opciones",
}


def traducir_ashby(datos: dict) -> list[Pregunta]:
    """Preguntas de la consulta `ApiJobPosting`: `applicationForm.sections[].fieldEntries[]`,
    con la ruta (`path`) del campo como clave."""
    publicacion = ((datos or {}).get("data") or {}).get("jobPosting") or {}
    secciones = (publicacion.get("applicationForm") or {}).get("sections") or []
    preguntas = []
    for seccion in secciones:
        for entrada in seccion.get("fieldEntries") or []:
            campo = {**entrada, **(entrada.get("field") or {})}
            tipo = _TIPOS_ASHBY.get(campo.get("type"), "texto")
            opciones = [v.get("label") for v in campo.get("selectableValues") or []]
            if campo.get("type") == "Boolean":
                opciones = ["Yes", "No"]
            nueva = _pregunta(
                campo.get("title"),
                tipo,
                nombre=campo.get("path"),
                opciones=opciones,
                obligatoria=entrada.get("isRequired", False),
                ayuda=entrada.get("descriptionHtml") or entrada.get("descriptionPlain"),
            )
            if nueva:
                preguntas.append(nueva)
    return preguntas


# --- Typeform ---------------------------------------------------------------------------------

_TIPOS_TYPEFORM = {
    "short_text": "texto",
    "long_text": "texto",
    "website": "texto",
    "email": "correo",
    "phone_number": "telefono",
    "number": "numero",
    "opinion_scale": "numero",
    "rating": "numero",
    "date": "fecha",
    "file_upload": "archivo",
    "multiple_choice": "opciones",
    "picture_choice": "opciones",
    "dropdown": "opciones",
    "yes_no": "opciones",
    "legal": "opciones",
}


def _definicion_typeform(pagina: str) -> dict | None:
    """El `form` de `window.rendererData`, o None si la página no lo trae o está roto."""
    marca = re.search(r"window\.rendererData\s*=\s*", pagina)
    if not marca:
        return None
    try:
        datos, _ = json.JSONDecoder().raw_decode(pagina, marca.end())
    except ValueError:
        return None
    formulario = datos.get("form") if isinstance(datos, dict) else None
    return formulario if isinstance(formulario, dict) else None


def _campos_typeform(campos: list[dict]) -> list[dict]:
    """Los campos en orden, con los de un grupo desplegados en su lugar."""
    planos = []
    for campo in campos:
        if campo.get("type") == "group":
            planos.extend(_campos_typeform((campo.get("properties") or {}).get("fields") or []))
        else:
            planos.append(campo)
    return planos


def traducir_typeform(pagina: str) -> list[Pregunta]:
    """Preguntas de la definición que trae la página. Se ignoran los enunciados y las pantallas de
    bienvenida y de gracias. Si el formulario tiene saltos (`logic`) solo se resuelven las
    preguntas: el bucle sigue el orden real de las pantallas."""
    formulario = _definicion_typeform(pagina)
    if not formulario:
        return []
    sino = ["Yes", "No"] if str(formulario.get("language", "")).startswith("en") else ["Sí", "No"]
    preguntas = []
    for campo in _campos_typeform(formulario.get("fields") or []):
        tipo = _TIPOS_TYPEFORM.get(campo.get("type"))
        if tipo is None:  # statement y tipos sin respuesta
            continue
        propiedades = campo.get("properties") or {}
        if campo.get("type") in ("yes_no", "legal"):
            opciones = sino
        else:
            opciones = [c.get("label") for c in propiedades.get("choices") or []]
        nueva = _pregunta(
            campo.get("title"),
            tipo,
            nombre=campo.get("id"),
            opciones=opciones,
            obligatoria=(campo.get("validations") or {}).get("required", False),
            ayuda=propiedades.get("description"),
        )
        if nueva:
            preguntas.append(nueva)
    return preguntas


# --- Lever ------------------------------------------------------------------------------------

# Voluntarias o internas del formulario de Lever: no se responden
_IGNORADOS_LEVER = ("surveysResponses[", "pronouns", "accountId", "selectedLocation")


def _etiqueta_lever(pregunta: Tag) -> tuple[str | None, bool]:
    """El texto de la pregunta sin la marca de obligatorio, y si la trae."""
    etiqueta = pregunta.select_one(".application-label")
    if etiqueta is None:
        return None, False
    obligatoria = etiqueta.select_one(".required") is not None
    for marca in etiqueta.select(".required"):
        marca.decompose()
    return _texto_plano(etiqueta.get_text(" ")), obligatoria


def traducir_lever(pagina: str) -> list[Pregunta]:
    """Preguntas de `form#application-form` de la página `/apply` de Lever: una por cada
    `li.application-question`, con el `name` de su campo como clave."""
    sopa = BeautifulSoup(pagina or "", "lxml")
    formulario = sopa.find("form", id="application-form")
    if formulario is None:
        return []
    preguntas = []
    for item in formulario.select("li.application-question"):
        if item.select_one("li.application-question"):
            continue  # un contenedor de otras preguntas, no una pregunta
        controles = [
            c for c in item.select("input, textarea, select")
            if c.get("type") != "hidden" and c.get("name")
        ]  # fmt: skip
        if not controles or controles[0]["name"].startswith(_IGNORADOS_LEVER):
            continue
        texto, marcada = _etiqueta_lever(item)
        primero = controles[0]
        nombre = primero["name"]
        obligatoria = marcada or primero.has_attr("required")
        opciones: list[str] = []
        if primero.get("type") == "file":
            tipo = "archivo"
        elif primero.get("type") in ("radio", "checkbox"):
            tipo = "opciones"
            opciones = [a.get_text(" ") for a in item.select(".application-answer-alternative")]
        elif primero.name == "select":
            tipo = "opciones"
            opciones = [o.get_text(" ") for o in primero.find_all("option") if o.get("value")]
        elif primero.name == "textarea":
            tipo = "texto"
        elif primero.get("type") == "email":
            tipo = "correo"
        elif primero.get("type") == "tel" or nombre == "phone":
            tipo = "telefono"
        elif primero.get("type") == "number":
            tipo = "numero"
        else:
            tipo = "texto"
        nueva = _pregunta(texto, tipo, nombre=nombre, opciones=opciones, obligatoria=obligatoria)
        if nueva:
            preguntas.append(nueva)
    return preguntas


# --- cliente ----------------------------------------------------------------------------------


def _greenhouse(url: str) -> str | None:
    partes = urlparse(url)
    if not (partes.hostname or "").endswith("greenhouse.io"):
        return None
    if partes.path.rstrip("/") == "/embed/job_app":  # el tablero incrustado en el sitio propio
        consulta = parse_qs(partes.query)
        tablero, id_ = (consulta.get("for") or [""])[0], (consulta.get("token") or [""])[0]
    else:
        encaja = re.fullmatch(r"/([\w-]+)/jobs/(\d+)/?", partes.path)
        tablero, id_ = encaja.groups() if encaja else ("", "")
    if not (re.fullmatch(r"[\w-]+", tablero) and id_.isdigit()):
        return None
    return URL_GREENHOUSE_API.format(tablero=tablero, id=id_)


def _ashby(url: str) -> dict | None:
    partes = urlparse(url)
    if (partes.hostname or "") != "jobs.ashbyhq.com":
        return None
    encaja = re.fullmatch(rf"/([\w.-]+)/({_UUID})(?:/application)?/?", partes.path)
    if not encaja:
        return None
    return {
        "operationName": "ApiJobPosting",
        "variables": {
            "organizationHostedJobsPageName": encaja.group(1),
            "jobPostingId": encaja.group(2),
        },
        "query": CONSULTA_ASHBY,
    }


def _lever(url: str) -> str | None:
    partes = urlparse(url)
    if (partes.hostname or "") != "jobs.lever.co":
        return None
    encaja = re.fullmatch(rf"/([\w.-]+)/({_UUID})(?:/apply)?/?", partes.path)
    return f"https://jobs.lever.co/{encaja.group(1)}/{encaja.group(2)}/apply" if encaja else None


def _typeform(url: str) -> str | None:
    partes = urlparse(url)
    host = partes.hostname or ""
    if not host.endswith(".typeform.com") or partes.scheme != "https":
        return None
    encaja = re.fullmatch(r"/to/([\w-]+)/?", partes.path)
    return f"https://{host}/to/{encaja.group(1)}" if encaja else None


class LectorEsquemas:
    """Lee el formulario de un destino de ATS sin sesión y sin enviar nada. `leer` devuelve None
    si la familia no tiene lector, la URL no es de una vacante o la lectura falla."""

    def __init__(self, cliente: httpx.AsyncClient, ritmo: Ritmo) -> None:
        self.cliente = cliente
        self.ritmo = ritmo

    async def _pedir(self, metodo: str, url: str, **args: Any) -> httpx.Response | None:
        await self.ritmo.esperar_turno(urlparse(url).hostname or "")
        try:
            respuesta = await self.cliente.request(metodo, url, **args)
        except httpx.HTTPError as exc:
            log.info("Esquema de %s no disponible: %s", urlparse(url).hostname, type(exc).__name__)
            return None
        if respuesta.status_code != 200:
            log.info("Esquema de %s: HTTP %s", urlparse(url).hostname, respuesta.status_code)
            return None
        return respuesta

    async def leer(self, familia: str, url: str) -> list[Pregunta] | None:
        try:
            preguntas = await self._leer(familia, url or "")
        except (ValueError, TypeError, AttributeError) as exc:  # JSON roto o forma inesperada
            log.info("Esquema de %s ilegible: %s", familia, type(exc).__name__)
            return None
        return preguntas or None

    async def _leer(self, familia: str, url: str) -> list[Pregunta]:
        if familia == "greenhouse" and (api := _greenhouse(url)):
            respuesta = await self._pedir("GET", api, params={"questions": "true"})
            return traducir_greenhouse(respuesta.json()) if respuesta else []
        if familia == "ashby" and (cuerpo := _ashby(url)):
            respuesta = await self._pedir("POST", URL_ASHBY, json=cuerpo)
            return traducir_ashby(respuesta.json()) if respuesta else []
        if familia == "lever" and (pagina := _lever(url)):
            respuesta = await self._pedir("GET", pagina)
            return traducir_lever(respuesta.text) if respuesta else []
        if familia == "typeform" and (pagina := _typeform(url)):
            respuesta = await self._pedir("GET", pagina)
            return traducir_typeform(respuesta.text) if respuesta else []
        return []
