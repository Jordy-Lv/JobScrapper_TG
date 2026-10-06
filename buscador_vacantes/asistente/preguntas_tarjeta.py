"""Tarjeta de preguntas rápidas: un solo mensaje para todo el bloque del cuestionario.

Muestra el progreso («Faltan N» / «Última»), la pregunta actual con sus botones y, al terminar,
un resumen para confirmar o corregir. Son funciones puras; la conversación guarda el estado y
edita el mensaje (mismo patrón que ``tarjeta.py``).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field

from buscador_vacantes.asistente import textos as t

PREGUNTANDO = "preguntando"  # pregunta actual con sus botones (o a la espera de texto)
OTRO = "otro"  # «Otro valor»: se espera un número escrito
RESUMEN = "resumen"
LISTA = "lista"  # elegir qué respuesta corregir

MAX_RESPUESTA = 40  # el resumen recorta respuestas largas (la tarjeta cabe en 4096 caracteres)
AVISO_OTRO = "Escribe el valor (solo el número, en pesos; por ejemplo 2200000)."
AVISO_NUMERO = "Escribe solo el número, en pesos (por ejemplo 2200000)."
CIERRE = "✅ Preguntas guardadas."

Botones = list[list[tuple[str, str]]]
Cb = Callable[..., str]

ETIQUETAS = {
    "nombre": "Nombre",
    "correo": "Correo",
    "telefono": "Celular",
    "documento": "Documento",
    "ciudad": "Ciudad",
    "salario": "Aspiración salarial",
    "disponibilidad_inicio": "Cuándo empiezas",
    "horario": "Horario",
    "modalidades": "Modalidades",
    "estudia_actualmente": "Estudias",
    "tipo_practica": "Qué buscas",
    "ingles_nivel": "Inglés",
    "equipo_propio": "Computador e internet",
    "traslado": "Traslado",
    "experiencia_meses": "Experiencia",
    "actualizar_cv_portal": "Actualizar CV en portales",
}


@dataclass
class Preguntas:
    mensaje_id: int | None = None
    fase: str = PREGUNTANDO
    indices: list[int] = field(default_factory=list)  # preguntas del bloque
    actual: int = 0  # índice del cuestionario que se muestra
    editando: bool = False  # se corrige una respuesta: al guardar se vuelve al resumen
    aviso: str = ""  # mensaje de error dentro de la tarjeta (valor inválido)

    def a_texto(self) -> str:
        return json.dumps(self.__dict__, ensure_ascii=False)

    @classmethod
    def de_texto(cls, valor: str | None) -> Preguntas | None:
        return cls(**json.loads(valor)) if valor else None

    def siguiente(self) -> int | None:
        """Índice de la pregunta que sigue a la actual dentro del bloque."""
        if self.actual not in self.indices:
            return None
        posicion = self.indices.index(self.actual) + 1
        return self.indices[posicion] if posicion < len(self.indices) else None


def etiqueta(indice: int) -> str:
    clave = t.CUESTIONARIO[indice].clave
    return ETIQUETAS.get(clave, clave)


def progreso(estado: Preguntas) -> str:
    """«Faltan N» (cuenta la actual) o «Última»; al corregir, «Editando»."""
    if estado.editando:
        return "<b>Editando</b>\n"
    if estado.actual not in estado.indices:
        return ""
    restantes = len(estado.indices) - estado.indices.index(estado.actual)
    return f"<b>Faltan {restantes}</b>\n" if restantes > 1 else "<b>Última</b>\n"


def texto_pregunta(estado: Preguntas, pregunta: str) -> str:
    aviso = f"\n\n⚠️ {t.e(estado.aviso)}" if estado.aviso else ""
    return progreso(estado) + t.e(pregunta) + aviso


def texto_otro(estado: Preguntas, pregunta: str) -> str:
    aviso = f"\n\n⚠️ {t.e(estado.aviso)}" if estado.aviso else ""
    return progreso(estado) + t.e(pregunta) + f"\n\n✏️ {t.e(AVISO_OTRO)}" + aviso


def botones_pregunta(
    estado: Preguntas,
    cb: Cb,
    *,
    opciones: tuple[str, ...],
    por_fila: int,
    otro: str,
    sugerido: str | None,
    opcional: bool,
) -> Botones:
    indice = estado.actual
    botones: Botones = [
        [(o, cb("cuest", indice, n)) for n, o in enumerate(opciones[i : i + por_fila], i)]
        for i in range(0, len(opciones), por_fila)
    ]
    if otro:
        botones.append([(otro, cb("cuest", indice, "otro"))])
    if sugerido:
        botones.append([(f"Usar {sugerido}", cb("cuest", indice, "sug"))])
    if opcional:
        botones.append([("Omitir", cb("cuest", indice, "omitir"))])
    if estado.editando:
        botones.append([("↩️ Volver al resumen", cb("cuest", "volver"))])
    return botones


def botones_otro(cb: Cb) -> Botones:
    return [[("↩️ Volver", cb("cuest", "volver"))]]


def valor_corto(valor: str | None) -> str:
    valor = (valor or "").strip()
    if not valor:
        return "—"
    if len(valor) > MAX_RESPUESTA:
        valor = valor[: MAX_RESPUESTA - 1] + "…"
    return valor


def formato_valor(clave: str, valor: str | None) -> str:
    """El salario se muestra con puntos de mil; el resto, tal cual (recortado)."""
    if clave == "salario" and valor and valor.isdigit():
        return "$" + f"{int(valor):,}".replace(",", ".")
    return valor_corto(valor)


def texto_resumen(estado: Preguntas, respuestas: dict[str, str]) -> str:
    lineas = []
    for i in estado.indices:
        clave = t.CUESTIONARIO[i].clave
        lineas.append(f"• {t.e(etiqueta(i))}: {t.e(formato_valor(clave, respuestas.get(clave)))}")
    return "<b>Revisa tus respuestas</b>\n" + "\n".join(lineas)


def botones_resumen(cb: Cb) -> Botones:
    return [[("✅ Confirmar", cb("cuest", "ok")), ("✏️ Editar", cb("cuest", "editar"))]]


def texto_lista() -> str:
    return "<b>¿Cuál respuesta quieres corregir?</b>"


def botones_lista(estado: Preguntas, cb: Cb) -> Botones:
    filas: Botones = [[(etiqueta(i), cb("cuest", "campo", i))] for i in estado.indices]
    filas.append([("↩️ Volver", cb("cuest", "volver"))])
    return filas
