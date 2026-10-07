"""Card de una postulación: un solo mensaje que va del toque «Postular» al seguimiento.

Reúne lo que antes eran mensajes sueltos (en cola, progreso, preguntas pendientes, bloqueo del
portal, respaldo, confirmación y vistas de respuestas / de qué trata). Son funciones puras: la
conversación guarda el estado (``Card``), lee los datos y edita el mensaje, igual que con
``tarjeta.py`` y ``preguntas_tarjeta.py``.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field, replace

from buscador_vacantes.asistente import progreso, resumen_postulacion
from buscador_vacantes.asistente import textos as t
from buscador_vacantes.asistente.resumen_postulacion import DatosResumen

EN_COLA = "en_cola"
ESPERANDO_NAVEGADOR = "esperando_navegador"
PREGUNTA = "pregunta"
PROGRESO = "progreso"
SESION = "sesion"
VERIFICACION = "verificacion"
BLOQUEO = "bloqueo"
CONFIRMADA = "confirmada"
INCIERTA = "incierta"
RESPALDO = "respaldo"
CERRADA = "cerrada"

PRINCIPAL = "principal"
RESPUESTAS = "respuestas"
DE_QUE_TRATA = "de_que_trata"

MAX_TEXTO = 4000  # Telegram corta en 4096; se deja margen para las etiquetas HTML
POR_FILA = 3  # botones por fila

SEGUIMIENTO_RESPALDO = (("postulada", "Ya me postulé"), ("descartada", "No me interesa"))
BOTON_GUIA = "Generar guía para entrevista"

Botones = list[list[tuple[str, str]]]
Cb = Callable[..., str]


@dataclass
class Card:
    """Estado guardado en ``kv`` (``card:{pid}``); el contenido se recalcula de la base."""

    mensaje_id: int | None = None
    fase: str = EN_COLA
    vista: str = PRINCIPAL
    pregunta: dict | None = None  # {"id": pendiente, "n": avance, "total": cuántas}
    motivo: str | None = None  # del respaldo, del bloqueo del portal o del cierre
    afinidad: str | None = None  # línea «🎯 Afinidad…» ya escapada, bajo la cabecera

    def a_texto(self) -> str:
        return json.dumps(self.__dict__, ensure_ascii=False)

    @classmethod
    def de_texto(cls, valor: str | None) -> Card | None:
        return cls(**json.loads(valor)) if valor else None


@dataclass
class Datos:
    """Lo que la card necesita para pintarse, ya leído de la base."""

    pid: int
    titulo: str | None
    empresa: str | None
    plataforma: str | None
    url: str | None = None
    seguimiento: str | None = None
    etapa: int = 0
    cuadro: int = 0
    conexion: list[str] = field(default_factory=list)  # bloque «Conexión» (tarjeta.py)
    botones_conexion: Botones = field(default_factory=list)
    pendiente: dict | None = None  # {"id", "pregunta", "opciones"} de la fase PREGUNTA
    resumen: DatosResumen | None = None  # confirmada / incierta

    @property
    def portal(self) -> str:
        return t.NOMBRES_PLATAFORMA.get(self.plataforma or "", self.plataforma or "el portal")


def _cabecera(d: Datos) -> list[str]:
    lineas = [f"<b>{t.e(d.titulo or 'Vacante')}</b>"]
    if d.empresa:
        lineas.append(t.e(d.empresa))
    return lineas


def _pregunta(card: Card, d: Datos) -> list[str]:
    avance = card.pregunta or {}
    titulo = "Pregunta rápida"
    if (avance.get("total") or 0) > 1:
        titulo += f" ({avance.get('n', 1)} de {avance['total']})"
    pendiente = d.pendiente or {}
    lineas = [titulo, f"<b>{t.e(pendiente.get('pregunta'))}</b>"]
    if not pendiente.get("opciones"):
        lineas.append("Escribe tu respuesta.")
    return lineas


def _respaldo(card: Card) -> list[str]:
    motivo = card.motivo or ""
    lineas = []
    if motivo == "sin_navegador":
        lineas.append("Falta vincular tu navegador.")
    lineas.append(f"No puedo postularla sola: {t.e(t.MOTIVOS_RESPALDO.get(motivo, motivo))}.")
    lineas.append("Te envío el paquete abajo para que la envíes a mano.")
    return lineas


def _cuerpo(card: Card, d: Datos) -> list[str]:
    """Líneas del `<blockquote>` de estado para las fases que no son la confirmación."""
    match card.fase:
        case "esperando_navegador":
            return ["Se enviará cuando abras tu navegador."]
        case "pregunta":
            return _pregunta(card, d)
        case "progreso":
            return progreso.etapas(d.etapa, d.cuadro)
        case "sesion":
            lineas = [f"🔒 Inicia sesión en {t.e(d.portal)} en tu navegador y sigo solo."]
            if t.URL_REGISTRO.get(d.plataforma or ""):
                lineas.append("Si no tienes cuenta, créala con el botón.")
            return lineas
        case "verificacion":
            return [
                "🔒 El portal pide una verificación; complétala en la pestaña que abrí en tu "
                "navegador y sigo solo."
            ]
        case "bloqueo":
            causa = t.BLOQUEOS_PORTAL.get(card.motivo or "", "")
            return [f"🔒 {t.e(causa.format(portal=d.portal))}", "No envié nada todavía."]
        case "respaldo":
            return _respaldo(card)
        case "cerrada":
            return [t.e(t.ESTADOS.get(card.motivo or "", card.motivo or "Cerrada"))]
        case _:
            return ["En cola. Te aviso el resultado."]


def _texto_confirmacion(card: Card, d: Datos) -> str:
    if d.resumen is not None:
        texto = resumen_postulacion.tarjeta(replace(d.resumen, confirmada=card.fase == CONFIRMADA))
    else:
        if card.fase == CONFIRMADA:
            estado = f"✅ {t.e(d.portal)} confirmó tu postulación"
        else:
            estado = (
                f"❔ {t.e(d.portal)} no mostró la confirmación: revísala en «Mis postulaciones»"
            )
        texto = "\n".join([*_cabecera(d), "", f"<blockquote>{estado}</blockquote>"])
    return texto


def texto(card: Card, d: Datos) -> str:
    """El texto completo de la card según su fase y su vista, con tope de 4000 caracteres."""
    if card.fase in (CONFIRMADA, INCIERTA):
        if d.resumen is not None and card.vista == RESPUESTAS:
            return resumen_postulacion.recortar(resumen_postulacion.respuestas_lineas(d.resumen))
        if d.resumen is not None and card.vista == DE_QUE_TRATA:
            return resumen_postulacion.recortar(resumen_postulacion.de_que_trata_lineas(d.resumen))
        return resumen_postulacion.recortar(_texto_confirmacion(card, d).split("\n"))
    lineas = _cabecera(d)
    if d.conexion:
        lineas += ["", *d.conexion]
    if card.afinidad:
        lineas += ["", card.afinidad]
    lineas += ["", "<blockquote>" + "\n".join(_cuerpo(card, d)) + "</blockquote>"]
    return resumen_postulacion.recortar(lineas)


def _filas(botones: list[tuple[str, str]]) -> Botones:
    return [botones[i : i + POR_FILA] for i in range(0, len(botones), POR_FILA)]


def _seguimiento(d: Datos, opciones: tuple[tuple[str, str], ...], cb: Cb) -> Botones:
    return _filas([
        (f"✓ {nombre}" if d.seguimiento == valor else nombre, cb("seg", d.pid, valor))
        for valor, nombre in opciones
    ])  # fmt: skip


def _botones_confirmacion(card: Card, d: Datos, cb: Cb) -> Botones:
    if card.vista != PRINCIPAL and d.resumen is not None:
        return [[("Volver", cb("res", d.pid, "v"))]]
    vistas: list[tuple[str, str]] = []
    r = d.resumen
    if r is not None:
        if r.respuestas:
            vistas.append(("Respuestas", cb("res", d.pid, "r")))
        if r.vacante.detalle or r.requisitos or r.vacante.ficha:
            vistas.append(("De qué trata", cb("res", d.pid, "d")))
    if d.url:
        vistas.append(("Ver vacante", f"url:{d.url}"))
    return [*_filas(vistas), [(BOTON_GUIA, cb("guia", d.pid))]]


def botones(card: Card, d: Datos, cb: Cb) -> Botones | None:
    """Botones de la card: acciones del estado, luego vistas y al final el seguimiento."""
    filas: Botones = [*d.botones_conexion]
    match card.fase:
        case "confirmada" | "incierta":
            filas += _botones_confirmacion(card, d, cb)
        case "pregunta":
            for n, opcion in enumerate((d.pendiente or {}).get("opciones", [])[:8]):
                filas.append([(opcion, cb("pend", d.pendiente["id"], n))])
        case "sesion":
            if destino := t.URL_REGISTRO.get(d.plataforma or ""):
                filas.append([("Crear cuenta", f"url:{destino}")])
        case "bloqueo":
            filas.append([("Reintentar", cb("rei", d.pid))])
        case "respaldo":
            acciones = [("Pegar preguntas", cb("pegar", d.pid))]
            if d.url:
                acciones.insert(0, ("Ver vacante", f"url:{d.url}"))
            if card.motivo == "sin_navegador":
                acciones.insert(0, ("Vincular navegador", cb("vincular")))
            filas += _filas(acciones)
            filas += _seguimiento(d, SEGUIMIENTO_RESPALDO, cb)
        case "cerrada":
            if d.url:
                filas.append([("Ver vacante", f"url:{d.url}")])
    return filas or None
