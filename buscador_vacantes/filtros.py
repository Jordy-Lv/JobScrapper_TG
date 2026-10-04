"""Veredicto aceptar/rechazar/dudosa y categoría de cada vacante, por reglas deterministas."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from buscador_vacantes import config as cfg
from buscador_vacantes.modelo import Categoria, Vacante, Veredicto
from buscador_vacantes.normalizar import coincidencias, compilar_terminos, normalizar_texto

_EXPERIENCIA = r"(?:experiencia|experience)"
_ANIOS = r"(?:anos?|years?)"
# "2 a 3 años", "2-3 years": cuenta el mínimo del rango
_RANGO = re.compile(rf"(?<!\d)(\d{{1,2}})\s*(?:-|a|y|to)\s*(\d{{1,2}})\s*\+?\s*{_ANIOS}\b")
_ANIOS_SUELTOS = re.compile(rf"(?<!\d)(\d{{1,2}})\s*(?:\+|o mas|or more)?\s*{_ANIOS}\b")


class Motivo(StrEnum):
    SENIORITY = "seniority"
    ANTIGUEDAD = "antiguedad"
    UBICACION = "ubicacion"
    NO_TI = "no_ti"
    ACEPTADA = "aceptada"
    DUDOSA = "dudosa"
    REMOTO_SIN_PAIS = "remoto_sin_pais"


@dataclass(frozen=True)
class Evaluacion:
    veredicto: Veredicto
    motivo: Motivo
    categoria: Categoria | None = None
    detalle: str = ""


class _Geo(StrEnum):
    OK = "ok"
    FUERA = "fuera"
    REMOTO_SIN_PAIS = "remoto_sin_pais"


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

    def _geografia(self, vacante: Vacante, titulo: str, descripcion: str) -> tuple[_Geo, str]:
        lugar = self._limpiar(f"{vacante.ubicacion or ''} {vacante.modalidad or ''}")
        cercano = f"{lugar} {titulo}"
        completo = f"{cercano} {descripcion}"
        en_colombia = bool(
            vacante.fuente in self._fuentes_colombianas
            or coincidencias(self._colombia, cercano)
            or coincidencias(self._solo_colombia, completo)
        )
        en_latam = bool(coincidencias(self._latam, completo))
        exterior = coincidencias(self._exterior, cercano)
        remoto = bool(coincidencias(self._remoto, completo))

        if not remoto:
            if coincidencias(self._colombia, lugar) or not lugar:
                return _Geo.OK, ""
            if exterior:
                return _Geo.FUERA, f"presencial en {exterior[0]}"
            return _Geo.OK, ""

        if self._restriccion is not None:
            for restriccion in self._restriccion.finditer(completo):
                destino = restriccion.group(1)
                if coincidencias(self._colombia, destino) or coincidencias(self._latam, destino):
                    return _Geo.OK, ""
                if coincidencias(self._exterior, destino):
                    return _Geo.FUERA, f"remoto restringido a {destino.strip()}"
        if en_colombia or en_latam:
            return _Geo.OK, ""
        if exterior:
            return _Geo.FUERA, f"remoto en {exterior[0]}"
        return _Geo.REMOTO_SIN_PAIS, "remoto sin país"

    # --- veredicto --------------------------------------------------------------------------

    def evaluar(self, vacante: Vacante, ahora: datetime) -> Evaluacion:
        titulo = self._limpiar(vacante.titulo)
        descripcion = self._limpiar(vacante.descripcion)
        texto = f"{titulo} {descripcion}".strip()

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

        # 3. Ubicación
        geo, detalle_geo = self._geografia(vacante, titulo, descripcion)
        if geo == _Geo.FUERA:
            return Evaluacion(Veredicto.RECHAZAR, Motivo.UBICACION, detalle=detalle_geo)

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

        # 4. Aceptar: TI en el título + nivel, salvo que el título mencione un área no TI
        # ("Programador de mantenimiento"). Si lo técnico solo está en la descripción
        # ("Auxiliar logístico … manejo de sistemas"), decide la IA.
        if ti_titulo and nivel and not no_ti_titulo:
            if geo == _Geo.REMOTO_SIN_PAIS:
                return Evaluacion(Veredicto.DUDOSA, Motivo.REMOTO_SIN_PAIS, detalle=detalle_geo)
            return Evaluacion(
                Veredicto.ACEPTAR, Motivo.ACEPTADA, categoria=self.categoria_por_terminos(vacante)
            )

        # 5. Rechazar si no hay nada de TI ni disparadores (un área no TI anula los disparadores).
        # Excepción: las prácticas ("Practicante administrativo") nunca se rechazan aquí; la IA
        # decide según sus funciones, porque la prioridad del canal son las prácticas
        disparadores = [] if no_ti_titulo else coincidencias(self._disparadores, titulo)
        if not ti and not disparadores and not coincidencias(self._practica, titulo):
            return Evaluacion(
                Veredicto.RECHAZAR,
                Motivo.NO_TI,
                detalle=no_ti_titulo[0] if no_ti_titulo else "",
            )

        # 6. Dudosa en cualquier otro caso
        return Evaluacion(Veredicto.DUDOSA, Motivo.DUDOSA, detalle=detalle_geo)
