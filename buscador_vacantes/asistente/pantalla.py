"""Decisión de cada pantalla del bucle genérico (POST /postulaciones/{id}/pantalla).

La extensión lee una pantalla y manda su esquema, sus botones y un resumen sin valores. Aquí se
decide qué hacer: las respuestas salen de `respuestas.resolver` (y el redactor), el botón de las
reglas de la extensión y, solo si las reglas dudan, de un árbitro con IA. El árbitro es un punto de
enlace (`Arbitrar`): responde con una lista cerrada de acciones y cada índice se valida contra los
botones recibidos, así que nunca pulsa algo que la extensión no haya leído ni un botón `nunca`.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from buscador_vacantes.asistente.recetas import BotonReceta, clave_campo
from buscador_vacantes.asistente.respuestas import Pregunta
from buscador_vacantes.comun.normalizar import normalizar_texto

MS_ESPERA = 1500  # pausa que se pide cuando el árbitro decide esperar
MAX_TEXTO_EXITO = 200


# --- lo que manda la extensión ----------------------------------------------------------------


class Boton(BaseModel):
    indice: int = Field(ge=0)
    texto: str = Field("", max_length=200)
    clase: str | None = Field(None, max_length=20)  # avanzar | enviar | nunca | intermedia | null
    oauth: bool = False
    tipo: str = Field("button", max_length=20)
    en_contenedor: bool = False
    selector: Any | None = None  # selector estable que calculó la extensión (para recetas)


class Sugerido(BaseModel):
    indice: int = Field(ge=0)
    accion: str = Field(max_length=10)  # avanzar | enviar


class ElementoResumen(BaseModel):
    indice: int = Field(ge=0)
    rol: str = Field("", max_length=40)
    texto: str = Field("", max_length=200)
    tipo: str | None = Field(None, max_length=20)
    en_contenedor: bool = False
    cookies: bool = False


class Resumen(BaseModel):
    """Lo visible e interactivo de la página, sin valores de campos."""

    elementos: list[ElementoResumen] = Field(default_factory=list, max_length=150)
    encabezados: list[str] = Field(default_factory=list, max_length=30)
    avisos: list[str] = Field(default_factory=list, max_length=30)


class Exito(BaseModel):
    senal: str | None = Field(None, max_length=20)
    texto: str | None = Field(None, max_length=500)


# --- lo que entiende el árbitro ----------------------------------------------------------------


ACCIONES_PAGINA = ("avanzar", "enviar", "esperar", "elegir")
ACCIONES_REPARACION = (*ACCIONES_PAGINA, "cerrar_modal")
MAX_ACCIONES = 5
MAX_OPCION = 100
MAX_MOTIVO = 300


def _solo_conocidas(acciones: Any, conocidas: tuple[str, ...]) -> Any:
    """Descarta, antes de validar, las acciones fuera de la lista cerrada o mal formadas: una
    acción inventada no tumba la decisión entera, solo se ignora."""
    if not isinstance(acciones, list):
        return []
    validas = []
    for a in acciones:
        if isinstance(a, BaseModel):  # una acción ya construida
            a = a.model_dump()
        if not isinstance(a, dict) or a.get("accion") not in conocidas:
            continue
        indice, opcion = a.get("indice"), a.get("opcion")
        if indice is not None and (not isinstance(indice, int) or isinstance(indice, bool)):
            continue
        if indice is not None and indice < 0:
            continue
        if opcion is not None and not isinstance(opcion, str):
            continue
        validas.append({**a, "opcion": opcion[:MAX_OPCION] if opcion else None})
    return validas[:MAX_ACCIONES]


def _recortar(texto: Any, maximo: int) -> Any:
    return " ".join(texto.split())[:maximo] if isinstance(texto, str) else ""


class AccionPagina(BaseModel):
    """Una acción de la lista cerrada. `indice` señala un botón (`avanzar`, `enviar`) o un
    elemento del resumen (`elegir`); `esperar` no lleva índice. `opcion` es el texto de la
    opción que `elegir` marca en ese elemento."""

    accion: Literal["avanzar", "enviar", "esperar", "elegir"]
    indice: int | None = Field(None, ge=0)
    opcion: str | None = Field(None, max_length=MAX_OPCION)


class AccionReparacion(AccionPagina):
    accion: Literal["avanzar", "enviar", "esperar", "elegir", "cerrar_modal"]  # type: ignore[assignment]


class DecisionPagina(BaseModel):
    """Salida de la tarea `entender_pagina`. Los índices solo valen contra la pantalla enviada:
    ver `acciones_validas`."""

    clase: Literal["formulario", "intermedia", "exito", "barrera", "desconocida"]
    acciones: list[AccionPagina] = Field(default_factory=list, max_length=MAX_ACCIONES)
    motivo: str = Field("", max_length=MAX_MOTIVO)

    @field_validator("acciones", mode="before")
    @classmethod
    def _acciones_conocidas(cls, valor: Any) -> Any:
        return _solo_conocidas(valor, ACCIONES_PAGINA)

    @field_validator("motivo", mode="before")
    @classmethod
    def _motivo_corto(cls, valor: Any) -> Any:
        return _recortar(valor, MAX_MOTIVO)


class Reparacion(DecisionPagina):
    """Salida de la tarea `reparar_flujo`: lo mismo, con `cerrar_modal` y un diagnóstico corto
    para el dueño."""

    acciones: list[AccionReparacion] = Field(default_factory=list, max_length=MAX_ACCIONES)
    diagnostico: str = Field("", max_length=MAX_MOTIVO)

    @field_validator("acciones", mode="before")
    @classmethod
    def _acciones_conocidas(cls, valor: Any) -> Any:
        return _solo_conocidas(valor, ACCIONES_REPARACION)

    @field_validator("diagnostico", mode="before")
    @classmethod
    def _diagnostico_corto(cls, valor: Any) -> Any:
        return _recortar(valor, MAX_MOTIVO)


def acciones_validas(
    acciones: list[AccionPagina], botones: list[Boton], resumen: Resumen
) -> list[AccionPagina]:
    """Solo las acciones cuyo índice existe en la pantalla que se mandó: `avanzar` y `enviar`
    señalan un botón recibido; `elegir` (con la opción) y `cerrar_modal`, un elemento del
    resumen. Lo demás se descarta: nada se pulsa por un índice que la extensión no leyó."""
    de_botones = {b.indice for b in botones}
    de_resumen = {e.indice for e in resumen.elementos}
    validas = []
    for a in acciones:
        if a.accion == "esperar":
            ok = True
        elif a.accion in ("avanzar", "enviar"):
            ok = a.indice in de_botones
        elif a.accion == "elegir":
            ok = a.indice in de_resumen and bool((a.opcion or "").strip())
        else:  # cerrar_modal
            ok = a.indice in de_resumen
        if ok:
            validas.append(a)
    return validas


@dataclass
class Peticion:
    clase: str  # la que sugirieron las reglas de la extensión
    motivo: str | None
    idioma: str | None
    url: str
    preguntas: list[Pregunta]  # una por campo del esquema, en su orden
    botones: list[Boton]
    sugerido: Sugerido | None
    resumen: Resumen
    exito: Exito | None
    correccion: bool
    # El botón que la receta del sitio pulsó en esta pantalla; las reglas dudan y ella no
    boton_receta: BotonReceta | None = None

    @property
    def pide_archivo(self) -> bool:
        return any(p.tipo == "archivo" for p in self.preguntas)


@dataclass
class Consulta:
    """Todo lo que ve el árbitro de una pantalla: texto de la página, nunca valores del usuario."""

    peticion: Peticion


@dataclass
class Decision:
    esperar_usuario: bool = False
    respuestas: list[dict[str, Any]] = field(default_factory=list)
    cv: Path | None = None
    accion: dict[str, Any] | None = None
    # clave del campo → campo del catálogo o «redactar»; nunca valores (para la receta)
    mapeo: dict[str, str] = field(default_factory=dict)


Resolver = Callable[[list[Pregunta]], Awaitable[Any]]  # → ResultadoFormulario
Arbitrar = Callable[[Consulta], Awaitable[DecisionPagina | None]]  # None: sin IA o falló


# --- decisión ----------------------------------------------------------------------------------


def respuestas_de(preguntas: list[Pregunta], resultado: Any) -> list[dict[str, Any]]:
    """Respuestas por índice de campo; lo que falta y no es obligatorio se deja vacío."""
    respuestas = []
    for indice, pregunta in enumerate(preguntas):
        r = next((x for x in resultado.respuestas if x.pregunta is pregunta), None)
        if r is None or r.falta:
            continue
        respuestas.append({"indice": indice, "valor": r.valor, "opcion": r.opcion,
                           "origen": r.origen})  # fmt: skip
    return respuestas


def mapeo_de(preguntas: list[Pregunta], resultado: Any) -> dict[str, str]:
    """Qué dato del catálogo (o «redactar») se puso en cada campo respondido, por su clave."""
    mapeo = {}
    for pregunta in preguntas:
        r = next((x for x in resultado.respuestas if x.pregunta is pregunta), None)
        if r is None or r.falta or pregunta.tipo == "archivo":
            continue
        mapeo[clave_campo(pregunta.nombre, pregunta.texto)] = r.campo or "redactar"
    return mapeo


def _respaldo(motivo: str) -> Decision:
    return Decision(accion={"tipo": "respaldo", "motivo": motivo})


def _boton(botones: list[Boton], indice: int | None) -> Boton | None:
    return next((b for b in botones if b.indice == indice), None) if indice is not None else None


def _accion_boton(boton: Boton, pedida: str) -> dict[str, Any] | None:
    """La acción sobre un botón. Su clase manda sobre lo que pida quien decide: solo un botón
    `enviar` registra el envío, y uno `nunca` (u OAuth) no se pulsa."""
    if boton.clase == "nunca" or boton.oauth:
        return None
    tipo = {"enviar": "enviar", "avanzar": "avanzar", "intermedia": "avanzar"}.get(
        boton.clase or "", pedida
    )
    if tipo not in ("avanzar", "enviar"):
        return None
    return {"tipo": tipo, "indice": boton.indice}


def _por_reglas(peticion: Peticion) -> dict[str, Any] | None:
    """El botón que sugirieron las reglas, si existe y se puede pulsar; None: dudan."""
    if peticion.sugerido is None:
        return None
    boton = _boton(peticion.botones, peticion.sugerido.indice)
    return _accion_boton(boton, peticion.sugerido.accion) if boton else None


def _por_receta(peticion: Peticion) -> dict[str, Any] | None:
    """El botón de la receta del sitio, si sigue en la pantalla con el mismo texto. Su clase
    manda: uno `nunca` o de inicio de sesión con un tercero no se pulsa."""
    receta = peticion.boton_receta
    if receta is None or not receta.texto:
        return None
    texto = normalizar_texto(receta.texto)
    boton = next((b for b in peticion.botones if normalizar_texto(b.texto) == texto), None)
    if boton is None or boton.clase not in ("enviar", "avanzar", "intermedia"):
        return None  # sin la clase de las reglas, ni una receta decide que un clic envía
    return _accion_boton(boton, boton.clase)


def _por_arbitro(decision: DecisionPagina, peticion: Peticion) -> Decision:
    if decision.clase == "exito":
        texto = " ".join(decision.motivo.split())[:MAX_TEXTO_EXITO] or None
        return Decision(accion={"tipo": "exito", "texto": texto})
    if decision.clase == "barrera":
        return _respaldo("barrera")
    if decision.clase == "desconocida":
        return _respaldo("pantalla_desconocida")
    for accion in acciones_validas(decision.acciones, peticion.botones, peticion.resumen):
        if accion.accion == "esperar":
            return Decision(accion={"tipo": "esperar", "ms": MS_ESPERA})
        if accion.accion not in ("avanzar", "enviar"):
            continue  # elegir y cerrar_modal las ejecuta la reparación (6.2), no esta decisión
        boton = _boton(peticion.botones, accion.indice)
        elegida = _accion_boton(boton, accion.accion) if boton else None
        if elegida:
            return Decision(accion=elegida)
    return _respaldo("pantalla_desconocida")


async def decidir(
    peticion: Peticion,
    resolver: Resolver,
    arbitrar: Arbitrar | None,
    motivo_sin_arbitro: str = "tope_arbitro",
) -> Decision:
    """La decisión de una pantalla. `arbitrar` es None cuando no hay llamadas al árbitro: se
    agotó el tope (`tope_arbitro`) o el nivel de IA del usuario no las permite (`nivel_ahorro`)."""
    if peticion.clase == "exito":
        texto = peticion.exito.texto if peticion.exito else None
        return Decision(accion={"tipo": "exito", "texto": texto})
    if peticion.clase == "barrera":
        return _respaldo(peticion.motivo or "barrera")

    decision = Decision()
    if peticion.preguntas:
        resultado = await resolver(peticion.preguntas)
        if resultado.revisar or any(r.pregunta.obligatoria for r in resultado.faltan):
            return Decision(esperar_usuario=True)
        decision.respuestas = respuestas_de(peticion.preguntas, resultado)
        decision.mapeo = mapeo_de(peticion.preguntas, resultado)
        if peticion.pide_archivo:
            decision.cv = resultado.cv

    accion = _por_reglas(peticion) or _por_receta(peticion)
    if accion is not None:
        decision.accion = accion
        return decision
    if arbitrar is None:
        return _respaldo(motivo_sin_arbitro)
    veredicto = await arbitrar(Consulta(peticion))
    if veredicto is None:
        return _respaldo("sin_ia")
    elegido = _por_arbitro(veredicto, peticion)
    decision.accion = elegido.accion
    if decision.accion and decision.accion["tipo"] in ("respaldo", "exito"):
        return Decision(accion=decision.accion)
    return decision


# --- consulta al árbitro -----------------------------------------------------------------------

INSTRUCCION_ENTENDER_PAGINA = (
    "Eres el asistente de un candidato que se postula en línea y miras una pantalla que las "
    "reglas no supieron clasificar. Indica en clase qué es: formulario (hay campos por llenar), "
    "intermedia (solo hay que avanzar: detalle de la vacante, aviso o resumen), exito (la "
    "postulación ya se envió), barrera (pide contraseña, crear una cuenta, un captcha, un "
    "código de verificación o iniciar sesión con un tercero) o desconocida.\n"
    "En acciones (máximo 5, en orden) usa solo estas:\n"
    "- avanzar o enviar con el índice de un botón de «botones»; enviar solo si ese botón envía "
    "la postulación definitiva, y ante la duda, avanzar.\n"
    "- esperar si la página sigue cargando.\n"
    "- elegir con el índice de un elemento de «elementos» y en opcion el texto exacto de la "
    "opción a marcar.\n"
    "Nunca pulses botones de clase «nunca» ni de inicio de sesión con terceros, y nunca uses un "
    "índice que no esté en la lista. En motivo explica la decisión en una frase."
)


def texto_consulta(consulta: Consulta) -> str:
    """La pantalla como texto para el árbitro: lo que ve la página, nunca valores del usuario."""
    p = consulta.peticion
    lineas = [f"clase sugerida por las reglas: {p.clase}" + (f" ({p.motivo})" if p.motivo else "")]
    if p.idioma:
        lineas.append(f"idioma: {p.idioma}")
    if p.url:
        lineas.append("página: " + p.url.split("?", 1)[0].split("#", 1)[0])
    if p.resumen.encabezados:
        lineas.append("encabezados: " + " | ".join(p.resumen.encabezados))
    if p.resumen.avisos:
        lineas.append("avisos: " + " | ".join(p.resumen.avisos))
    if p.preguntas:
        lineas.append("campos:")
        lineas += [
            f"- {q.texto} ({q.tipo}{'' if q.obligatoria else ', opcional'})" for q in p.preguntas
        ]
    lineas.append("botones:")
    for b in p.botones:
        marcas = " ".join(
            x for x in (f"clase={b.clase}" if b.clase else "", "oauth" if b.oauth else "") if x
        )
        lineas.append(f"{b.indice}. {b.texto} [{b.tipo}{' ' + marcas if marcas else ''}]")
    lineas.append("elementos:")
    lineas += [
        f"{e.indice}. {e.rol}{f'/{e.tipo}' if e.tipo else ''}: {e.texto}"
        for e in p.resumen.elementos
    ]
    return "\n".join(lineas)


INSTRUCCION_REPARAR_FLUJO = (
    "Eres el asistente de un candidato que se postula en línea. Un paso del flujo falló ANTES de "
    "enviar la postulación y debes proponer cómo seguir. Recibes el paso que falló, su motivo y "
    "lo que se ve en la pantalla. Indica en clase qué es la pantalla (formulario, intermedia, "
    "exito, barrera o desconocida) y en diagnostico, en una frase, qué salió mal para que el "
    "dueño del asistente lo arregle.\n"
    "En acciones (máximo 5, en orden) usa solo estas:\n"
    "- cerrar_modal con el índice del elemento de «elementos» que cierra un aviso, un banner o "
    "una ventana que tapa la página.\n"
    "- avanzar o enviar con el índice de un botón de «botones»; enviar solo si ese botón envía "
    "la postulación definitiva, y ante la duda, avanzar.\n"
    "- elegir con el índice de un elemento de «elementos» y en opcion el texto exacto de la "
    "opción a marcar.\n"
    "- esperar si la página sigue cargando.\n"
    "Nunca pulses botones de clase «nunca» ni de inicio de sesión con terceros, nunca uses un "
    "índice que no esté en la lista y no propongas escribir texto, abrir direcciones ni "
    "contraseñas. Si no ves cómo reparar el paso, deja acciones vacías."
)


@dataclass
class ConsultaReparacion:
    """Lo que ve la reparación: la pantalla, el paso que falló y su motivo. Nada de valores."""

    peticion: Peticion
    paso: str
    fallo: str


def texto_reparacion(consulta: ConsultaReparacion) -> str:
    return f"paso que falló: {consulta.paso}\nmotivo: {consulta.fallo}\n" + texto_consulta(
        Consulta(consulta.peticion)
    )
