"""Servicio Público de Empleo (buscadordeempleo.gov.co): API JSON de plazas de práctica.

El SPE agrega vacantes de otros portales y de bolsas universitarias. Las copias de elempleo y
Magneto llevan el mismo id del portal de origen, así que se identifican con su clave de origen
(``elempleo:<id>`` / ``magneto:<id>``) para que la deduplicación las reconozca.
"""

from __future__ import annotations

import re
import ssl
from datetime import datetime
from urllib.parse import urlsplit, urlunsplit

import certifi
import httpx

from buscador_vacantes.config import RAIZ
from buscador_vacantes.fechas import ZONA
from buscador_vacantes.fuentes.base import CambioHTML, Fuente, Peticion
from buscador_vacantes.modelo import Vacante

URL_BUSQUEDA = "https://www.buscadordeempleo.gov.co/backbue/v1/vacantes/resultados"
# El servidor no envía su certificado intermedio; se completa la cadena con el de DigiCert
CERTIFICADO_INTERMEDIO = RAIZ / "assets" / "certs" / "geotrust-tls-rsa-ca-g1.pem"
MAX_DESCRIPCION = 600
TODO_EL_TERRITORIO = "vacantes para todo el territorio"
SALARIOS_VACIOS = {"a convenir", ""}
# Portales que el buscador ya consulta: dominio → nombre de la fuente
ORIGENES = {"www.elempleo.com": "elempleo", "www.magneto365.com": "magneto"}
# Bolsas que exigen iniciar sesión para ver la oferta (configurable en opciones)
DOMINIOS_CON_LOGIN = ("symplicity.com", "coallytalent.com")
_PALABRAS_MENORES = {"de", "del", "la", "las", "los", "y", "el"}
_PREFIJO = re.compile(r"^\s*PL\s*-\s*", re.IGNORECASE)
_RUTA_LOGIN = re.compile(r"login|auth/|signin", re.IGNORECASE)


def _capitalizar(texto: str) -> str:
    palabras = texto.strip().lower().split()
    return " ".join(
        p if i and p in _PALABRAS_MENORES else p[:1].upper() + p[1:] for i, p in enumerate(palabras)
    ).replace("D.c.", "D.C.")  # "BOGOTÁ, D.C." → "Bogotá, D.C."


def _ubicacion(municipio: str | None, departamento: str | None) -> str | None:
    municipio = (municipio or "").strip()
    departamento = (departamento or "").strip()
    if municipio.lower() == TODO_EL_TERRITORIO:
        return "Colombia"
    if municipio.lower().startswith("departamento"):
        municipio = ""
    partes = [municipio] if municipio == departamento else [municipio, departamento]
    lugar = ", ".join(_capitalizar(p) for p in partes if p)
    return lugar or None


def _fecha(texto: str | None) -> datetime | None:
    """Las fechas vienen como medianoche UTC del día publicado: se toma ese día en Colombia."""
    if not texto:
        return None
    try:
        dia = datetime.fromisoformat(texto[:10])
    except ValueError:
        return None
    return dia.replace(hour=12, tzinfo=ZONA)


def _sin_consulta(url: str) -> str:
    """Quita los parámetros de seguimiento (utm_*) del enlace de origen."""
    partes = urlsplit(url)
    return urlunsplit((partes.scheme, partes.netloc, partes.path, "", ""))


def exige_login(url: str, dominios_con_login: tuple[str, ...] | list[str]) -> bool:
    partes = urlsplit(url)
    dominio = partes.netloc.lower().split(":")[0]
    if any(dominio == d or dominio.endswith(f".{d}") for d in dominios_con_login):
        return True
    return bool(_RUTA_LOGIN.search(partes.path))


def _origen(
    prestadores: list[dict], dominios_con_login: tuple[str, ...] | list[str]
) -> tuple[str, str, str] | None:
    """(fuente, url, prestador): prefiere un portal ya consultado; si no, el primer enlace
    público. Los enlaces que exigen iniciar sesión no sirven al lector del canal."""
    candidatos = [
        ((p.get("URL_DETALLE_VACANTE") or "").strip(), (p.get("NOMBRE_PRESTADOR") or "").strip())
        for p in prestadores
    ]
    candidatos = [
        (url, nombre)
        for url, nombre in candidatos
        if url.startswith("http") and not exige_login(url, dominios_con_login)
    ]
    for url, nombre in candidatos:
        fuente = ORIGENES.get(urlsplit(url).netloc.lower())
        if fuente:
            return fuente, _sin_consulta(url), nombre
    if candidatos:
        url, nombre = candidatos[0]
        return "spe", url, nombre
    return None


class ServicioPublicoEmpleo(Fuente):
    nombre = "spe"
    # No usa la rotación de palabras clave: pide las plazas de práctica más recientes
    consulta_fija = "plazas de práctica"
    soporta_paginas = True
    tamano_pagina = 50
    selectores = [
        "resultados[]: CODIGO_VACANTE, TITULO_VACANTE ('PL-'), DESCRIPCION_VACANTE",
        "MUNICIPIO, DEPARTAMENTO, FECHA_PUBLICACION, FECHA_VENCIMIENTO",
        "RANGO_SALARIAL, TELETRABAJO, DETALLES_PRESTADOR[]: NOMBRE_PRESTADOR, URL_DETALLE_VACANTE",
    ]

    _filas_ultima_pagina = 0

    def pagina_completa(self, vacantes: list[Vacante]) -> bool:
        # Se cuentan las filas recibidas: parsear descarta vencidas y plazas sin enlace
        return self._filas_ultima_pagina >= self.tamano_pagina

    def verificacion_tls(self) -> ssl.SSLContext:
        contexto = ssl.create_default_context(cafile=certifi.where())
        contexto.load_verify_locations(cafile=str(CERTIFICADO_INTERMEDIO))
        return contexto

    def construir_peticion(self, keyword: str, pagina: int = 1) -> Peticion:
        return Peticion(
            URL_BUSQUEDA,
            params={"page": pagina, "PLAZA_PRACTICA": 1},
            cabeceras={"Accept": "application/json"},
        )

    def parsear(self, respuesta: httpx.Response, keyword: str, ahora: datetime) -> list[Vacante]:
        try:
            datos = respuesta.json()
        except ValueError as exc:
            raise CambioHTML("La respuesta no es JSON") from exc
        if not isinstance(datos, dict) or not isinstance(datos.get("resultados"), list):
            raise CambioHTML("La respuesta no tiene la lista 'resultados'")
        self._filas_ultima_pagina = len(datos["resultados"])
        dominios_con_login = self.opciones.get("dominios_con_login", DOMINIOS_CON_LOGIN)
        hoy = ahora.astimezone(ZONA).date()
        vacantes = []
        for fila in datos["resultados"]:
            codigo = str(fila.get("CODIGO_VACANTE") or "").strip()
            titulo = _PREFIJO.sub("", fila.get("TITULO_VACANTE") or "").strip()
            origen = _origen(fila.get("DETALLES_PRESTADOR") or [], dominios_con_login)
            if not codigo or not titulo or origen is None:
                continue
            vence = _fecha(fila.get("FECHA_VENCIMIENTO"))
            if vence is not None and vence.date() < hoy:
                continue
            fuente, url, prestador = origen
            salario = (fila.get("RANGO_SALARIAL") or "").strip()
            descripcion = " ".join((fila.get("DESCRIPCION_VACANTE") or "").split())
            if prestador:
                descripcion = f"Publicada por {prestador}. {descripcion}"
            vacantes.append(
                Vacante(
                    fuente=fuente,
                    id_fuente=codigo,
                    titulo=titulo,
                    empresa="",  # el SPE solo expone el prestador intermediario
                    url=url,
                    keyword=keyword,
                    ubicacion=_ubicacion(fila.get("MUNICIPIO"), fila.get("DEPARTAMENTO")),
                    modalidad="Remoto" if fila.get("TELETRABAJO") == 1 else None,
                    salario=None if salario.lower() in SALARIOS_VACIOS else salario,
                    publicada=_fecha(fila.get("FECHA_PUBLICACION")),
                    descripcion=descripcion[:MAX_DESCRIPCION] or None,
                )
            )
        return vacantes
