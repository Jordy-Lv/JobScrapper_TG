"""LinkedIn: API pública para invitados (HTML de tarjetas, sin sesión)."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

from buscador_vacantes.config import ConsultaOpciones
from buscador_vacantes.detalle import extraer_descripcion
from buscador_vacantes.estado import a_texto, de_texto
from buscador_vacantes.fechas import interpretar_fecha
from buscador_vacantes.fuentes.base import (
    CambioHTML,
    Fuente,
    Intento,
    Peticion,
    ResultadoFuente,
)
from buscador_vacantes.modelo import Vacante

URL_BUSQUEDA = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
URL_DETALLE = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{id}"
URL_OFERTA = "https://co.linkedin.com/jobs/view/{id}"
TAMANO_PAGINA = 10  # tarjetas por página de la API pública
VENTANA_MAX_S = 86_400  # tope de la ventana de publicación: 24 h
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

    soporta_paginas = True
    tamano_pagina = TAMANO_PAGINA
    soporta_detalle = True

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.consulta = self.config.consulta or ConsultaOpciones()
        # Por consulta y corrida: la ventana pedida y la hora de su primera petición
        self._ventanas: dict[str, int] = {}

    def _clave_sondeo(self, keyword: str) -> str:
        huella = hashlib.sha1(keyword.encode()).hexdigest()[:10]
        return f"sondeo:{self.nombre}:{self.variante_id}:{huella}"

    def _ventana_s(self, keyword: str) -> int:
        """Antigüedad máxima que se pide (f_TPR), fijada una vez por consulta y corrida.

        Es el tiempo desde el último sondeo exitoso más el margen, entre ``ventana_min_h`` y 24 h;
        sin sondeo previo, 24 h. Así tras un cooldown o un apagado la ventana cubre el hueco.
        """
        if keyword not in self._ventanas:
            consulta = self.consulta
            sondeo = de_texto(self.estado.kv_obtener(self._clave_sondeo(keyword)))
            if sondeo is None:
                segundos = VENTANA_MAX_S
            else:
                segundos = (self.reloj() - sondeo).total_seconds() + consulta.margen_min * 60
            minimo = consulta.ventana_min_h * 3600
            self._ventanas[keyword] = round(min(max(segundos, minimo), VENTANA_MAX_S))
        return self._ventanas[keyword]

    def construir_peticion(self, keyword: str, pagina: int = 1) -> Peticion:
        params = {
            "keywords": keyword,
            "location": self.opciones.get("location", "Colombia"),
            "f_E": self.opciones.get("f_E", "1,2"),
            "f_TPR": f"r{self._ventana_s(keyword)}",
            "start": (pagina - 1) * TAMANO_PAGINA,
        }
        if self.consulta.orden:
            params["sortBy"] = self.consulta.orden
        # La variante cambia parámetros de la búsqueda (p. ej. location)
        params.update(self.variante or {})
        return Peticion(URL_BUSQUEDA, params=params)

    def peticion_detalle(self, vacante: Vacante) -> Peticion:
        """Endpoint de invitados del detalle: responde con el HTML de la descripción (40-60 KB)."""
        return Peticion(URL_DETALLE.format(id=vacante.id_fuente))

    def extraer_detalle(self, respuesta: httpx.Response) -> str | None:
        return extraer_descripcion(respuesta.text)

    def al_terminar(self, resultado: ResultadoFuente) -> None:
        """Registra el sondeo de cada consulta cuyas páginas pedidas respondieron todas bien.

        Se guarda la hora de inicio de su primera petición. Si una página falla (p. ej. un 429 en
        la segunda), se conserva el sondeo anterior y la ventana siguiente cubre ese hueco.
        """
        if not self.persistir_estado:
            return
        por_consulta: dict[str, list[Intento]] = {}
        for intento in resultado.intentos:
            por_consulta.setdefault(intento.keyword, []).append(intento)
        for keyword, intentos in por_consulta.items():
            if all(i.tipo_error is None and i.status is not None for i in intentos):
                inicio = min(i.ts for i in intentos)
                self.estado.kv_guardar(self._clave_sondeo(keyword), a_texto(inicio))

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
