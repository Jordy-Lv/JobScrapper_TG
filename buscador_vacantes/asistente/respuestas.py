"""Respuestas a las preguntas de postulación con el mínimo uso de IA.

Orden: respuestas aprendidas del usuario → banco compartido (campo del perfil) → clasificar la
pregunta nueva con IA (se guarda en el banco para todos). Las preguntas de texto compuestas o en
prosa quedan marcadas para el redactor por formulario, que las redacta todas en una llamada.
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
from typing import Literal

import yaml
from pydantic import BaseModel, Field

from buscador_vacantes.asistente import campos
from buscador_vacantes.asistente.campos import CONTACTO, RESERVADO, DatosUsuario
from buscador_vacantes.asistente.datos import BaseAsistente
from buscador_vacantes.asistente.ia import ClaveInvalida, ClienteIA, ErrorIA, Parte, datos
from buscador_vacantes.comun.config import RAIZ
from buscador_vacantes.comun.estado import a_texto
from buscador_vacantes.comun.normalizar import normalizar_texto

RUTA_BANCO = RAIZ / "assets" / "asistente" / "banco_preguntas.yaml"
REDACTAR = "redactar"  # campo del banco: la pregunta se redacta, no es un dato del catálogo
TIPOS_REDACTABLES = {"texto"}  # opciones, número, fecha, correo y teléfono nunca se redactan
MAX_APRENDIDOS_IA = 40  # datos aprendidos de formulario (los más recientes) para el redactor
MAX_SUGERENCIA = 40
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
    maximo: int | None = None  # maxlength del campo, si el portal lo informa


@dataclass
class Respuesta:
    pregunta: Pregunta
    valor: str | None = None
    opcion: int | None = None  # índice en pregunta.opciones
    origen: Origen | None = None
    campo: str | None = None
    falta: bool = False  # no se pudo responder con fundamento: hay que preguntarle al usuario
    redactar: bool = False  # va al redactor por formulario (pregunta de texto compuesta o prosa)
    datos: list[DatoFaltante] = field(default_factory=list)  # lo que el redactor pide al usuario

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
    formato: Literal["dato", "redactar"] = Field(
        description="dato: pide solo el valor de un campo; redactar: prosa, varios datos o "
        "ninguno del catálogo"
    )


class DatoFaltante(BaseModel):
    pregunta: str = Field(description="pregunta corta en segunda persona por el dato que falta")
    sugerencias: list[str] = Field(
        default_factory=list, description="de 2 a 4 respuestas probables y cortas"
    )


class RespuestaRedactada(BaseModel):
    indice: int = Field(description="número de la pregunta")
    respuesta: str | None = Field(None, description="null si falta un dato del usuario")
    faltan: list[DatoFaltante] = Field(default_factory=list)


class RedaccionFormulario(BaseModel):
    respuestas: list[RespuestaRedactada] = Field(default_factory=list)


def _instruccion_clasificar() -> str:
    lineas = [f"- {c}: {d}" for c, d in campos.CAMPOS.items()]
    lineas += [f"- {c}: {d}" for c, d in campos.CAMPOS_PARAMETRO.items()]
    return (
        "Clasifica la pregunta de un formulario de postulación según el dato que pide. "
        "Campos posibles:\n" + "\n".join(lineas) + "\nResponde formato=dato solo si la pregunta "
        "pide únicamente el valor de UN campo y se contesta con ese valor (por ejemplo «Ciudad de "
        "residencia» o «¿Nivel de inglés?»). Responde formato=redactar y campo=null si está "
        "formulada para responderse en prosa, pide varios datos a la vez (por ejemplo programa "
        "e institución) o no corresponde a ningún campo."
    )


INSTRUCCION_REDACTAR_FORMULARIO = (
    "Eres el candidato y respondes las preguntas abiertas de un formulario de postulación, "
    "numeradas en «preguntas». Para cada una devuelve su número en indice y su respuesta.\n"
    "- Escribe en primera persona, en español, con tono natural y profesional, sin muletillas "
    "de plantilla («Me apasiona…», «Soy una persona proactiva…») y sin copiar el CV "
    "literalmente.\n"
    "- Responde TODO lo que pide cada pregunta: si pide dos datos, los dos.\n"
    "- La longitud va con la pregunta: una o dos frases para un dato; varias para motivación "
    "o experiencia.\n"
    "- Conecta con la vacante cuando aporte.\n"
    "- Usa solo el perfil, el cuestionario y los datos del usuario; los datos del usuario "
    "mandan sobre el CV.\n"
    "- No inventes nada. Si para responder bien falta un dato que solo el usuario sabe, deja "
    "respuesta=null y en faltan pon una pregunta corta en segunda persona por ese dato (por "
    "ejemplo «¿En qué institución estudias?») con 2 a 4 sugerencias cortas y probables.\n"
    "- Un dato marcado «(prefiere no decirlo)» no se vuelve a pedir: redacta sin él.\n"
    "- Si la pregunta dice «máximo N caracteres», la respuesta no lo supera."
)


@dataclass
class Contexto:
    base: BaseAsistente
    usuario_id: int
    datos: DatosUsuario
    ahora: datetime
    cliente: ClienteIA | None = None
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


# Autorizaciones y aceptaciones (tratamiento de datos, términos): las decide el usuario. No se
# confunde con «¿tienes autorización para trabajar?», que es un dato del perfil.
_CONSENTIMIENTO = re.compile(
    r"tratamiento de (?:tus |sus |mis )?datos|datos personales|habeas data|terminos y condiciones"
    r"|politicas? de (?:privacidad|tratamiento)|consentimiento|\bautoriz(?:o|as|a|amos)\b"
)


def es_consentimiento(norma: str) -> bool:
    """True si la pregunta (ya normalizada) pide autorizar o aceptar algo."""
    return bool(_CONSENTIMIENTO.search(norma))


async def resolver(pregunta: Pregunta, ctx: Contexto) -> Respuesta:
    norma = normalizar_pregunta(pregunta.texto)
    if estandar := _desde_tipo(pregunta):
        return _desde_campo(pregunta, *estandar, ctx, Origen.PERFIL)
    # Lo que el usuario respondió o corrigió manda sobre el banco y el perfil; si no, una
    # pregunta del banco sin dato en el perfil se volvería a preguntar en bucle
    texto = aprendida(ctx.base, ctx.usuario_id, norma)
    if texto is not None and texto != RESERVADO:
        if pregunta.opciones:
            indice = elegir_opcion(texto, pregunta.opciones)
            if indice is not None:
                return Respuesta(pregunta, opcion=indice, origen=Origen.APRENDIDA)
        else:
            return Respuesta(pregunta, valor=texto, origen=Origen.APRENDIDA)
    if es_consentimiento(norma):
        # Solo vale lo que el usuario respondió: ni el banco ni la IA aceptan por él
        return Respuesta(pregunta, falta=True)
    if encontrada := buscar_en_banco(ctx.base, norma):
        if encontrada[0] == REDACTAR:
            return _para_redactar(pregunta)
        return _desde_campo(pregunta, *encontrada, ctx, Origen.PERFIL)
    if not ctx.con_ia:
        return Respuesta(pregunta, falta=True)
    try:
        clasificacion = await ctx.cliente.generar(
            "clasificar_pregunta", ctx.clave, ctx.usuario_id, _instruccion_clasificar(),
            [Parte(datos("pregunta", _pregunta_con_opciones(pregunta)))], Clasificacion,
        )  # fmt: skip
    except ErrorIA:
        return Respuesta(pregunta, falta=True)
    campo, parametro = clasificacion.campo, clasificacion.parametro
    if clasificacion.formato == "dato" and campo and campos.es_campo_valido(campo, parametro):
        guardar_en_banco(ctx.base, norma, campo, parametro, ctx.ahora)
        return _desde_campo(pregunta, campo, parametro, ctx, Origen.BANCO)
    # Compuesta, en prosa o fuera del catálogo: el banco la guarda sin datos personales
    guardar_en_banco(ctx.base, norma, REDACTAR, None, ctx.ahora)
    return _para_redactar(pregunta)


def es_redactable(pregunta: Pregunta) -> bool:
    return pregunta.tipo in TIPOS_REDACTABLES and not pregunta.opciones


def _para_redactar(pregunta: Pregunta) -> Respuesta:
    """Las de texto van al redactor; las demás (opciones, número…) se le preguntan al usuario."""
    if es_redactable(pregunta):
        return Respuesta(pregunta, redactar=True)
    return Respuesta(pregunta, falta=True)


def _pregunta_con_opciones(pregunta: Pregunta) -> str:
    if not pregunta.opciones:
        return pregunta.texto
    opciones = "\n".join(f"{i}. {o}" for i, o in enumerate(pregunta.opciones))
    return f"{pregunta.texto}\nOpciones:\n{opciones}"


# --- redactor por formulario ------------------------------------------------------------


@dataclass
class Redactada:
    """Lo que devolvió el redactor para una pregunta: la respuesta o los datos que faltan."""

    valor: str | None = None
    faltan: list[DatoFaltante] = field(default_factory=list)


def recortar_a_limite(texto: str, maximo: int | None) -> str:
    """Corta en el último fin de frase dentro del límite, o en el último espacio si no hay."""
    if not maximo or len(texto) <= maximo:
        return texto
    corte = texto[:maximo]
    fin = max(corte.rfind("."), corte.rfind("!"), corte.rfind("?"))
    if fin > 0:
        return corte[: fin + 1]
    espacio = texto[: maximo + 1].rfind(" ")  # una palabra que llega justo al límite cabe
    if espacio > 0:
        return corte[:espacio].rstrip(" ,;:")
    return corte


def datos_aprendidos(base: BaseAsistente, usuario_id: int) -> list[tuple[str, str]]:
    """(pregunta, respuesta) que dio el usuario, del más reciente al más viejo: todos los datos
    cortos y los 40 más recientes del formulario. Nunca van los de contacto."""
    pendientes = base.cx.execute(
        "SELECT pregunta_norm, pregunta, tipo, campo FROM pendientes_usuario "
        "WHERE usuario_id = ? ORDER BY id",
        (usuario_id,),
    ).fetchall()
    textos = {p["pregunta_norm"]: p["pregunta"] for p in pendientes}  # el último gana
    de_dato = {p["pregunta_norm"] for p in pendientes if p["tipo"] == "dato"}
    contacto = {p["pregunta_norm"] for p in pendientes if p["campo"] in CONTACTO}
    contacto |= {
        f["pregunta_norm"]
        for f in base.cx.execute("SELECT pregunta_norm, campo FROM banco_preguntas")
        if f["campo"] in CONTACTO
    }
    filas = base.cx.execute(
        "SELECT pregunta_norm, respuesta FROM respuestas_aprendidas WHERE usuario_id = ? "
        "ORDER BY actualizada DESC",
        (usuario_id,),
    ).fetchall()
    resultado, otros = [], 0
    for f in filas:
        norma = f["pregunta_norm"]
        if norma in contacto:
            continue
        if norma not in de_dato:
            if otros >= MAX_APRENDIDOS_IA:
                continue
            otros += 1
        resultado.append((textos.get(norma, norma), f["respuesta"]))
    return resultado


def _texto_aprendidos(aprendidos: list[tuple[str, str]]) -> str:
    lineas = [
        f"- {pregunta} → {'(prefiere no decirlo)' if respuesta == RESERVADO else respuesta}"
        for pregunta, respuesta in aprendidos
    ]
    return "\n".join(lineas) or "(ninguno)"


def _texto_preguntas(preguntas: list[Pregunta]) -> str:
    return "\n".join(
        f"{n}. {p.texto}" + (f" (máximo {p.maximo} caracteres)" if p.maximo else "")
        for n, p in enumerate(preguntas, 1)
    )


def _limpiar_faltantes(faltan: list[DatoFaltante]) -> list[DatoFaltante]:
    limpios = []
    for f in faltan:
        pregunta = " ".join(f.pregunta.split())
        if not pregunta:
            continue
        sugerencias: list[str] = []
        for s in f.sugerencias:
            s = " ".join(s.split())[:MAX_SUGERENCIA].strip()
            if s and s.casefold() not in {x.casefold() for x in sugerencias}:
                sugerencias.append(s)
        limpios.append(DatoFaltante(pregunta=pregunta, sugerencias=sugerencias[:4]))
    return limpios


async def redactar_formulario(
    preguntas: list[Pregunta], ctx: Contexto
) -> dict[int, Redactada] | None:
    """Redacta en una sola llamada todas las preguntas abiertas del formulario.

    Devuelve, por posición en ``preguntas``, la respuesta o los datos que faltan; las que la IA
    no devolvió no aparecen. None sin IA o si la IA falla (ClaveInvalida se propaga).
    """
    if not preguntas:
        return {}
    if not ctx.con_ia:
        return None
    try:
        redaccion = await ctx.cliente.generar(
            "responder", ctx.clave, ctx.usuario_id, INSTRUCCION_REDACTAR_FORMULARIO,
            [
                Parte(datos("perfil", json.dumps(ctx.datos.para_ia(), ensure_ascii=False))),
                Parte(datos("datos_del_usuario",
                            _texto_aprendidos(datos_aprendidos(ctx.base, ctx.usuario_id)))),
                Parte(datos("vacante", ctx.vacante)),
                Parte(datos("preguntas", _texto_preguntas(preguntas))),
            ],
            RedaccionFormulario,
        )  # fmt: skip
    except ClaveInvalida:
        raise
    except ErrorIA:
        return None
    resultado: dict[int, Redactada] = {}
    for r in redaccion.respuestas:
        posicion = r.indice - 1
        if not 0 <= posicion < len(preguntas) or posicion in resultado:
            continue  # número que no está en el formulario: se ignora
        valor = " ".join((r.respuesta or "").split()) or None
        if valor:
            valor = recortar_a_limite(valor, preguntas[posicion].maximo)
        resultado[posicion] = Redactada(valor, _limpiar_faltantes(r.faltan))
    return resultado


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
