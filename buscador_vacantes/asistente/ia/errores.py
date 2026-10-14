"""Errores comunes de la IA del asistente, iguales para todos los proveedores."""

from __future__ import annotations


class ErrorIA(Exception):
    """La IA no dio una respuesta usable. El mensaje es apto para el usuario.

    ``motivo`` es el texto corto que se guarda en ``ia_uso`` (nunca incluye la clave).
    """

    def __init__(self, mensaje: str = "", *, motivo: str | None = None) -> None:
        super().__init__(mensaje)
        self.motivo = motivo


class ClaveInvalida(ErrorIA):
    """El proveedor rechazó la clave del usuario (inválida o revocada)."""


class CuotaAgotada(ErrorIA):
    """Cuota o límite de frecuencia. ``espera_s`` es lo que pide el proveedor, si lo dice."""

    def __init__(
        self, mensaje: str = "", *, motivo: str | None = None, espera_s: float | None = None
    ) -> None:
        super().__init__(mensaje, motivo=motivo)
        self.espera_s = espera_s


class Saturado(ErrorIA):
    """El modelo responde 5xx por alta demanda (problema del proveedor, temporal)."""


class ModeloNoDisponible(ErrorIA):
    pass


class TopeAlcanzado(ErrorIA):
    pass
