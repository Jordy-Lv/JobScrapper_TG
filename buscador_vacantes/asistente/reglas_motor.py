"""Reglas del motor genérico de la extensión (assets/asistente/motor_generico.json).

Son datos versionados, como los selectores: el servidor los valida al cargarlos y la extensión
los recibe con su versión en el latido, para afinar textos sin publicar otra versión.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator

from buscador_vacantes.comun import config as cfg

RUTA_REGLAS = cfg.RAIZ / "assets" / "asistente" / "motor_generico.json"


class _Modelo(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TextosIdioma(_Modelo):
    es: list[str] = Field(min_length=1)
    en: list[str] = Field(min_length=1)
    pt: list[str] = Field(min_length=1)

    @field_validator("es", "en", "pt")
    @classmethod
    def _sin_vacios(cls, textos: list[str]) -> list[str]:
        if any(not t.strip() for t in textos):
            raise ValueError("hay un texto vacío")
        return textos


class Textos(_Modelo):
    avanzar: TextosIdioma
    enviar: TextosIdioma
    nunca: TextosIdioma
    intermedia: TextosIdioma
    exito: TextosIdioma
    barrera: TextosIdioma
    oauth: TextosIdioma
    verificacion: TextosIdioma
    captcha: TextosIdioma
    cookies_rechazar: TextosIdioma


class Captcha(_Modelo):
    desafio: list[str] = Field(min_length=1)  # selectores del desafío (se exige que se vea)
    tamano_minimo: int = Field(30, ge=1)  # píxeles de ancho y alto para contarlo como visible


class Cookies(_Modelo):
    banner: list[str] = Field(min_length=1)


class ReglasMotor(_Modelo):
    version: str = Field(min_length=1, max_length=20)
    nota: str = ""
    textos: Textos
    url_exito: list[str] = Field(min_length=1)
    trampas: list[str] = Field(min_length=1)
    captcha: Captcha
    cookies: Cookies


def leer_reglas(ruta: Path = RUTA_REGLAS) -> ReglasMotor:
    return ReglasMotor.model_validate(json.loads(ruta.read_text(encoding="utf-8")))


@lru_cache(maxsize=1)
def reglas() -> ReglasMotor:
    """Las reglas del repositorio, leídas una vez por proceso."""
    return leer_reglas()
