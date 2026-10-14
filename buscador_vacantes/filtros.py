"""Veredicto aceptar/rechazar/dudosa y categoría de cada vacante, por reglas deterministas."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from buscador_vacantes import config as cfg
from buscador_vacantes.modelo import Categoria, Vacante, Veredicto
from buscador_vacantes.normalizar import (
    coincidencias,
    compilar_terminos,
    normalizar_empresa,
    normalizar_texto,
)

_EXPERIENCIA = r"(?:experiencia|experience)"
_ANIOS = r"(?:anos?|years?)"
# "2 a 3 años", "2-3 years": cuenta el mínimo del rango
_RANGO = re.compile(rf"(?<!\d)(\d{{1,2}})\s*(?:-|a|y|to)\s*(\d{{1,2}})\s*\+?\s*{_ANIOS}\b")
_ANIOS_SUELTOS = re.compile(rf"(?<!\d)(\d{{1,2}})\s*(?:\+|o mas|or more)?\s*{_ANIOS}\b")


class Motivo(StrEnum):
    LISTA_NEGRA = "lista_negra"
    SENIORITY = "seniority"
    ANTIGUEDAD = "antiguedad"
    UBICACION = "ubicacion"
    PRESENCIAL_FUERA = "presencial_fuera"
    CALL_CENTER = "call_center"
    NO_TI = "no_ti"
    ACEPTADA = "aceptada"
    DUDOSA = "dudosa"
    REMOTO_SIN_PAIS = "remoto_sin_pais"
    PENDIENTE_DETALLE = "pendiente_detalle"


# Condición de modalidad que la IA debe confirmar (Vacante.exige_modalidad)
REMOTO_O_HIBRIDO = "remoto_o_hibrido"
SOLO_REMOTO = "remoto"


@dataclass(frozen=True)
class Evaluacion:
    veredicto: Veredicto
    motivo: Motivo
    categoria: Categoria | None = None
    detalle: str = ""
    exige_modalidad: str | None = None


@dataclass(frozen=True)
class Correccion:
    """Cambio del guardarraíl a una vacante que llegó como «Prácticas y Aprendizaje»."""

    original: Categoria
    nueva: Categoria | None  # None: la vacante se rechaza
    detalle: str = ""

    @property
    def rechaza(self) -> bool:
        return self.nueva is None


class _Geo(StrEnum):
    OK = "ok"
    FUERA = "fuera"
    REMOTO_SIN_PAIS = "remoto_sin_pais"
    PRESENCIAL_FUERA = "presencial_fuera"
    CALL_CENTER = "call_center"
    CONFIRMAR_MODALIDAD = "confirmar_modalidad"
    PENDIENTE_DETALLE = "pendiente_detalle"


class _Origen(StrEnum):
    """De dónde salió la señal de modalidad."""

    PORTAL = "portal"
    TITULO = "titulo"
    DESCRIPCION = "descripcion"


class _Modalidad(StrEnum):
    REMOTO = "remoto"
    HIBRIDO = "híbrido"
    PRESENCIAL = "presencial"
    DESCONOCIDA = "desconocida"


class Filtros:
    def __init__(self, filtros: cfg.Filtros) -> None:
        self.config = filtros
        self._ignoradas = compilar_terminos(filtros.frases_ignoradas)
        self._seniority = compilar_terminos(filtros.exclusion_seniority)
        self._practica = compilar_terminos(filtros.nivel.practica)
        self._junior = compilar_terminos(filtros.nivel.junior)
        self._areas = [(a.categoria, compilar_terminos(a.terminos)) for a in filtros.areas]
        self._ti_generico = compilar_terminos(filtros.ti_generico)
        self._disparadores = compilar_terminos(filtros.disparadores_dudosa)
        self._no_ti = compilar_terminos(filtros.areas_no_ti)
        ubicacion = filtros.ubicacion
        self._colombia = compilar_terminos(ubicacion.colombia)
        self._solo_colombia = compilar_terminos(["colombia", "colombiano", "colombiana"])
        self._fuentes_colombianas = set(ubicacion.fuentes_colombianas)
        self._remoto = compilar_terminos(ubicacion.remoto)
        self._latam = compilar_terminos(ubicacion.latam)
        self._exterior = compilar_terminos(ubicacion.exterior)
        self._ciudad_base = compilar_terminos(ubicacion.ciudad_base)
        self._hibrido = compilar_terminos(ubicacion.hibrido)
        self._presencial = compilar_terminos(ubicacion.presencial)
        self._call_center = compilar_terminos(filtros.call_center)
        self._empresas_negras = [
            compilar_terminos([e])
            for e in dict.fromkeys(normalizar_empresa(e) for e in filtros.lista_negra.empresas)
            if e
        ]
        self._palabras_negras = compilar_terminos(filtros.lista_negra.palabras)
        self._evidencia_practica = compilar_terminos(filtros.nivel.evidencia_practica)
        self._evidencia_descripcion = compilar_terminos(
            filtros.nivel.evidencia_practica_descripcion
        )
        patrones = sorted(
            {normalizar_texto(p) for p in ubicacion.patrones_restriccion}, key=len, reverse=True
        )
        self._restriccion = (
            re.compile(
                r"(?:"
                + "|".join(re.escape(p).replace(r"\ ", r"\s+") for p in patrones)
                + r")\s+([a-z ]{3,40})"
            )
            if patrones
            else None
        )

    # --- utilidades -------------------------------------------------------------------------

    def _limpiar(self, texto: str | None) -> str:
        normalizado = normalizar_texto(texto)
        if self._ignoradas is not None:
            normalizado = self._ignoradas.sub(" ", normalizado)
        return re.sub(r"\s+", " ", normalizado).strip()

    def _anios_excesivos(self, titulo: str, descripcion: str) -> bool:
        limite = self.config.anios_experiencia_excluidos_desde

        def minimo(texto: str) -> int | None:
            valores = [int(m.group(1)) for m in _RANGO.finditer(texto)]
            sin_rangos = _RANGO.sub(" ", texto)
            valores += [int(m.group(1)) for m in _ANIOS_SUELTOS.finditer(sin_rangos)]
            return min(valores) if valores else None

        en_titulo = minimo(titulo)
        if en_titulo is not None and en_titulo >= limite:
            return True
        # En la descripción solo cuenta si habla de experiencia ("empresa con 10 años" no)
        for frase in re.split(r"[.;\n]", descripcion):
            if re.search(_EXPERIENCIA, frase):
                valor = minimo(frase)
                if valor is not None and valor >= limite:
                    return True
        return False

    def categoria_por_area(self, titulo: str, descripcion: str = "") -> Categoria | None:
        """Primera área (en el orden configurado) que coincide; primero en el título."""
        for texto in (titulo, descripcion):
            for categoria, patron in self._areas:
                if coincidencias(patron, texto):
                    return categoria
        return None

    def categoria_por_terminos(self, vacante: Vacante) -> Categoria:
        """Categoría para una vacante aceptada (también sirve de respaldo para la IA)."""
        titulo = self._limpiar(vacante.titulo)
        descripcion = self._limpiar(vacante.descripcion)
        if coincidencias(self._practica, titulo):
            return Categoria.PRACTICAS
        if not coincidencias(self._junior, titulo) and coincidencias(self._practica, descripcion):
            return Categoria.PRACTICAS
        return self.categoria_por_area(titulo, descripcion) or Categoria.OTROS_TI

    def ciudad_base_texto(self) -> str:
        """Ciudad base para mostrarla a la IA: la primera de la lista, con mayúscula inicial."""
        ciudades = self.config.ubicacion.ciudad_base
        return ciudades[0].title() if ciudades else ""

    # --- modalidad y geografía ----------------------------------------------------------------

    def _detectar_modalidad(self, texto: str, *, con_presencial: bool = True) -> _Modalidad | None:
        # Híbrido primero: "presencial y remoto" contiene a la vez "presencial" y "remoto"
        if coincidencias(self._hibrido, texto):
            return _Modalidad.HIBRIDO
        if coincidencias(self._remoto, texto):
            return _Modalidad.REMOTO
        if con_presencial and coincidencias(self._presencial, texto):
            return _Modalidad.PRESENCIAL
        return None

    def _modalidad(
        self, vacante: Vacante, titulo: str, descripcion: str
    ) -> tuple[_Modalidad, _Origen | None]:
        """Modalidad según el portal; si falta, el título y la ubicación; y si falta, la
        descripción, solo para remoto o híbrido (un anuncio híbrido puede decir «presencial»).

        Devuelve también de dónde salió la señal (``None`` si la modalidad es desconocida).
        """
        fuentes = (
            (self._limpiar(vacante.modalidad), True, _Origen.PORTAL),
            (f"{titulo} {self._limpiar(vacante.ubicacion)}", True, _Origen.TITULO),
            (descripcion, False, _Origen.DESCRIPCION),
        )
        for texto, con_presencial, origen in fuentes:
            modalidad = self._detectar_modalidad(texto, con_presencial=con_presencial)
            if modalidad is not None:
                return modalidad, origen
        return _Modalidad.DESCONOCIDA, None

    def _geografia(
        self, vacante: Vacante, titulo: str, descripcion: str, permite_detalle: bool = False
    ) -> tuple[_Geo, str, str | None]:
        """Alcance geográfico: (resultado, detalle, condición de modalidad que debe confirmar).

        ``permite_detalle``: la fuente puede pedir el detalle de la oferta. Sin descripción, no
        saber la modalidad no rechaza (queda pendiente de detalle) y, con ella, un remoto o
        híbrido que solo aparece en la descripción lo confirma la IA en lugar de aceptarse.
        """
        ubicacion = self._limpiar(vacante.ubicacion)
        lugar = self._limpiar(f"{vacante.ubicacion or ''} {vacante.modalidad or ''}")
        cercano = f"{lugar} {titulo}"
        completo = f"{cercano} {descripcion}"
        modalidad, origen = self._modalidad(vacante, titulo, descripcion)
        exterior = coincidencias(self._exterior, cercano)
        es_call_center = bool(coincidencias(self._call_center, titulo))
        solo_descripcion = permite_detalle and origen == _Origen.DESCRIPCION

        def aceptable(resultado: _Geo = _Geo.OK, detalle: str = "") -> tuple[_Geo, str, str | None]:
            """Un remoto o híbrido que solo vimos en el detalle lo confirma la IA."""
            if solo_descripcion:
                exige = SOLO_REMOTO if es_call_center else REMOTO_O_HIBRIDO
                return _Geo.CONFIRMAR_MODALIDAD, "modalidad solo en la descripción", exige
            return resultado, detalle, None

        # Call center: solo remoto, también en la ciudad base
        if es_call_center:
            if modalidad in (_Modalidad.PRESENCIAL, _Modalidad.HIBRIDO):
                return _Geo.CALL_CENTER, modalidad.value, None
            if modalidad == _Modalidad.DESCONOCIDA:
                if descripcion:
                    return _Geo.CONFIRMAR_MODALIDAD, "call center sin modalidad", SOLO_REMOTO
                if permite_detalle:
                    return _Geo.PENDIENTE_DETALLE, "call center sin modalidad", SOLO_REMOTO
                return _Geo.CALL_CENTER, "sin modalidad ni descripción", None
        elif coincidencias(self._ciudad_base, f"{ubicacion} {titulo}") and not exterior:
            return _Geo.OK, "", None

        en_colombia = bool(
            vacante.fuente in self._fuentes_colombianas
            or coincidencias(self._colombia, cercano)
            or coincidencias(self._solo_colombia, completo)
        )

        if modalidad == _Modalidad.REMOTO:
            if self._restriccion is not None:
                for restriccion in self._restriccion.finditer(completo):
                    destino = restriccion.group(1)
                    if coincidencias(self._colombia, destino) or coincidencias(
                        self._latam, destino
                    ):
                        return aceptable()
                    if coincidencias(self._exterior, destino):
                        return _Geo.FUERA, f"remoto restringido a {destino.strip()}", None
            if en_colombia or coincidencias(self._latam, completo):
                return aceptable()
            if exterior:
                return _Geo.FUERA, f"remoto en {exterior[0]}", None
            return aceptable(_Geo.REMOTO_SIN_PAIS, "remoto sin país")

        en_lugar_colombiano = bool(coincidencias(self._colombia, lugar))
        if modalidad == _Modalidad.HIBRIDO:
            if not en_lugar_colombiano and exterior:
                return _Geo.FUERA, f"híbrido en {exterior[0]}", None
            return aceptable()

        # Presencial o sin modalidad, fuera de la ciudad base
        if not en_lugar_colombiano and exterior:
            return _Geo.FUERA, f"presencial en {exterior[0]}", None
        if modalidad == _Modalidad.DESCONOCIDA and descripcion:
            return _Geo.CONFIRMAR_MODALIDAD, "modalidad sin confirmar", REMOTO_O_HIBRIDO
        if modalidad == _Modalidad.DESCONOCIDA and permite_detalle:
            return _Geo.PENDIENTE_DETALLE, "modalidad sin confirmar", REMOTO_O_HIBRIDO
        origen_texto = "presencial" if modalidad == _Modalidad.PRESENCIAL else "sin modalidad"
        lugar_texto = vacante.ubicacion or "ubicación desconocida"
        return _Geo.PRESENCIAL_FUERA, f"{origen_texto} en {lugar_texto}", None

    # --- lista negra --------------------------------------------------------------------------

    def _en_lista_negra(self, vacante: Vacante) -> str | None:
        empresa = normalizar_empresa(vacante.empresa)
        if empresa:
            for patron in self._empresas_negras:
                if coincidencias(patron, empresa):
                    return f"empresa {vacante.empresa}"
        palabra = coincidencias(self._palabras_negras, normalizar_texto(vacante.titulo))
        return f"palabra {palabra[0]}" if palabra else None

    # --- guardarraíl de prácticas -------------------------------------------------------------

    def guardarrail_practicas(self, vacante: Vacante) -> Correccion | None:
        """Corrige una vacante de «Prácticas y Aprendizaje» que no tiene evidencia de práctica.

        La evidencia es un término de práctica en el título o uno fuerte en la descripción; que la
        fuente filtre por nivel no cuenta. Sin evidencia, la vacante pasa a su categoría por área,
        a «Otros TI» si tiene algo de TI, o se rechaza.
        """
        if vacante.categoria != Categoria.PRACTICAS:
            return None
        titulo = self._limpiar(vacante.titulo)
        descripcion = self._limpiar(vacante.descripcion)
        if coincidencias(self._evidencia_practica, titulo) or coincidencias(
            self._evidencia_descripcion, descripcion
        ):
            return None
        categoria = self.categoria_por_area(titulo, descripcion)
        if categoria is None and (
            coincidencias(self._ti_generico, titulo)
            or coincidencias(self._ti_generico, descripcion)
        ):
            categoria = Categoria.OTROS_TI
        return Correccion(Categoria.PRACTICAS, categoria, "sin evidencia de práctica")

    # --- veredicto --------------------------------------------------------------------------

    def evaluar(
        self, vacante: Vacante, ahora: datetime, *, permite_detalle: bool = False
    ) -> Evaluacion:
        """Veredicto de una vacante.

        ``permite_detalle``: la fuente puede pedir el detalle de la oferta. Una oferta sin
        modalidad ni descripción que solo se rechazaría por eso no se rechaza: si por lo demás
        pasa los filtros del título, devuelve ``DUDOSA`` con ``Motivo.PENDIENTE_DETALLE``.
        """
        titulo = self._limpiar(vacante.titulo)
        descripcion = self._limpiar(vacante.descripcion)
        texto = f"{titulo} {descripcion}".strip()

        # 0. Lista negra
        negra = self._en_lista_negra(vacante)
        if negra:
            return Evaluacion(Veredicto.RECHAZAR, Motivo.LISTA_NEGRA, detalle=negra)

        # 1. Seniority: términos solo en el título; años de experiencia en título y descripción
        senior = coincidencias(self._seniority, titulo)
        if senior:
            return Evaluacion(Veredicto.RECHAZAR, Motivo.SENIORITY, detalle=senior[0])
        if self._anios_excesivos(titulo, descripcion):
            return Evaluacion(Veredicto.RECHAZAR, Motivo.SENIORITY, detalle="años de experiencia")

        # 2. Antigüedad
        if vacante.publicada is not None:
            dias = (ahora - vacante.publicada) / timedelta(days=1)
            if dias > self.config.max_dias_publicada:
                return Evaluacion(
                    Veredicto.RECHAZAR, Motivo.ANTIGUEDAD, detalle=f"{int(dias)} días"
                )

        # 3. Ubicación (ciudad base, modalidad y call center)
        geo, detalle_geo, exige = self._geografia(vacante, titulo, descripcion, permite_detalle)
        if geo == _Geo.FUERA:
            return Evaluacion(Veredicto.RECHAZAR, Motivo.UBICACION, detalle=detalle_geo)
        if geo == _Geo.PRESENCIAL_FUERA:
            return Evaluacion(Veredicto.RECHAZAR, Motivo.PRESENCIAL_FUERA, detalle=detalle_geo)
        if geo == _Geo.CALL_CENTER:
            return Evaluacion(Veredicto.RECHAZAR, Motivo.CALL_CENTER, detalle=detalle_geo)

        resultado = self._por_titulo(vacante, titulo, descripcion, texto, geo, detalle_geo, exige)
        if geo == _Geo.PENDIENTE_DETALLE and resultado.veredicto != Veredicto.RECHAZAR:
            # Solo falta la modalidad: se pide el detalle y se evalúa de nuevo con la descripción
            return Evaluacion(
                Veredicto.DUDOSA, Motivo.PENDIENTE_DETALLE, detalle=detalle_geo,
                exige_modalidad=exige,
            )  # fmt: skip
        return resultado

    def _por_titulo(
        self,
        vacante: Vacante,
        titulo: str,
        descripcion: str,
        texto: str,
        geo: _Geo,
        detalle_geo: str,
        exige: str | None,
    ) -> Evaluacion:
        """Reglas de TI, nivel y áreas no TI del título y la descripción, tras la geografía."""
        areas_titulo = [c for c, p in self._areas if coincidencias(p, titulo)]
        ti_titulo = bool(areas_titulo or coincidencias(self._ti_generico, titulo))
        ti = ti_titulo or bool(
            self.categoria_por_area("", descripcion)
            or coincidencias(self._ti_generico, descripcion)
        )
        nivel = bool(coincidencias(self._practica, texto) or coincidencias(self._junior, texto))
        # El área no TI se busca sin las frases técnicas: "Mantenimiento de cómputo" es TI,
        # "Programador de mantenimiento" no
        titulo_sin_ti = titulo
        for _, patron in self._areas:
            titulo_sin_ti = patron.sub(" ", titulo_sin_ti)
        no_ti_titulo = coincidencias(self._no_ti, titulo_sin_ti)

        # 4. Práctica sin nada de TI: solo se rechaza (sin IA) tras leer la descripción. Sin
        # descripción no hay con qué afirmarlo y decide la IA
        practica_titulo = bool(coincidencias(self._practica, titulo))
        if practica_titulo and descripcion and not ti:
            return Evaluacion(Veredicto.RECHAZAR, Motivo.NO_TI, detalle="práctica sin TI")

        # 5. Aceptar: TI en el título + nivel, salvo que el título mencione un área no TI
        # ("Programador de mantenimiento"). Si lo técnico solo está en la descripción
        # ("Auxiliar logístico … manejo de sistemas"), decide la IA.
        if ti_titulo and nivel and not no_ti_titulo:
            if geo == _Geo.CONFIRMAR_MODALIDAD:
                return Evaluacion(
                    Veredicto.DUDOSA, Motivo.DUDOSA, detalle=detalle_geo, exige_modalidad=exige
                )
            if geo == _Geo.REMOTO_SIN_PAIS:
                return Evaluacion(Veredicto.DUDOSA, Motivo.REMOTO_SIN_PAIS, detalle=detalle_geo)
            return Evaluacion(
                Veredicto.ACEPTAR, Motivo.ACEPTADA, categoria=self.categoria_por_terminos(vacante)
            )

        # 6. Rechazar si no hay nada de TI ni disparadores (un área no TI anula los disparadores)
        disparadores = [] if no_ti_titulo else coincidencias(self._disparadores, titulo)
        if not ti and not disparadores and not practica_titulo:
            return Evaluacion(
                Veredicto.RECHAZAR,
                Motivo.NO_TI,
                detalle=no_ti_titulo[0] if no_ti_titulo else "",
            )

        # 7. Dudosa en cualquier otro caso
        return Evaluacion(
            Veredicto.DUDOSA, Motivo.DUDOSA, detalle=detalle_geo, exige_modalidad=exige
        )
