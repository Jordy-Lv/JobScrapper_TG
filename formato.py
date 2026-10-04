"""Mensajes HTML de Telegram: encabezado, categorías, fichas y división en mensajes ≤4096."""

from __future__ import annotations

import html
from dataclasses import dataclass, field
from datetime import datetime

from fechas import fecha_relativa
from modelo import Categoria, Vacante
from normalizar import normalizar_texto

LIMITE_TELEGRAM = 4096
SEPARADOR = "\n\n"

TITULOS_CATEGORIA = {
    Categoria.PRACTICAS: "🎓 PRÁCTICAS Y APRENDIZAJE",
    Categoria.DESARROLLO: "💻 DESARROLLO JUNIOR",
    Categoria.INFRAESTRUCTURA: "🚀 INFRAESTRUCTURA / DEVOPS / CLOUD JUNIOR",
    Categoria.BASES_DATOS: "🗄 BASES DE DATOS JUNIOR",
    Categoria.SOPORTE: "🛠 SOPORTE IT JUNIOR",
    Categoria.DATOS: "📊 DATOS Y ANALÍTICA JUNIOR",
    Categoria.QA: "🧪 QA / TESTING JUNIOR",
    Categoria.CIBERSEGURIDAD: "🔐 CIBERSEGURIDAD JUNIOR",
    Categoria.OTROS_TI: "🧩 OTROS TI JUNIOR",
}

NOMBRES_FUENTE = {
    "linkedin": "LinkedIn",
    "computrabajo": "Computrabajo",
    "elempleo": "elempleo",
    "magneto": "Magneto",
    "getonboard": "GetOnBoard",
    "torre": "Torre",
    "sena": "APE SENA",
}


@dataclass
class Mensaje:
    texto: str
    claves: list[str] = field(default_factory=list)  # vacantes contenidas en el mensaje


def longitud(texto: str) -> int:
    """Longitud en unidades UTF-16 del HTML completo: cota superior de lo que cuenta Telegram."""
    return len(texto.encode("utf-16-le")) // 2


def escapar(texto: str | None) -> str:
    return html.escape(texto or "", quote=False)


def encabezado(cantidad: int) -> str:
    sufijo = "vacante nueva" if cantidad == 1 else "vacantes nuevas"
    return f"🔔 <b>{cantidad} {sufijo}</b>"


def titulo_categoria(categoria: Categoria) -> str:
    emoji, _, nombre = TITULOS_CATEGORIA[categoria].partition(" ")
    return f"{emoji} <b>{escapar(nombre)}</b>"


def _lugar(vacante: Vacante) -> str:
    ubicacion = (vacante.ubicacion or "").strip()
    modalidad = (vacante.modalidad or "").strip()
    if modalidad and normalizar_texto(modalidad) in normalizar_texto(ubicacion):
        modalidad = ""
    if ubicacion and modalidad:
        return f"{escapar(ubicacion)} ({escapar(modalidad)})"
    return escapar(ubicacion or modalidad)


def ficha(vacante: Vacante, ahora: datetime) -> str:
    url = html.escape(vacante.url, quote=True)
    lineas = [f'<b><a href="{url}">{escapar(vacante.titulo)}</a></b>']
    datos = []
    if vacante.empresa and vacante.empresa.strip():
        datos.append(f"🏢 {escapar(vacante.empresa.strip())}")
    if lugar := _lugar(vacante):
        datos.append(f"📍 {lugar}")
    if datos:
        lineas.append(" · ".join(datos))
    if vacante.salario and vacante.salario.strip():
        lineas.append(f"💰 {escapar(vacante.salario.strip())}")
    origen = f"🔎 {escapar(NOMBRES_FUENTE.get(vacante.fuente, vacante.fuente))}"
    if cuando := fecha_relativa(vacante.publicada, ahora):
        origen += f" · 🕒 {cuando}"
    lineas.append(origen)
    return "\n".join(lineas)


def _ordenar(vacantes: list[Vacante]) -> list[Vacante]:
    """Por categoría en el orden fijo y, dentro de cada una, las más recientes primero."""
    orden = {categoria: i for i, categoria in enumerate(TITULOS_CATEGORIA)}

    def clave(v: Vacante) -> tuple:
        categoria = v.categoria or Categoria.OTROS_TI
        fecha = v.publicada.timestamp() if v.publicada else float("-inf")
        return (orden[categoria], -fecha)

    return sorted(vacantes, key=clave)


def componer(
    vacantes: list[Vacante], ahora: datetime, limite: int = LIMITE_TELEGRAM
) -> list[Mensaje]:
    """Arma los mensajes sin cortar fichas, repitiendo el título de categoría al continuar."""
    if not vacantes:
        return []
    mensajes: list[Mensaje] = []
    actual = Mensaje(encabezado(len(vacantes)))
    categoria_actual: Categoria | None = None

    def cabe(mensaje: Mensaje, bloque: str) -> bool:
        return longitud(mensaje.texto + SEPARADOR + bloque) <= limite

    for vacante in _ordenar(vacantes):
        categoria = vacante.categoria or Categoria.OTROS_TI
        bloque = ficha(vacante, ahora)
        if categoria != categoria_actual:
            bloque_con_titulo = titulo_categoria(categoria) + SEPARADOR + bloque
        else:
            bloque_con_titulo = bloque
        if not cabe(actual, bloque_con_titulo) and actual.claves:
            mensajes.append(actual)
            actual = Mensaje(titulo_categoria(categoria))
            bloque_con_titulo = bloque
        actual.texto += SEPARADOR + bloque_con_titulo
        actual.claves.append(vacante.clave)
        categoria_actual = categoria
    mensajes.append(actual)
    return mensajes


def empaquetar(bloques: list[str], limite: int = LIMITE_TELEGRAM) -> list[str]:
    """Une bloques en mensajes de hasta ``limite`` sin partir ningún bloque.

    Un bloque que por sí solo supera el límite se recorta (solo pasa con textos de la IA).
    """
    mensajes: list[str] = []
    actual = ""
    for bloque in bloques:
        if longitud(bloque) > limite:
            bloque = bloque[: limite // 2]
        candidato = f"{actual}{SEPARADOR}{bloque}" if actual else bloque
        if longitud(candidato) <= limite:
            actual = candidato
        else:
            mensajes.append(actual)
            actual = bloque
    if actual:
        mensajes.append(actual)
    return mensajes
