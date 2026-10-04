"""Modelo común de vacante y enumeraciones compartidas."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class Veredicto(StrEnum):
    ACEPTAR = "aceptar"
    RECHAZAR = "rechazar"
    DUDOSA = "dudosa"


class Categoria(StrEnum):
    """Categorías de publicación. El orden de declaración es el orden del mensaje."""

    PRACTICAS = "practicas"
    DESARROLLO = "desarrollo"
    INFRAESTRUCTURA = "infraestructura"
    BASES_DATOS = "bases_datos"
    SOPORTE = "soporte"
    DATOS = "datos"
    QA = "qa"
    CIBERSEGURIDAD = "ciberseguridad"
    OTROS_TI = "otros_ti"


@dataclass
class Vacante:
    fuente: str
    id_fuente: str
    titulo: str
    empresa: str
    url: str
    keyword: str
    ubicacion: str | None = None
    modalidad: str | None = None  # Presencial / Híbrido / Remoto
    salario: str | None = None
    publicada: datetime | None = None
    descripcion: str | None = None
    categoria: Categoria | None = None

    @property
    def clave(self) -> str:
        return f"{self.fuente}:{self.id_fuente}"
