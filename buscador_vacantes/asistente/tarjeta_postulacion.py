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
from datetime import datetime

from buscador_vacantes.asistente import progreso, resumen_postulacion
from buscador_vacantes.asistente import textos as t
from buscador_vacantes.asistente.resumen_postulacion import DatosResumen
from buscador_vacantes.comun.fechas import ZONA

EN_COLA = "en_cola"
ESPERANDO_NAVEGADOR = "esperando_navegador"
PREGUNTA = "pregunta"
REVISION = "revision"  # el usuario revisa lo redactado antes del envío
PROGRESO = "progreso"
SESION = "sesion"
VERIFICACION = "verificacion"
BLOQUEO = "bloqueo"
CONFIRMADA = "confirmada"
INCIERTA = "incierta"
RESPALDO = "respaldo"
CERRADA = "cerrada"
CUENTA = "cuenta"  # cuenta regresiva antes de encolar: la postulación aún no existe
CANCELADA = "cancelada"

PRINCIPAL = "principal"
RESPUESTAS = "respuestas"
DE_QUE_TRATA = "de_que_trata"
CORREGIR = "corregir"  # revisión: lista para elegir la respuesta a corregir

MAX_TEXTO = 4000  # Telegram corta en 4096; se deja margen para las etiquetas HTML
POR_FILA = 3  # botones por fila

SEGUIMIENTO_RESPALDO = (("postulada", "Ya me postulé"), ("descartada", "No me interesa"))
BOTON_GUIA = "Generar guía para entrevista"
BOTON_ESCRIBIR = "✍️ Escribir yo"
BOTON_RESERVADO = "Prefiero no decirlo"

Botones = list[list[tuple[str, str]]]
Cb = Callable[..., str]


@dataclass
class Card:
    """Estado guardado en ``kv`` (``card:{pid}``); el contenido se recalcula de la base."""

    mensaje_id: int | None = None
    fase: str = EN_COLA
    vista: str = PRINCIPAL
    # Pregunta: {"id": pendiente, "n": avance, "total": cuántas, "escribir": tocó «Escribir
    # yo»}. Revisión: {"corrigiendo": id de la respuesta que el usuario reescribe}
    pregunta: dict | None = None
    motivo: str | None = None  # del respaldo, del bloqueo del portal o del cierre
    afinidad: str | None = None  # línea «🎯 Afinidad…» ya escapada, bajo la cabecera
    # En cola: por qué todavía no sale ({codigo, plataforma, datos} de espera.Causa) o None
    espera: dict | None = None

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
    segundos_etapa: float = 0.0  # progreso: segundos desde que empezó la etapa en curso
    conexion: list[str] = field(default_factory=list)  # bloque «Conexión» (tarjeta.py)
    botones_conexion: Botones = field(default_factory=list)
    pendiente: dict | None = None  # {"id", "pregunta", "opciones", "tipo"} de la fase PREGUNTA
    revision: list[dict] = field(default_factory=list)  # {id, pregunta, respuesta, origen}
    resumen: DatosResumen | None = None  # confirmada / incierta
    id_corto: str | None = None  # cuenta / cancelada: aún no hay postulación (pid)
    segundos: int = 0  # cuenta: segundos que faltan
    total: int = 0  # cuenta: duración completa
    url_tienda: str = ""  # en cola: tienda de la extensión, si hay enlace configurado

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
    if not pendiente.get("opciones") or avance.get("escribir"):
        lineas.append("Escribe tu respuesta.")
    elif pendiente.get("tipo") == "dato":
        lineas.append("Elige una opción o escríbela tú.")
    return lineas


def lineas_revision(d: Datos) -> list[str]:
    """Cada pregunta con la respuesta redactada, completa (la corrigió el usuario: 💬)."""
    lineas: list[str] = []
    for n, r in enumerate(d.revision, 1):
        icono = " 💬" if r.get("origen") == "usuario" else ""
        respuesta = t.e(r.get("respuesta") or "—")
        lineas += ["", f"{n}· {t.e(r['pregunta'])}", f"<b>{respuesta}</b>{icono}"]
    return lineas


def _revision(card: Card, d: Datos) -> list[str]:
    corrigiendo = (card.pregunta or {}).get("corrigiendo")
    if corrigiendo is not None:
        n = next((i for i, r in enumerate(d.revision, 1) if r["id"] == corrigiendo), None)
        if n is not None:
            return [f"✏️ Escribe el texto nuevo para la respuesta {n}; lo enviaré tal cual."]
    if card.vista == CORREGIR:
        return ["✏️ ¿Qué respuesta quieres corregir?"]
    return ["✍️ Revisa lo que redacté antes de enviarlo. Aún no envié nada."]


def revision_cabe(card: Card, d: Datos) -> bool:
    """Las respuestas completas caben en la card; si no, van aparte con partir()."""
    completo = "\n".join([*_cabecera(d), "", *_revision(card, d), *lineas_revision(d)])
    return len(completo) <= MAX_TEXTO


def _respaldo(card: Card) -> list[str]:
    motivo = card.motivo or ""
    lineas = []
    if motivo == "sin_navegador":
        lineas.append("Falta vincular tu navegador.")
    lineas.append(f"No puedo postularla sola: {t.e(t.MOTIVOS_RESPALDO.get(motivo, motivo))}.")
    return lineas


def _barra(restante: int, total: int) -> str:
    """Barra que se va llenando: ▰ lo transcurrido y ▱ lo que falta (hasta 10 casillas)."""
    ancho = max(1, min(total, 10))
    llenas = round(ancho * (total - restante) / total) if total > 0 else ancho
    return "▰" * llenas + "▱" * (ancho - llenas)


def _cuenta(d: Datos) -> list[str]:
    return [f"⚡ Postulando en {d.segundos} s", _barra(d.segundos, d.total)]


def _cancelada(card: Card) -> list[str]:
    match card.motivo:
        case "interrumpida":
            return ["La cuenta se interrumpió; no envié nada."]
        case "pausa":
            return ["Tus postulaciones están en pausa. No envié nada."]
        case _:
            return ["Cancelaste la postulación. No envié nada."]


def _hora(valor: str | None) -> str:
    """Hora local (Bogotá) de un instante guardado en la causa; vacío si no hay."""
    return datetime.fromisoformat(valor).astimezone(ZONA).strftime("%H:%M") if valor else ""


def _espera(card: Card, d: Datos) -> list[str]:
    """«En cola» con la causa concreta de la espera y cómo resolverla."""
    espera = card.espera or {}
    datos = espera.get("datos") or {}
    plataforma = espera.get("plataforma") or d.plataforma or ""
    hora = _hora(datos.get("cuando"))
    ultimo = _hora(datos.get("ultimo"))
    mensaje = t.ESPERAS[espera["codigo"]].format(
        portal=t.e(t.NOMBRES_PLATAFORMA.get(plataforma, plataforma or "el portal")),
        dominio=t.e(t.DOMINIOS.get(plataforma, plataforma)),
        version=t.e(datos.get("version", "?")),
        minima=t.e(datos.get("minima", "?")),
        desde=f" desde las {ultimo}" if ultimo else "",
        hora=hora,
    )
    return ["⏳ En cola.", mensaje]


def _con_espera(card: Card) -> bool:
    return card.fase in (EN_COLA, ESPERANDO_NAVEGADOR) and bool(card.espera)


def _cuerpo(card: Card, d: Datos) -> list[str]:
    """Líneas del `<blockquote>` de estado para las fases que no son la confirmación."""
    if _con_espera(card):
        return _espera(card, d)
    match card.fase:
        case "cuenta":
            return _cuenta(d)
        case "cancelada":
            return _cancelada(card)
        case "esperando_navegador":
            return ["Se enviará cuando abras tu navegador."]
        case "pregunta":
            return _pregunta(card, d)
        case "revision":
            if revision_cabe(card, d):
                return [*_revision(card, d), *lineas_revision(d)]
            return [*_revision(card, d), "", "Te las mando completas en los mensajes de abajo."]
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
    if card.fase == PROGRESO:
        lineas += ["", progreso.linea_barra(d.etapa, d.segundos_etapa)]
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


def _botones_pregunta(card: Card, d: Datos, cb: Cb) -> Botones:
    """Formulario: una opción del portal por fila. Dato: las sugerencias del redactor, «✍️
    Escribir yo» (solo si hay sugerencias) y «Prefiero no decirlo»."""
    pendiente = d.pendiente or {}
    opciones = pendiente.get("opciones", [])[:8]
    if pendiente.get("tipo") != "dato":
        return [[(opcion, cb("pend", pendiente["id"], n))] for n, opcion in enumerate(opciones)]
    filas: Botones = []
    if not (card.pregunta or {}).get("escribir"):
        filas += _filas([(o, cb("pend", pendiente["id"], n)) for n, o in enumerate(opciones)])
        if opciones:
            filas.append([(BOTON_ESCRIBIR, cb("pesc", pendiente["id"]))])
    filas.append([(BOTON_RESERVADO, cb("pres", pendiente["id"]))])
    return filas


def _botones_revision(card: Card, d: Datos, cb: Cb) -> Botones:
    if (card.pregunta or {}).get("corrigiendo") is not None:
        return [[("Volver", cb("rev", d.pid, "v"))]]
    if card.vista == CORREGIR:
        numeros = [(str(n), cb("rev", d.pid, n)) for n in range(1, len(d.revision) + 1)]
        return [*_filas(numeros), [("Volver", cb("rev", d.pid, "v"))]]
    return [[("✅ Enviar", cb("rev", d.pid, "ok")), ("✏️ Corregir", cb("rev", d.pid, "c"))]]


def _botones_espera(card: Card, d: Datos, cb: Cb) -> Botones:
    """La solución de cada causa; solo las que el usuario resuelve con un toque llevan botón."""
    espera = card.espera or {}
    plataforma = espera.get("plataforma") or d.plataforma or ""
    match espera.get("codigo"):
        case "sin_sesion":
            ingreso = t.URL_INGRESO.get(plataforma) or t.URL_REGISTRO.get(plataforma)
            if not ingreso:
                return []
            acciones = [("Iniciar sesión", f"url:{ingreso}")]
            if destino := t.URL_REGISTRO.get(plataforma):
                acciones.append(("Crear cuenta", f"url:{destino}"))
            return [acciones]
        case "sin_navegador":
            return [[("Vincular navegador", cb("vincular"))]]
        case "extension_desactualizada" if d.url_tienda:
            return [[("Actualizar extensión", f"url:{d.url_tienda}")]]
        case "cuenta_por_confirmar" if not d.botones_conexion:
            nombre = t.NOMBRES_PLATAFORMA.get(plataforma, plataforma)
            return [[
                (f"Confirmar {nombre}", cb("cuenta", plataforma, "si")),
                ("Cancelar", cb("cuenta", plataforma, "no")),
            ]]  # fmt: skip
        case "cuenta_distinta" if not d.botones_conexion:
            return [[
                ("Es mi cuenta nueva", cb("cuenta", plataforma, "nueva")),
                ("No es mía", cb("cuenta", plataforma, "no")),
            ]]  # fmt: skip
    return []


def botones(card: Card, d: Datos, cb: Cb) -> Botones | None:
    """Botones de la card: acciones del estado, luego vistas y al final el seguimiento."""
    filas: Botones = [*d.botones_conexion]
    if _con_espera(card):
        return [*filas, *_botones_espera(card, d, cb)] or None
    match card.fase:
        case "confirmada" | "incierta":
            filas += _botones_confirmacion(card, d, cb)
        case "cuenta":
            filas.append([("Cancelar", cb("cancel", d.id_corto))])
        case "cancelada":
            filas.append([("Postular", cb("post", d.id_corto))])
        case "pregunta":
            filas += _botones_pregunta(card, d, cb)
        case "revision":
            filas += _botones_revision(card, d, cb)
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
