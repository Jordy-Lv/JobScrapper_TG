"""Diagnóstico de la espera: por qué una postulación en cola todavía no sale hacia la extensión.

Funciones puras sobre lo que el servidor ya sabe (último latido de cada navegador, configuración
de la plataforma y reglas de la cola). El orden de prioridad vive solo en ``causa``: la primera
que aplica es la única que se explica, y las que dependen de otra (la sesión no importa si la
extensión no recibe trabajos) quedan detrás.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from buscador_vacantes.asistente.cola import Restriccion
from buscador_vacantes.asistente.cuentas_portal import EstadoCuenta
from buscador_vacantes.comun.estado import a_texto

SIN_NAVEGADOR = "sin_navegador"
SIN_LATIDO = "sin_latido"
EXTENSION_DESACTUALIZADA = "extension_desactualizada"
EXTENSION_EN_PAUSA = "extension_en_pausa"
PLATAFORMA_APAGADA = "plataforma_apagada"
SIN_PERMISO = "sin_permiso"
SIN_SESION = "sin_sesion"
CUENTA_POR_CONFIRMAR = "cuenta_por_confirmar"
CUENTA_DISTINTA = "cuenta_distinta"
CORREO_ILEGIBLE = "correo_ilegible"
PERFIL_INCOMPLETO = "perfil_incompleto"
OTRA_EN_CURSO = "otra_en_curso"
TOPE_DIARIO = "tope_diario"
PAUSA = "pausa"
TOPE_LINKEDIN = "tope_linkedin"
PAUSA_LINKEDIN = "pausa_linkedin"
LINKEDIN_PAUSADO = "linkedin_pausado"

CAUSAS = (
    SIN_NAVEGADOR, SIN_LATIDO, EXTENSION_DESACTUALIZADA, EXTENSION_EN_PAUSA, PLATAFORMA_APAGADA,
    SIN_PERMISO, SIN_SESION, CUENTA_POR_CONFIRMAR, CUENTA_DISTINTA, CORREO_ILEGIBLE,
    PERFIL_INCOMPLETO, OTRA_EN_CURSO, TOPE_DIARIO, PAUSA, TOPE_LINKEDIN, PAUSA_LINKEDIN,
    LINKEDIN_PAUSADO,
)  # fmt: skip

# Causa de la cola (restricción) → causa de la espera
_DE_RESTRICCION = {
    "en_curso": OTRA_EN_CURSO, "tope_diario": TOPE_DIARIO, "pausa": PAUSA,
    "tope_linkedin": TOPE_LINKEDIN, "pausa_linkedin": PAUSA_LINKEDIN,
    "linkedin_pausado": LINKEDIN_PAUSADO,
}  # fmt: skip
_DE_CUENTA = {
    EstadoCuenta.POR_CONFIRMAR: CUENTA_POR_CONFIRMAR,
    EstadoCuenta.DISTINTA: CUENTA_DISTINTA,
    EstadoCuenta.SIN_CORREO: CORREO_ILEGIBLE,
}


def version_tupla(version: str) -> tuple[int, ...]:
    try:
        return tuple(int(p) for p in version.split("."))
    except ValueError:
        return (0,)


@dataclass(frozen=True)
class NavegadorLatido:
    """Lo último que reportó un navegador vinculado (no revocado)."""

    id: int
    ultimo_latido: datetime | None
    version: str | None
    portales: dict[str, Any] = field(default_factory=dict)  # portales_json, con `_pausado`


@dataclass(frozen=True)
class Entrada:
    plataforma: str
    navegadores: list[NavegadorLatido]
    ahora: datetime
    version_minima: str
    navegador_caido: timedelta
    plataforma_encendida: bool  # `/plataformas` y selectores cargados
    restriccion: Restriccion | None = None  # lo que frena a la postulación en la cola


@dataclass(frozen=True)
class Causa:
    """``datos`` solo lleva valores estables (horas, versiones), nunca cuentas regresivas."""

    codigo: str
    plataforma: str
    datos: dict[str, str] = field(default_factory=dict)

    def a_dict(self) -> dict[str, Any]:
        return {"codigo": self.codigo, "plataforma": self.plataforma, "datos": dict(self.datos)}

    @classmethod
    def de_dict(cls, datos: dict[str, Any] | None) -> Causa | None:
        if not datos:
            return None
        return cls(datos["codigo"], datos["plataforma"], dict(datos.get("datos") or {}))


def causa(entrada: Entrada) -> Causa | None:
    """La causa que explica la espera, o None si nada la frena."""
    if not entrada.navegadores:
        return Causa(SIN_NAVEGADOR, entrada.plataforma)
    vigentes = [n for n in entrada.navegadores if _reciente(n, entrada)]
    if not vigentes:
        ultimo = max(
            (n.ultimo_latido for n in entrada.navegadores if n.ultimo_latido), default=None
        )
        return Causa(SIN_LATIDO, entrada.plataforma, {"ultimo": a_texto(ultimo)} if ultimo else {})
    propias = [_causa_del_navegador(n, entrada) for n in vigentes]
    if all(propias):
        # Todos tienen algo pendiente: se explica el del latido más reciente
        reciente = max(
            range(len(vigentes)), key=lambda i: vigentes[i].ultimo_latido or entrada.ahora
        )
        return propias[reciente]
    if entrada.restriccion:
        return Causa(
            _DE_RESTRICCION[entrada.restriccion.codigo], entrada.plataforma, _cuando(entrada)
        )
    return None


def _reciente(n: NavegadorLatido, entrada: Entrada) -> bool:
    return (
        n.ultimo_latido is not None and entrada.ahora - n.ultimo_latido <= entrada.navegador_caido
    )


def _cuando(entrada: Entrada) -> dict[str, str]:
    cuando = entrada.restriccion.cuando if entrada.restriccion else None
    return {"cuando": a_texto(cuando)} if cuando else {}


def _causa_del_navegador(n: NavegadorLatido, entrada: Entrada) -> Causa | None:
    plataforma = entrada.plataforma
    if version_tupla(n.version or "") < version_tupla(entrada.version_minima):
        return Causa(
            EXTENSION_DESACTUALIZADA, plataforma,
            {"version": n.version or "?", "minima": entrada.version_minima},
        )  # fmt: skip
    if n.portales.get("_pausado"):
        return Causa(EXTENSION_EN_PAUSA, plataforma)
    if not entrada.plataforma_encendida:
        return Causa(PLATAFORMA_APAGADA, plataforma)
    portal = n.portales.get(plataforma) or {}
    estado = portal.get("estado")
    if estado in (None, "sin_permiso"):
        return Causa(SIN_PERMISO, plataforma)
    if estado == "sin_sesion":
        return Causa(SIN_SESION, plataforma)
    cuenta = _DE_CUENTA.get(portal.get("cuenta"))
    if cuenta:
        return Causa(cuenta, plataforma)
    if estado == "incompleto":
        return Causa(PERFIL_INCOMPLETO, plataforma)
    return None
