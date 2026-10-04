"""Respuestas a las preguntas de postulación con el mínimo uso de IA.

Orden: banco compartido (campo del perfil) → respuestas aprendidas del usuario → clasificar la
pregunta nueva con IA (se guarda en el banco para todos) → redactar con IA si es abierta.
Lo que no se puede sustentar con los datos del usuario no se inventa: queda "falta dato" y se
le pregunta una sola vez.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from buscador_vacantes.asistente import campos
from buscador_vacantes.asistente.campos import DatosUsuario
from buscador_vacantes.asistente.datos import BaseAsistente
from buscador_vacantes.asistente.gemini import ClienteGemini, ErrorIA, Parte, datos
from buscador_vacantes.config import RAIZ
from buscador_vacantes.estado import a_texto
from buscador_vacantes.normalizar import normalizar_texto

RUTA_BANCO = RAIZ / "assets" / "banco_preguntas.yaml"
MAX_PREGUNTAS_PEGADAS = 15
MAX_CARACTERES_PEGADOS = 4000

SI = {"si", "s", "yes", "true", "verdadero", "afirmativo", "claro"}
NO = {"no", "n", "false", "falso", "negativo", "ninguno", "ninguna"}


class Origen(StrEnum):
    PERFIL = "perfil"  # campo conocido del perfil o cuestionario (vía banco)
    BANCO = "banco"  # pregunta clasificada por primera vez y guardada en el banco
    APRENDIDA = "aprendida"
    IA = "ia"
    USUARIO = "usuario"


@dataclass
class Pregunta:
    texto: str
    tipo: str = "texto"  # texto | opciones | numero | correo | telefono | archivo | fecha
    opciones: list[str] = field(default_factory=list)
    obligatoria: bool = True
    nombre: str | None = None  # atributo name del campo, si lo envía la extensión


@dataclass
class Respuesta:
    pregunta: Pregunta
    valor: str | None = None
    opcion: int | None = None  # índice en pregunta.opciones
    origen: Origen | None = None
    campo: str | None = None
    falta: bool = False  # no se pudo responder con fundamento: hay que preguntarle al usuario

    @property
    def texto(self) -> str | None:
        if self.opcion is not None:
            return self.pregunta.opciones[self.opcion]
        return self.valor


class ErrorPegado(ValueError):
    pass


# --- normalización y banco ----------------------------------------------------------


def normalizar_pregunta(texto: str) -> str:
    texto = normalizar_texto(texto)
    texto = re.sub(r"^\s*(\d+|[a-z])[.)-]\s+", "", texto)  # numeración
    texto = re.sub(r"\((obligatori[oa]|opcional|requerid[oa])\)", "", texto)
    texto = re.sub(r"[¿?¡!:*.,;\"'()]", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


@lru_cache(maxsize=1)
def semilla(ruta: Path = RUTA_BANCO) -> list[dict]:
    return yaml.safe_load(ruta.read_text(encoding="utf-8"))


def sembrar_banco(base: BaseAsistente, ahora: datetime) -> int:
    """Carga las preguntas sembradas que falten. Devuelve cuántas se agregaron."""
    agregadas = 0
    with base.transaccion() as cx:
        for item in semilla():
            cur = cx.execute(
                "INSERT OR IGNORE INTO banco_preguntas(pregunta_norm, campo, parametro, origen, "
                "creada) VALUES (?, ?, ?, 'semilla', ?)",
                (
                    normalizar_pregunta(item["pregunta"]),
                    item["campo"],
                    item.get("parametro"),
                    a_texto(ahora),
                ),
            )
            agregadas += cur.rowcount
    return agregadas


def buscar_en_banco(base: BaseAsistente, pregunta_norm: str) -> tuple[str, str | None] | None:
    fila = base.cx.execute(
        "SELECT campo, parametro FROM banco_preguntas WHERE pregunta_norm = ?", (pregunta_norm,)
    ).fetchone()
    if not fila:
        return None
    with base.transaccion() as cx:
        cx.execute(
            "UPDATE banco_preguntas SET usos = usos + 1 WHERE pregunta_norm = ?", (pregunta_norm,)
        )
    return fila["campo"], fila["parametro"]


def guardar_en_banco(
    base: BaseAsistente, pregunta_norm: str, campo: str, parametro: str | None, ahora: datetime
) -> None:
    with base.transaccion() as cx:
        cx.execute(
            "INSERT OR IGNORE INTO banco_preguntas(pregunta_norm, campo, parametro, origen, "
            "creada) VALUES (?, ?, ?, 'ia', ?)",
            (pregunta_norm, campo, parametro, a_texto(ahora)),
        )


def aprendida(base: BaseAsistente, usuario_id: int, pregunta_norm: str) -> str | None:
    fila = base.cx.execute(
        "SELECT respuesta FROM respuestas_aprendidas WHERE usuario_id = ? AND pregunta_norm = ?",
        (usuario_id, pregunta_norm),
    ).fetchone()
    return fila["respuesta"] if fila else None


def recordar(
    base: BaseAsistente, usuario_id: int, pregunta: str, respuesta: str, ahora: datetime
) -> None:
    with base.transaccion() as cx:
        cx.execute(
            "INSERT INTO respuestas_aprendidas(usuario_id, pregunta_norm, respuesta, actualizada) "
            "VALUES (?, ?, ?, ?) ON CONFLICT(usuario_id, pregunta_norm) "
            "DO UPDATE SET respuesta = excluded.respuesta, actualizada = excluded.actualizada",
            (usuario_id, normalizar_pregunta(pregunta), respuesta, a_texto(ahora)),
        )


# --- opciones -------------------------------------------------------------------------


def _numeros(texto: str) -> list[float]:
    limpio = re.sub(r"(?<=\d)[.,](?=\d{3}\b)", "", texto)  # separadores de miles
    return [float(n.replace(",", ".")) for n in re.findall(r"\d+(?:[.,]\d+)?", limpio)]


def elegir_opcion(valor: str, opciones: list[str]) -> int | None:
    """Índice de la opción que corresponde al valor, o None si ninguna corresponde."""
    if not opciones:
        return None
    norma = normalizar_texto(valor)
    normas = [normalizar_texto(o) for o in opciones]
    if norma in normas:
        return normas.index(norma)
    if norma in SI | NO:
        buscado = SI if norma in SI else NO
        for i, o in enumerate(normas):
            if o in buscado or o.split(" ")[0] in buscado:
                return i
    for i, o in enumerate(normas):  # "B1" ⊂ "Intermedio (B1)", "intermedio" ⊂ "B1 - Intermedio"
        if len(norma) >= 2 and (re.search(rf"\b{re.escape(norma)}\b", o) or o in norma):
            return i
    numeros = _numeros(valor)
    if numeros:  # rangos de salario o semestres
        objetivo = numeros[0]
        for i, o in enumerate(opciones):
            n = _numeros(o)
            if len(n) >= 2 and n[0] <= objetivo <= n[1]:
                return i
            if len(n) == 1 and n[0] == objetivo:
                return i
            if len(n) == 1 and re.search(r"m[aá]s de|superior|mayor", normalizar_texto(o)):
                if objetivo > n[0]:
                    return i
            if len(n) == 1 and re.search(r"menos de|inferior|hasta", normalizar_texto(o)):
                if objetivo <= n[0]:
                    return i
    return None


# --- salidas de la IA -------------------------------------------------------------------


class Clasificacion(BaseModel):
    campo: str | None = Field(None, description="uno de los campos del catálogo o null")
    parametro: str | None = Field(None, description="herramienta o idioma, si aplica")
    abierta: bool = Field(description="true si la pregunta pide redactar una respuesta propia")


class Redaccion(BaseModel):
    respuesta: str | None = None
    opcion: int | None = Field(None, description="índice de la opción elegida, si hay opciones")
    suficiente: bool = Field(description="false si el perfil no basta para responder")


def _instruccion_clasificar() -> str:
    lineas = [f"- {c}: {d}" for c, d in campos.CAMPOS.items()]
    lineas += [f"- {c}: {d}" for c, d in campos.CAMPOS_PARAMETRO.items()]
    return (
        "Clasifica la pregunta de un formulario de postulación según el dato que pide. "
        "Campos posibles:\n" + "\n".join(lineas) + "\nSi pide redactar algo propio (motivación, "
        "describir un logro, por qué te interesa), responde abierta=true y campo=null. Si no "
        "corresponde a ningún campo y no es abierta, campo=null y abierta=false."
    )


INSTRUCCION_REDACTAR = (
    "Responde la pregunta del formulario como si fueras el candidato, en primera persona, en "
    "español, breve (máximo 3 frases) y profesional. Usa solo los datos del perfil; si no "
    "alcanzan para responder con verdad, responde suficiente=false. Si la pregunta trae "
    "opciones, elige solo una de ellas por su índice."
)


@dataclass
class Contexto:
    base: BaseAsistente
    usuario_id: int
    datos: DatosUsuario
    ahora: datetime
    cliente: ClienteGemini | None = None
    clave: str | None = None
    vacante: str = ""  # título, empresa y descripción, para redactar

    @property
    def con_ia(self) -> bool:
        return self.cliente is not None and bool(self.clave)


def _desde_campo(pregunta, campo, parametro, ctx: Contexto, origen: Origen) -> Respuesta:
    valor = ctx.datos.valor(campo, parametro)
    if valor is None:
        return Respuesta(pregunta, campo=campo, falta=True)
    if pregunta.opciones:
        indice = elegir_opcion(valor, pregunta.opciones)
        if indice is None:
            return Respuesta(pregunta, campo=campo, falta=True)
        return Respuesta(pregunta, opcion=indice, origen=origen, campo=campo)
    return Respuesta(pregunta, valor=valor, origen=origen, campo=campo)


def _desde_tipo(pregunta: Pregunta) -> tuple[str, None] | None:
    """Campos estándar identificables sin IA por su tipo o atributo name."""
    nombre = normalizar_texto(pregunta.nombre or "")
    if pregunta.tipo == "correo" or "email" in nombre or "correo" in nombre:
        return "correo", None
    if pregunta.tipo == "telefono" or any(t in nombre for t in ("phone", "telefono", "celular")):
        return "telefono", None
    return None


async def resolver(pregunta: Pregunta, ctx: Contexto) -> Respuesta:
    norma = normalizar_pregunta(pregunta.texto)
    if estandar := _desde_tipo(pregunta):
        return _desde_campo(pregunta, *estandar, ctx, Origen.PERFIL)
    if encontrada := buscar_en_banco(ctx.base, norma):
        return _desde_campo(pregunta, *encontrada, ctx, Origen.PERFIL)
    if (texto := aprendida(ctx.base, ctx.usuario_id, norma)) is not None:
        if pregunta.opciones:
            indice = elegir_opcion(texto, pregunta.opciones)
            if indice is not None:
                return Respuesta(pregunta, opcion=indice, origen=Origen.APRENDIDA)
        else:
            return Respuesta(pregunta, valor=texto, origen=Origen.APRENDIDA)
    if not ctx.con_ia:
        return Respuesta(pregunta, falta=True)
    try:
        clasificacion = await ctx.cliente.generar(
            "clasificar_pregunta", ctx.clave, ctx.usuario_id, _instruccion_clasificar(),
            [Parte(datos("pregunta", _pregunta_con_opciones(pregunta)))], Clasificacion,
        )  # fmt: skip
    except ErrorIA:
        return Respuesta(pregunta, falta=True)
    if clasificacion.campo and campos.es_campo_valido(clasificacion.campo, clasificacion.parametro):
        guardar_en_banco(ctx.base, norma, clasificacion.campo, clasificacion.parametro, ctx.ahora)
        return _desde_campo(
            pregunta, clasificacion.campo, clasificacion.parametro, ctx, Origen.BANCO
        )
    # Fuera del catálogo: se trata como abierta y se redacta con el perfil
    return await _redactar(pregunta, ctx)


def _pregunta_con_opciones(pregunta: Pregunta) -> str:
    if not pregunta.opciones:
        return pregunta.texto
    opciones = "\n".join(f"{i}. {o}" for i, o in enumerate(pregunta.opciones))
    return f"{pregunta.texto}\nOpciones:\n{opciones}"


async def _redactar(pregunta: Pregunta, ctx: Contexto) -> Respuesta:
    try:
        redaccion = await ctx.cliente.generar(
            "responder", ctx.clave, ctx.usuario_id, INSTRUCCION_REDACTAR,
            [
                Parte(datos("perfil", json.dumps(ctx.datos.para_ia(), ensure_ascii=False))),
                Parte(datos("vacante", ctx.vacante)),
                Parte(datos("pregunta", _pregunta_con_opciones(pregunta))),
            ],
            Redaccion,
        )  # fmt: skip
    except ErrorIA:
        return Respuesta(pregunta, falta=True)
    if not redaccion.suficiente:
        return Respuesta(pregunta, falta=True)
    if pregunta.opciones:
        if redaccion.opcion is None or not 0 <= redaccion.opcion < len(pregunta.opciones):
            return Respuesta(pregunta, falta=True)
        return Respuesta(pregunta, opcion=redaccion.opcion, origen=Origen.IA)
    if not (redaccion.respuesta or "").strip():
        return Respuesta(pregunta, falta=True)
    return Respuesta(pregunta, valor=redaccion.respuesta.strip(), origen=Origen.IA)


# --- preguntas pegadas por el usuario -------------------------------------------------------

_VINETA = re.compile(r"^\s*(?:[-•*○◯◦▪]|\(\s?\)|\[\s?\]|[a-z][.)])\s+", re.IGNORECASE)


def separar_preguntas(texto: str) -> list[Pregunta]:
    """Divide el texto pegado en preguntas. Las líneas con viñeta tras una pregunta son opciones;
    también "Pregunta: A / B / C"."""
    if len(texto) > MAX_CARACTERES_PEGADOS:
        raise ErrorPegado(f"El texto supera {MAX_CARACTERES_PEGADOS} caracteres; recórtalo.")
    preguntas: list[Pregunta] = []
    for linea in (fila.strip() for fila in texto.splitlines()):
        if not linea:
            continue
        if _VINETA.match(linea) and preguntas:
            preguntas[-1].opciones.append(_VINETA.sub("", linea).strip())
            preguntas[-1].tipo = "opciones"
            continue
        if ":" in linea and " / " in linea.split(":", 1)[1]:
            enunciado, resto = linea.split(":", 1)
            opciones = [o.strip() for o in resto.split(" / ") if o.strip()]
            preguntas.append(Pregunta(enunciado.strip(), "opciones", opciones))
            continue
        preguntas.append(Pregunta(linea))
    if len(preguntas) > MAX_PREGUNTAS_PEGADAS:
        raise ErrorPegado(
            f"Son {len(preguntas)} preguntas; envía como máximo {MAX_PREGUNTAS_PEGADAS} a la vez."
        )
    return preguntas
