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
from buscador_vacantes.asistente.cv_adaptado import tecnologias_del_perfil
from buscador_vacantes.asistente.datos import BaseAsistente
from buscador_vacantes.asistente.ia import ClaveInvalida, ClienteIA, ErrorIA, Parte, datos
from buscador_vacantes.asistente.tecnologias import diccionario
from buscador_vacantes.comun.config import RAIZ
from buscador_vacantes.comun.estado import a_texto
from buscador_vacantes.comun.normalizar import normalizar_texto

RUTA_BANCO = RAIZ / "assets" / "asistente" / "banco_preguntas.yaml"
REDACTAR = "redactar"  # campo del banco: la pregunta se redacta, no es un dato del catálogo
TIPOS_REDACTABLES = {"texto"}  # número, fecha, correo y teléfono nunca van al redactor
MAX_APRENDIDOS_IA = 40  # datos aprendidos de formulario (los más recientes) para el redactor
MAX_EJEMPLOS_ESTILO = 5  # respuestas del usuario que el redactor de Máximo imita en tono
MIN_EJEMPLO_ESTILO = 60  # una respuesta más corta que esto no enseña estilo
LARGA_DESDE = 300  # caracteres pedidos desde los que una respuesta cuenta como larga
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
    # Del esquema ampliado de la extensión 1.2 (la 1.1.x no los manda)
    ayuda: str | None = None  # texto de ayuda del campo (aria-describedby)
    autocomplete: str | None = None  # atributo autocomplete, si lo tiene
    accept: str | None = None  # tipos de archivo que acepta un campo de archivo
    idioma: str | None = None  # lang del formulario o el detectado por la extensión
    busqueda: bool = False  # lista demasiado larga para leerla: se escribe el valor y se elige
    # Lo que la receta del sitio dice de este campo: «campo», «campo:parámetro» o «redactar»
    campo_receta: str | None = None


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
    """Carga las preguntas sembradas que falten y corrige las ya sembradas cuyo campo cambió.
    Devuelve cuántas se agregaron."""
    agregadas = 0
    with base.transaccion() as cx:
        for item in semilla():
            cx.execute(
                "UPDATE banco_preguntas SET campo = ?, parametro = ? WHERE pregunta_norm = ? "
                "AND origen = 'semilla' AND (campo != ? OR parametro IS NOT ?)",
                (
                    item["campo"],
                    item.get("parametro"),
                    normalizar_pregunta(item["pregunta"]),
                    item["campo"],
                    item.get("parametro"),
                ),
            )
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


# --- idioma del formulario ----------------------------------------------------------------

IDIOMAS = {"es": "español", "en": "inglés", "pt": "portugués"}
# Palabras frecuentes de las etiquetas, sin las que se escriben igual en dos idiomas («para»,
# «de», «salarial», «experiencia»…)
_PALABRAS_IDIOMA = {
    "es": set(
        "el la los las tu tus cual cuales una nombre apellido apellidos correo telefono celular "
        "ciudad tienes estas puedes cuanto cuanta donde cuando aspiracion disponibilidad estudias "
        "hoja vida cuentas eres porque quieres".split()
    ),
    "en": set(
        "the you your are is do does have what why how please tell about first last name years "
        "of to and with for in work upload resume cover letter current company describe salary "
        "expected authorized legally hear opportunity country city phone number address "
        "available background".split()
    ),
    "pt": set(
        "voce seu sua seus suas qual quais nome sobrenome telefone cidade tem trabalho trabalhar "
        "pretensao uma nao curriculo onde quando disponibilidade formacao estudando sao "
        "obrigatorio".split()
    ),
}  # fmt: skip


def _idioma_declarado(codigo: str | None) -> str | None:
    base = (codigo or "").strip().lower()[:2]
    return base if base in IDIOMAS else None


def detectar_idioma(preguntas: list[Pregunta], declarado: str | None = None) -> str:
    """Idioma del formulario: es, en o pt.

    La extensión informa el `lang` de la página, pero muchos sitios declaran `en` aunque estén en
    español; por eso se cuentan las palabras frecuentes de cada idioma en las etiquetas, las
    ayudas y las opciones. El declarado manda si las palabras no dicen claramente otra cosa.
    """
    declaradas = [_idioma_declarado(declarado)] + [_idioma_declarado(p.idioma) for p in preguntas]
    declaradas = [d for d in declaradas if d]
    declarado = max(set(declaradas), key=declaradas.count) if declaradas else None
    palabras: list[str] = []
    for p in preguntas:
        textos = [p.texto, p.ayuda or "", *p.opciones]
        palabras += re.findall(r"[a-z]+", normalizar_texto(" ".join(textos)))
    puntos = {
        idioma: sum(1 for w in palabras if w in lista) for idioma, lista in _PALABRAS_IDIOMA.items()
    }
    ordenados = sorted(puntos.items(), key=lambda x: x[1], reverse=True)
    (mejor, mejor_puntos), (_, segundo_puntos) = ordenados[0], ordenados[1]
    if mejor_puntos > segundo_puntos and mejor_puntos >= (2 if declarado else 1):
        return mejor
    return declarado or "es"


_SI_NO = {"Sí": {"en": "Yes", "pt": "Sim"}, "No": {"pt": "Não"}}


def _en_idioma(valor: str, idioma: str) -> str:
    """«Sí»/«No» como texto libre en el idioma del formulario; lo demás va como está."""
    return _SI_NO.get(valor, {}).get(idioma, valor)


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
    opcion: int | None = Field(None, description="índice de la opción elegida, si hay opciones")
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
    "- Escribe en primera persona, en el idioma indicado en «idioma» (los datos del usuario "
    "pueden estar en otro idioma: tradúcelos sin cambiar su contenido), con tono natural y "
    "profesional, sin muletillas de plantilla («Me apasiona…», «Soy una persona "
    "proactiva…») y sin copiar el CV literalmente.\n"
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
    "- Si la pregunta dice «máximo N caracteres», la respuesta no lo supera.\n"
    "- Si la pregunta trae opciones, no redactes: devuelve en opcion el número de la que "
    "corresponde según los datos y deja respuesta=null; si los datos no alcanzan para elegir "
    "con verdad, pide el dato en faltan."
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
    plataforma: str | None = None  # de dónde vino la vacante («¿cómo te enteraste?»)
    idioma: str | None = None  # es | en | pt del formulario; None: se deduce de las preguntas
    # Calidad del nivel Máximo (ver `NivelIA`); en Ahorro y Normal quedan apagadas
    requisitos_en_redactor: bool = False
    ejemplos_estilo: bool = False
    doble_redaccion: bool = False
    revisor_final: bool = False
    requisitos: list[str] = field(default_factory=list)  # lo que pide la vacante
    revisadas: int = 0  # respuestas que el revisor final cambió en esta pasada
    nivel: str = "normal"  # nivel de IA efectivo de la postulación (ahorro | normal | maximo)
    clasificar_preguntas: bool = True  # False (Ahorro): las preguntas nuevas van a la card

    @property
    def con_ia(self) -> bool:
        return self.cliente is not None and bool(self.clave)


_MONEDA = re.compile(r"moneda|currency|moeda")
_DOLARES = re.compile(r"\busd\b|dolar|dollar")


def _con_moneda(valor: str, moneda: str) -> str:
    """«2500000» → «COP 2.500.000»; un valor que ya trae formato solo recibe la moneda."""
    limpio = re.sub(r"[.,\s$]", "", valor)
    if limpio.isdigit():
        valor = f"{int(limpio):,}".replace(",", ".")
    return f"{moneda} {valor}"


def _desde_campo(pregunta, campo, parametro, ctx: Contexto, origen: Origen) -> Respuesta:
    norma = normalizar_pregunta(pregunta.texto)
    if campo == "salario" and _DOLARES.search(norma):
        campo = "salario_usd"  # la cifra en pesos nunca va a un campo que pide dólares
    clave = campos.clave_cuestionario(campo, parametro)
    if campo == "fuente_vacante":  # la plataforma de la vacante: no se le pregunta al usuario
        valor = campos.nombre_fuente(ctx.plataforma)
    else:
        valor = ctx.datos.valor(campo, parametro)
    if valor is None:
        return Respuesta(pregunta, campo=clave, falta=True)
    if pregunta.opciones:
        indice = elegir_opcion(valor, pregunta.opciones)
        if indice is None:  # el dato existe pero no calza con las opciones: elige el redactor
            return Respuesta(pregunta, campo=clave, redactar=True)
        return Respuesta(pregunta, opcion=indice, origen=origen, campo=clave)
    if campo in ("salario", "salario_usd"):
        pedida = _MONEDA.search(f"{norma} {normalizar_texto(pregunta.ayuda)}")
        if pregunta.tipo != "numero" and pedida:  # «Please include currency»
            valor = _con_moneda(valor, "USD" if campo == "salario_usd" else "COP")
    else:
        valor = _en_idioma(valor, ctx.idioma or detectar_idioma([pregunta]))
    return Respuesta(pregunta, valor=valor, origen=origen, campo=clave)


# Atributo autocomplete (su último término) → campo del catálogo
_AUTOCOMPLETE = {
    "given-name": "nombre_pila",
    "family-name": "apellido",
    "name": "nombre",
    "email": "correo",
    "tel": "telefono",
    "tel-national": "telefono",
    "country": "pais",
    "country-name": "pais",
    "address-level2": "ciudad",
}
# Términos del atributo name o id (en snake_case, entre guiones bajos) → campo
_TOKENS_NOMBRE = (
    (("first_name", "firstname", "given_name", "givenname", "fname", "primer_nombre"),
     "nombre_pila"),
    (("last_name", "lastname", "family_name", "familyname", "surname", "lname", "apellido",
      "apellidos"), "apellido"),
    (("systemfield_name", "full_name", "fullname", "nombre_completo"), "nombre"),
    (("linkedin", "linkedin_url", "linkedin_profile"), "enlace_linkedin"),
    (("country", "pais"), "pais"),
)  # fmt: skip
_NO_ES_PAIS = ("_code_", "_codigo_", "_dial_", "_prefix_", "_phone_", "_tel_")


def _tokens_nombre(nombre: str) -> str:
    """«jobApplication[firstName]» → «_job_application_first_name_»."""
    snake = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", nombre).lower()
    return "_" + re.sub(r"[^a-z0-9]+", "_", snake).strip("_") + "_"


def _desde_tipo(pregunta: Pregunta) -> tuple[str, None] | None:
    """Campos estándar identificables sin IA por su tipo, su autocomplete o su name/id."""
    nombre = normalizar_texto(pregunta.nombre or "")
    if pregunta.tipo == "correo" or "email" in nombre or "correo" in nombre:
        return "correo", None
    if pregunta.tipo == "telefono" or any(t in nombre for t in ("phone", "telefono", "celular")):
        return "telefono", None
    terminos = (pregunta.autocomplete or "").lower().split()
    if terminos and (campo := _AUTOCOMPLETE.get(terminos[-1])):
        return campo, None
    tokens = _tokens_nombre(pregunta.nombre or "")
    for lista, campo in _TOKENS_NOMBRE:
        if any(f"_{t}_" in tokens for t in lista):
            if campo == "pais" and any(x in tokens for x in _NO_ES_PAIS):
                continue
            return campo, None
    return None


# Autorizaciones y aceptaciones (tratamiento de datos, términos): las decide el usuario. No se
# confunde con «¿tienes autorización para trabajar?», que es un dato del perfil.
_CONSENTIMIENTO = re.compile(
    r"tratamiento de (?:tus |sus |mis )?datos|datos personales|habeas data|terminos y condiciones"
    r"|politicas? de (?:privacidad|tratamiento)|(?:declaracion|aviso) de privacidad"
    r"|consentimiento|\bautoriz(?:o|as|a|amos)\b"
    # inglés y portugués
    r"|privacy (?:policy|notice|statement)|terms (?:and|&) conditions|terms of (?:use|service)"
    r"|\bconsent\b|\bi (?:agree|accept|authori[sz]e)\b|\bgdpr\b|politica de privacidade"
    r"|termos e condicoes|\bconcordo\b|\baceito\b"
)


def es_consentimiento(norma: str) -> bool:
    """True si la pregunta (ya normalizada) pide autorizar o aceptar algo."""
    return bool(_CONSENTIMIENTO.search(norma))


# «¿Tienes autorización para trabajar en Colombia?»: un dato del perfil, una vez por país
_TRABAJO = re.compile(r"\b(?:work|working|trabajar|trabajo|trabalhar|trabalho)\b")
_AUTORIZACION = re.compile(
    r"authori[sz]ed|authori[sz]ation|eligible|legally|work (?:permit|visa)|permit|"
    r"autorizad[oa]|autorizacion|autorizacao|legalmente|permiso|permissao"
)
_PATROCINIO = re.compile(r"sponsor|patrocin|requiere visa|require.*visa")  # lo contrario
_PAISES = {
    "colombia": "Colombia",
    "estados unidos": "Estados Unidos", "united states": "Estados Unidos", "usa": "Estados Unidos",
    "u s": "Estados Unidos", "eeuu": "Estados Unidos",
    "mexico": "México", "argentina": "Argentina", "chile": "Chile", "peru": "Perú",
    "ecuador": "Ecuador", "venezuela": "Venezuela", "panama": "Panamá",
    "espana": "España", "spain": "España", "canada": "Canadá",
    "brasil": "Brasil", "brazil": "Brasil",
    "reino unido": "Reino Unido", "united kingdom": "Reino Unido",
    "alemania": "Alemania", "germany": "Alemania",
}  # fmt: skip


def autorizacion_trabajo(norma: str) -> tuple[str, str] | None:
    """(campo, país) si la pregunta (normalizada) pide autorización para trabajar en un país
    conocido. «Requiere patrocinio» es la pregunta contraria y no se contesta con este dato."""
    if _PATROCINIO.search(norma) or not _TRABAJO.search(norma) or not _AUTORIZACION.search(norma):
        return None
    hallados = [
        (m.start(), pais)
        for alias, pais in _PAISES.items()
        for m in re.finditer(rf"\b{re.escape(alias)}\b", norma)
    ]
    if not hallados:
        return None
    return "autorizacion_trabajo", max(hallados)[1]  # el país suele ir al final de la frase


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
    if trabajo := autorizacion_trabajo(norma):
        return _desde_campo(pregunta, *trabajo, ctx, Origen.PERFIL)
    if desde_receta := _desde_receta(pregunta, ctx):
        return desde_receta
    if not ctx.con_ia or not ctx.clasificar_preguntas:
        return Respuesta(pregunta, falta=True)
    try:
        clasificacion = await ctx.cliente.generar(
            "clasificar_pregunta", ctx.clave, ctx.usuario_id, _instruccion_clasificar(),
            [Parte(datos("pregunta", _pregunta_con_opciones(pregunta)))], Clasificacion,
            nivel=ctx.nivel,
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


# Qué documento pide un campo de archivo, por su etiqueta (las mismas reglas que la extensión;
# lo que no calza queda para el CV). El orden importa: «carta» antes que «cv».
_TIPOS_ARCHIVO = (
    ("certificado_notas", re.compile(
        r"transcript|certificado de notas|calificaciones|notas academicas|historico escolar")),
    ("carta", re.compile(r"cover letter|carta de presentacion|carta")),
    ("portafolio", re.compile(r"portfolio|portafolio")),
    ("cv", re.compile(r"resume|\bcv\b|curriculum|curriculo|hoja de vida")),
)  # fmt: skip


def tipo_archivo(pregunta: Pregunta) -> str:
    """Tipo de documento de un campo de archivo: certificado_notas, carta, portafolio o cv."""
    texto = normalizar_texto(f"{pregunta.texto} {pregunta.nombre or ''}")
    for tipo, patron in _TIPOS_ARCHIVO:
        if patron.search(texto):
            return tipo
    return "cv"


def _desde_receta(pregunta: Pregunta, ctx: Contexto) -> Respuesta | None:
    """Lo que una receta del sitio ya sabe de este campo, sin clasificarlo con la IA. Solo
    vale un campo del catálogo: lo demás se trata como si la receta no existiera."""
    if not pregunta.campo_receta:
        return None
    campo, _, parametro = pregunta.campo_receta.partition(":")
    if campo == REDACTAR:
        return _para_redactar(pregunta)
    if campos.es_campo_valido(campo, parametro or None):
        return _desde_campo(pregunta, campo, parametro or None, ctx, Origen.PERFIL)
    return None


def es_redactable(pregunta: Pregunta) -> bool:
    """Texto libre que se redacta, o una pregunta con opciones en la que la IA elige una."""
    return bool(pregunta.opciones) or pregunta.tipo in TIPOS_REDACTABLES


def _para_redactar(pregunta: Pregunta) -> Respuesta:
    """Texto y opciones van al redactor; número, fecha, correo y teléfono, al usuario."""
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
    opcion: int | None = None  # pregunta con opciones: índice válido de la elegida
    alternativas: list[str] = field(default_factory=list)  # doble redacción: la otra versión
    revisada: bool = False  # el revisor final la corrigió, la cambió por otra versión o la frenó


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
    lineas = []
    for n, p in enumerate(preguntas, 1):
        if p.opciones:
            opciones = " · ".join(f"{i}) {o}" for i, o in enumerate(p.opciones))
            lineas.append(f"{n}. {p.texto} [opciones: {opciones}]")
        else:
            limite = f" (máximo {p.maximo} caracteres)" if p.maximo else ""
            lineas.append(f"{n}. {p.texto}{limite}")
        if p.ayuda:
            lineas[-1] += f" [ayuda: {' '.join(p.ayuda.split())[:200]}]"
    return "\n".join(lineas)


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


INSTRUCCION_REQUISITOS_VACANTE = (
    "\n- En «requisitos_de_la_vacante» está lo que pide la vacante: destaca los que el perfil "
    "cumple, apoyándote en el perfil. NUNCA afirmes ni insinúes que dominas, usas o tienes un "
    "requisito que el perfil, el cuestionario y los datos del usuario no mencionan; si la "
    "pregunta lo exige, dilo con honestidad o pide el dato en faltan."
)
INSTRUCCION_ESTILO_USUARIO = (
    "\n- En «ejemplos_de_estilo» hay respuestas que el usuario escribió o corrigió: imita su "
    "tono, su longitud y su manera de escribir. Son ejemplos de estilo y NUNCA datos: no tomes "
    "de ahí hechos, cifras ni nombres que no estén en el perfil o en los datos del usuario."
)
INSTRUCCION_SEGUNDA_VERSION = (
    "\n- Esta es una SEGUNDA versión de las mismas respuestas: dale a cada una otra apertura y "
    "otro orden de ideas que a la primera, con las mismas reglas y sin inventar nada."
)

_PREGUNTA_LARGA = re.compile(
    r"por que (?:te interesa|quieres|deseas|te gustaria)|porque te interesa|motivacion|motivo|"
    r"why (?:are you interested|do you want|this (?:role|position|job))|motivation|"
    r"experiencia|experience|cuentanos|tell us about|describe|descri[bp]e"
)


def es_larga(pregunta: Pregunta) -> bool:
    """Motivación, experiencia o más de 300 caracteres pedidos: la que recibe doble redacción."""
    return (pregunta.maximo or 0) > LARGA_DESDE or bool(
        _PREGUNTA_LARGA.search(normalizar_pregunta(pregunta.texto))
    )


def ejemplos_de_estilo(base: BaseAsistente, usuario_id: int) -> list[tuple[str, str]]:
    """Hasta 5 respuestas largas que el usuario escribió o corrigió, de la más reciente a la más
    vieja: sirven de ejemplo de tono, nunca de datos."""
    ejemplos = []
    for pregunta, respuesta in datos_aprendidos(base, usuario_id):
        if respuesta != RESERVADO and len(respuesta) >= MIN_EJEMPLO_ESTILO:
            ejemplos.append((pregunta, respuesta))
    return ejemplos[:MAX_EJEMPLOS_ESTILO]


def requisitos_ajenos(ctx: Contexto) -> set[str]:
    """Tecnologías que pide la vacante y que ni el perfil, ni el cuestionario ni lo que el usuario
    respondió mencionan: la IA no puede afirmarlas en una respuesta (nivel Máximo)."""
    if not (ctx.requisitos_en_redactor and ctx.requisitos):
        return set()
    dicc = diccionario()
    propias = tecnologias_del_perfil(ctx.datos.perfil, dicc)
    textos = [*ctx.datos.cuestionario.values()]
    textos += [r for _, r in datos_aprendidos(ctx.base, ctx.usuario_id)]
    for texto in textos:
        propias.update(dicc.buscar(str(texto)))
    pedidas: set[str] = set()
    for requisito in ctx.requisitos:
        pedidas.update(dicc.buscar(requisito))
        if canonica := dicc.canonica(requisito):
            pedidas.add(canonica)
    return pedidas - propias


def afirma_requisito_ajeno(texto: str, ajenos: set[str]) -> bool:
    return bool(ajenos) and any(t in ajenos for t in diccionario().buscar(texto))


def _instruccion_redactor(ctx: Contexto, *, segunda: bool = False) -> str:
    instruccion = INSTRUCCION_REDACTAR_FORMULARIO
    if ctx.requisitos_en_redactor and ctx.requisitos:
        instruccion += INSTRUCCION_REQUISITOS_VACANTE
    if ctx.ejemplos_estilo and ejemplos_de_estilo(ctx.base, ctx.usuario_id):
        instruccion += INSTRUCCION_ESTILO_USUARIO
    return instruccion + (INSTRUCCION_SEGUNDA_VERSION if segunda else "")


def _partes_datos(ctx: Contexto, idioma: str) -> list[Parte]:
    """Lo que ven el redactor y el revisor: idioma, perfil, datos del usuario y vacante."""
    partes = [
        Parte(datos("idioma", IDIOMAS.get(idioma, IDIOMAS["es"]))),
        Parte(datos("perfil", json.dumps(ctx.datos.para_ia(), ensure_ascii=False))),
        Parte(datos("datos_del_usuario",
                    _texto_aprendidos(datos_aprendidos(ctx.base, ctx.usuario_id)))),
        Parte(datos("vacante", ctx.vacante)),
    ]  # fmt: skip
    if ctx.requisitos_en_redactor and ctx.requisitos:
        requisitos = "\n".join(f"- {r}" for r in ctx.requisitos)
        partes.append(Parte(datos("requisitos_de_la_vacante", requisitos)))
    return partes


def _partes_redactor(preguntas: list[Pregunta], ctx: Contexto, idioma: str) -> list[Parte]:
    partes = _partes_datos(ctx, idioma)
    if ctx.ejemplos_estilo and (ejemplos := ejemplos_de_estilo(ctx.base, ctx.usuario_id)):
        partes.append(Parte(datos("ejemplos_de_estilo", "\n".join(
            f"- {p} → {r}" for p, r in ejemplos))))  # fmt: skip
    partes.append(Parte(datos("preguntas", _texto_preguntas(preguntas))))
    return partes


def _texto_redactado(r: RespuestaRedactada, pregunta: Pregunta) -> str | None:
    valor = " ".join((r.respuesta or "").split()) or None
    return recortar_a_limite(valor, pregunta.maximo) if valor else None


async def redactar_formulario(
    preguntas: list[Pregunta], ctx: Contexto
) -> dict[int, Redactada] | None:
    """Redacta en una sola llamada todas las preguntas abiertas del formulario.

    Devuelve, por posición en ``preguntas``, la respuesta o los datos que faltan; las que la IA
    no devolvió no aparecen. None sin IA o si la IA falla (ClaveInvalida se propaga).

    En Máximo, las respuestas largas (``es_larga``) reciben una segunda versión (``alternativas``)
    y ninguna respuesta afirma un requisito de la vacante que el usuario no cumple: la que lo
    hace se pregunta al usuario en vez de enviarse.
    """
    if not preguntas:
        return {}
    if not ctx.con_ia:
        return None
    idioma = ctx.idioma or detectar_idioma(preguntas)
    try:
        redaccion = await ctx.cliente.generar(
            "responder", ctx.clave, ctx.usuario_id, _instruccion_redactor(ctx),
            _partes_redactor(preguntas, ctx, idioma), RedaccionFormulario, nivel=ctx.nivel,
        )  # fmt: skip
    except ClaveInvalida:
        raise
    except ErrorIA:
        return None
    ajenos = requisitos_ajenos(ctx)
    resultado: dict[int, Redactada] = {}
    for r in redaccion.respuestas:
        posicion = r.indice - 1
        if not 0 <= posicion < len(preguntas) or posicion in resultado:
            continue  # número que no está en el formulario: se ignora
        pregunta = preguntas[posicion]
        faltan = _limpiar_faltantes(r.faltan)
        if pregunta.opciones:  # solo vale una opción del portal, nunca texto inventado
            valida = r.opcion is not None and 0 <= r.opcion < len(pregunta.opciones)
            resultado[posicion] = Redactada(faltan=faltan, opcion=r.opcion if valida else None)
            continue
        valor = _texto_redactado(r, pregunta)
        if valor and afirma_requisito_ajeno(valor, ajenos):
            valor = None  # un requisito que no cumple: no se envía, se pregunta al usuario
        resultado[posicion] = Redactada(valor, faltan)
    if ctx.doble_redaccion:
        await _segunda_version(preguntas, resultado, ctx, idioma, ajenos)
    return resultado


async def _segunda_version(
    preguntas: list[Pregunta],
    resultado: dict[int, Redactada],
    ctx: Contexto,
    idioma: str,
    ajenos: set[str],
) -> None:
    """Una llamada más con solo las respuestas largas ya redactadas; la otra versión queda en
    ``alternativas`` para que el revisor final elija. Si falla, queda la primera."""
    largas = [i for i, r in sorted(resultado.items()) if r.valor and es_larga(preguntas[i])]
    if not largas:
        return
    try:
        segunda = await ctx.cliente.generar(
            "responder", ctx.clave, ctx.usuario_id, _instruccion_redactor(ctx, segunda=True),
            _partes_redactor([preguntas[i] for i in largas], ctx, idioma),
            RedaccionFormulario, nivel=ctx.nivel,
        )  # fmt: skip
    except ClaveInvalida:
        raise
    except ErrorIA:
        return
    for r in segunda.respuestas:
        if not 1 <= r.indice <= len(largas):
            continue
        posicion = largas[r.indice - 1]
        texto = _texto_redactado(r, preguntas[posicion])
        if texto and texto != resultado[posicion].valor:
            if not afirma_requisito_ajeno(texto, ajenos):
                resultado[posicion].alternativas = [texto]


# --- revisor final (nivel Máximo) ---------------------------------------------------------


class VeredictoRespuesta(BaseModel):
    indice: int = Field(description="número de la respuesta")
    veredicto: Literal["ok", "elegir", "corregir", "preguntar"]
    eleccion: int | None = Field(None, description="elegir: versión (1 es la primera)")
    texto: str | None = Field(None, description="corregir: el texto nuevo completo")
    faltan: list[DatoFaltante] = Field(default_factory=list, description="preguntar: el dato")


class RevisionFormulario(BaseModel):
    veredictos: list[VeredictoRespuesta] = Field(default_factory=list)


INSTRUCCION_REVISAR_RESPUESTAS = (
    "Eres el revisor final de las respuestas que redactó un asistente por un candidato a un "
    "formulario de postulación. Recibes, numeradas, cada pregunta con su límite de caracteres, "
    "su respuesta y, si hay, una segunda versión; además el idioma del formulario, el perfil y "
    "los datos del usuario. Por cada respuesta devuelve su número en indice y un veredicto:\n"
    "- ok: responde la pregunta, está en el idioma del formulario, cabe en el límite y todo "
    "lo que afirma está en el perfil o en los datos del usuario.\n"
    "- elegir: hay dos versiones y la mejor es la otra; pon en eleccion su número (1 es la "
    "primera, 2 la segunda).\n"
    "- corregir: la respuesta está en otro idioma, se pasa del límite, no responde lo que se "
    "pregunta o suena a plantilla; pon en texto la versión corregida completa, SOLO con datos "
    "del perfil y del usuario.\n"
    "- preguntar: la respuesta afirma algo que el perfil contradice o no respalda (años de "
    "experiencia, un título, una herramienta, una cifra) y no puedes corregirla con los datos "
    "que tienes; pon en faltan una pregunta corta en segunda persona con 2 a 4 sugerencias.\n"
    "Nunca agregues datos que no estén en el perfil, en el cuestionario o en los datos del "
    "usuario. Nunca afirmes un requisito de «requisitos_de_la_vacante» que el perfil no "
    "mencione. Si una respuesta está bien, di ok."
)


def _texto_para_revisar(candidatas: list[tuple[int, Pregunta, Redactada]]) -> str:
    lineas = []
    for n, (_, pregunta, redactada) in enumerate(candidatas, 1):
        limite = f" (máximo {pregunta.maximo} caracteres)" if pregunta.maximo else ""
        lineas.append(f"{n}. Pregunta: {pregunta.texto}{limite}")
        lineas.append(f"   Respuesta: {redactada.valor}")
        for extra in redactada.alternativas:
            lineas.append(f"   Segunda versión: {extra}")
    return "\n".join(lineas)


async def revisar_formulario(
    preguntas: list[Pregunta], redactadas: dict[int, Redactada], ctx: Contexto
) -> int:
    """Revisor final (tarea ``revisar_respuestas``): corrige en el lugar las ``redactadas`` y
    devuelve cuántas cambió (corregidas, cambiadas por la otra versión o frenadas con una
    pregunta). Solo ve respuestas de texto que redactó la IA en esta pasada: los datos simples,
    las opciones, los consentimientos y lo que escribió el usuario nunca le llegan. Si la IA
    falla, las respuestas quedan como están; ClaveInvalida se propaga."""
    candidatas = [
        (i, preguntas[i], r) for i, r in sorted(redactadas.items())
        if r.valor and not r.faltan and r.opcion is None and not preguntas[i].opciones
    ]  # fmt: skip
    if not candidatas or not ctx.con_ia:
        return 0
    idioma = ctx.idioma or detectar_idioma(preguntas)
    partes = _partes_datos(ctx, idioma)  # los mismos datos que el redactor
    partes.append(Parte(datos("respuestas", _texto_para_revisar(candidatas))))
    try:
        revision = await ctx.cliente.generar(
            "revisar_respuestas", ctx.clave, ctx.usuario_id, INSTRUCCION_REVISAR_RESPUESTAS,
            partes, RevisionFormulario, nivel=ctx.nivel,
        )  # fmt: skip
    except ClaveInvalida:
        raise
    except ErrorIA:
        return 0
    ajenos = requisitos_ajenos(ctx)
    cambiadas = 0
    vistos: set[int] = set()
    for v in revision.veredictos:
        if not 1 <= v.indice <= len(candidatas) or v.indice in vistos:
            continue
        vistos.add(v.indice)
        _, pregunta, redactada = candidatas[v.indice - 1]
        versiones = [redactada.valor, *redactada.alternativas]
        if v.veredicto == "elegir":
            if v.eleccion is not None and 2 <= v.eleccion <= len(versiones):
                redactada.valor = versiones[v.eleccion - 1]
                redactada.alternativas = [versiones[0]]
                redactada.revisada = True
                cambiadas += 1
        elif v.veredicto == "corregir":
            texto = " ".join((v.texto or "").split())
            texto = recortar_a_limite(texto, pregunta.maximo) if texto else ""
            if texto and texto != redactada.valor and not afirma_requisito_ajeno(texto, ajenos):
                redactada.valor = texto
                redactada.revisada = True
                cambiadas += 1
        elif v.veredicto == "preguntar":
            faltan = _limpiar_faltantes(v.faltan)
            if faltan:
                redactada.valor, redactada.faltan, redactada.revisada = None, faltan, True
                cambiadas += 1
    return cambiadas


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
