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
ANCHO_BARRA = 14
PARCIALES = " ▏▎▍▌▋▊▉"  # el índice es cuántos octavos del bloque están llenos
DURACION_ETAPA_S = 10  # estimación decorativa, no una medición
FRACCION_MAX_ETAPA = 0.9  # tope del avance dentro de una etapa

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


def barra(porcentaje: float, ancho: int = ANCHO_BARRA) -> str:
    """Barra suave: bloques llenos, uno parcial (en octavos) y el resto de relleno."""
    octavos = round(max(0.0, min(100.0, porcentaje)) / 100 * ancho * 8)
    llenos, resto = divmod(octavos, 8)
    parcial = PARCIALES[resto] if resto else ""
    return "█" * llenos + parcial + "░" * (ancho - llenos - len(parcial))


def porcentaje(etapa: int, segundos: float = 0.0) -> int:
    """Avance estimado: etapas hechas más lo que va de la actual, sin pasar de 99 %.

    Cada etapa pesa lo mismo; dentro de la actual la barra sigue avanzando con el tiempo pero
    no pasa del 90 % de su tramo, así nunca alcanza a la etapa siguiente por sí sola."""
    fraccion = min(FRACCION_MAX_ETAPA, max(0.0, segundos) / DURACION_ETAPA_S)
    return min(99, int((etapa + fraccion) / len(ETAPAS) * 100))


def restante(etapa: int, segundos: float = 0.0) -> int:
    """Segundos que se estima que faltan, nunca menos de 1."""
    return max(1, round((len(ETAPAS) - etapa) * DURACION_ETAPA_S - max(0.0, segundos)))


def linea_barra(etapa: int, segundos: float = 0.0) -> str:
    """La línea de la barra con su porcentaje y el tiempo restante estimado."""
    avance = porcentaje(etapa, segundos)
    return f"{barra(avance)}  {avance} %  ·  ~{restante(etapa, segundos)} s"


def texto(
    titulo: str | None, empresa: str | None, etapa: int, cuadro: int = 0, segundos: float = 0.0
) -> str:
    """El mensaje de progreso con la barra y la etapa actual marcada."""
    lineas = [f"<b>{t.e(titulo or 'Vacante')}</b>"]
    if empresa:
        lineas.append(t.e(empresa))
    lineas += ["", linea_barra(etapa, segundos), ""]
    lineas += etapas(etapa, cuadro)
    return "\n".join(lineas)
