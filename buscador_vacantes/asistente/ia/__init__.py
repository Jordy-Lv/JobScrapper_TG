"""IA del asistente con la clave del usuario: cliente genérico y un adaptador por protocolo."""

from buscador_vacantes.asistente.ia.cliente import ClienteIA, crear_clientes
from buscador_vacantes.asistente.ia.contrato import INSTRUCCION_DATOS, Parte, datos
from buscador_vacantes.asistente.ia.errores import (
    ClaveInvalida,
    CuotaAgotada,
    ErrorIA,
    ModeloNoDisponible,
    Saturado,
    TopeAlcanzado,
)

__all__ = [
    "INSTRUCCION_DATOS",
    "ClaveInvalida",
    "ClienteIA",
    "CuotaAgotada",
    "ErrorIA",
    "ModeloNoDisponible",
    "Parte",
    "Saturado",
    "TopeAlcanzado",
    "crear_clientes",
    "datos",
]
