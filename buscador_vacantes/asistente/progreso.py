"""Mensaje de progreso de una postulación en curso: un solo mensaje que se edita.

Muestra las etapas como una lista corta: las hechas con ✓, la actual con un indicador que gira
y las que faltan en gris. Son funciones puras; la conversación se encarga de editar el mensaje.
"""

from __future__ import annotations

from buscador_vacantes.asistente import textos as t

ETAPAS = (
    "Abriendo la oferta",
    "Preparando tu hoja de vida",
    "Respondiendo el formulario",
    "Enviando y confirmando",
)
CUADROS = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

# Paso que reporta la extensión → etapa que ya está en marcha
_ETAPA_DE_PASO = {
    "abrir": 0,
    "cv_subir": 1,
    "cv_verificar": 1,
    "cv_liberado": 1,
    "llenado": 2,
    "envio_pulsado": 3,
    "enviar": 3,
    "confirmacion": 3,
}


def etapa_de_paso(paso: str) -> int | None:
    return _ETAPA_DE_PASO.get(paso)


def etapas(etapa: int, cuadro: int = 0) -> list[str]:
    """Una línea por etapa: hechas con ✓, la actual con el indicador y las que faltan en gris."""
    lineas = []
    for n, nombre in enumerate(ETAPAS):
        if n < etapa:
            lineas.append(f"✓ {nombre}")
        elif n == etapa:
            lineas.append(f"{CUADROS[cuadro % len(CUADROS)]} <b>{nombre}…</b>")
        else:
            lineas.append(f"<i>· {nombre}</i>")
    return lineas


def texto(titulo: str | None, empresa: str | None, etapa: int, cuadro: int = 0) -> str:
    """El mensaje de progreso con la etapa actual marcada."""
    lineas = [f"<b>{t.e(titulo or 'Vacante')}</b>"]
    if empresa:
        lineas.append(t.e(empresa))
    lineas.append("")
    lineas += etapas(etapa, cuadro)
    return "\n".join(lineas)
