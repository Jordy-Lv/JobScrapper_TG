"""Datos de las familias de ATS (assets/asistente/familias_ats.json): selector del CV, botón de
enviar y señal de éxito de Greenhouse, Ashby, Lever y Typeform.

Son datos versionados, como los selectores y las reglas del motor: el servidor los valida al
cargarlos y la extensión los recibe con su versión en el latido, para corregirlos sin publicar otra
versión. La extensión los usa antes que las reglas genéricas. Nunca traen código.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from buscador_vacantes.comun import config as cfg

RUTA_FAMILIAS = cfg.RAIZ / "assets" / "asistente" / "familias_ats.json"
_PROHIBIDO = ("javascript:", "<script", "data:text/html")


class _Modelo(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _textos_validos(valores: list[str]) -> list[str]:
    for valor in valores:
        if not valor.strip():
            raise ValueError("hay un texto o selector vacío")
        if any(marca in valor.lower() for marca in _PROHIBIDO):
            raise ValueError(f"los datos no llevan código: {valor!r}")
    return valores


class _Lista(_Modelo):
    @field_validator("*", mode="after")
    @classmethod
    def _sin_codigo(cls, valor):
        return _textos_validos(valor) if isinstance(valor, list) else valor


class Enviar(_Lista):
    selectores: list[str] = Field(default_factory=list)
    textos: list[str] = Field(default_factory=list)  # etiqueta del botón, sin tildes ni mayúsculas


class Exito(_Lista):
    url: list[str] = Field(default_factory=list)  # fragmentos de la URL tras enviar
    textos: list[str] = Field(default_factory=list)
    selectores: list[str] = Field(default_factory=list)


class Familia(_Lista):
    cv: list[str] = Field(
        default_factory=list
    )  # selectores del archivo del CV; vacío: no hay uno fijo
    enviar: Enviar
    exito: Exito

    @model_validator(mode="after")
    def _declarada(self) -> Familia:
        if not (self.enviar.selectores or self.enviar.textos):
            raise ValueError("falta el botón de enviar (selectores o textos)")
        if not (self.exito.url or self.exito.textos or self.exito.selectores):
            raise ValueError("falta la señal de éxito (url, textos o selectores)")
        return self


class FamiliasATS(_Modelo):
    version: str = Field(min_length=1, max_length=20)
    nota: str = ""
    familias: dict[str, Familia] = Field(min_length=1)


def leer_familias(ruta: Path = RUTA_FAMILIAS) -> FamiliasATS:
    return FamiliasATS.model_validate(json.loads(ruta.read_text(encoding="utf-8")))


@lru_cache(maxsize=1)
def familias() -> FamiliasATS:
    """Los datos del repositorio, leídos una vez por proceso."""
    return leer_familias()
