"""Resumen detallado de una postulación confirmada por el portal.

Lo recibe el usuario en el bot apenas el portal confirma el envío: de qué trata la vacante
(ficha y descripción), qué hoja de vida recibió el portal y cada pregunta del formulario con lo
que se respondió y de dónde salió la respuesta. Son funciones puras: el bot les pasa los datos
ya leídos de la base.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

from buscador_vacantes.asistente import textos as t
from buscador_vacantes.asistente.vacantes import VacanteIndexada

MAX_MENSAJE = 4000  # Telegram corta en 4096; se deja margen para las etiquetas HTML
MAX_DESCRIPCION = 700


@dataclass
class DatosResumen:
    vacante: VacanteIndexada
    plataforma: str | None
    enviada_en: datetime | None
    afinidad: int | None = None
    requisitos: dict | None = None  # vacantes.requisitos_json["requisitos"]
    respuestas: list[dict] = field(default_factory=list)  # pregunta, respuesta, origen
    pasos: list[str] = field(default_factory=list)  # nombres de los pasos registrados
    cv_adjunto: str | None = None  # nombre del PDF que la extensión adjuntó
    confirmada: bool = True  # False: se envió pero el portal no mostró la confirmación

    @property
    def con_encuesta(self) -> bool:
        """El portal pidió responder preguntas (encuesta) antes de recibir la postulación."""
        return bool(self.respuestas) or "llenado" in self.pasos


def descripcion_corta(texto: str | None, limite: int = MAX_DESCRIPCION) -> str:
    """Primeras frases de la descripción, cortadas en un final de frase si se puede."""
    texto = " ".join((texto or "").split())
    if len(texto) <= limite:
        return texto
    recorte = texto[:limite]
    fin = max(recorte.rfind(". "), recorte.rfind("! "), recorte.rfind("? "))
    if fin >= limite // 2:
        return recorte[: fin + 1]
    return recorte.rsplit(" ", 1)[0] + "…"


def _fecha(valor: str | None) -> str | None:
    if not valor or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", valor):
        return None
    año, mes, dia = valor.split("-")
    return f"{dia}/{mes}/{año}"


ICONOS_ORIGEN = {"perfil": "👤", "banco": "👤", "aprendida": "💬", "usuario": "💬", "ia": "🤖"}
LEYENDA_ORIGEN = {"👤": "tu perfil", "💬": "lo que me dijiste", "🤖": "redactada con IA"}


def _portal(d: DatosResumen) -> str:
    return t.NOMBRES_PLATAFORMA.get(d.plataforma or "", d.plataforma or "el portal")


def hoja_de_vida(d: DatosResumen) -> str:
    """Qué hoja de vida recibió el portal, según los pasos que reportó la extensión."""
    if d.cv_adjunto:
        return "CV adaptado adjunto"
    if "cv_subir" in d.pasos and "cv_verificar_fallo" not in d.pasos:
        return "CV adaptado en tu perfil"
    return "HdV del perfil"


def tarjeta(d: DatosResumen) -> str:
    """El mensaje corto de una postulación: título, empresa y una cita con el estado."""
    v = d.vacante
    portal = t.e(_portal(d))
    empresa = v.empresa or (v.ficha or {}).get("empresa")
    icono = "✅" if d.confirmada else "❔"
    cabecera = [f"{icono} <b>{t.e(v.titulo or 'Vacante')}</b>"]
    if empresa:
        cabecera.append(t.e(empresa))
    cuando = d.enviada_en.astimezone().strftime("%d/%m, %H:%M") if d.enviada_en else ""
    if d.confirmada:
        estado = f"{portal} confirmó tu postulación"
    else:
        estado = f"{portal} no mostró la confirmación: revísala en «Mis postulaciones»"
    detalle = [cuando] if cuando else []
    detalle.append(f"Encuesta de {len(d.respuestas)}" if d.con_encuesta else "Sin encuesta")
    detalle.append(hoja_de_vida(d))
    return "\n".join([*cabecera, "", f"<blockquote>{estado}\n{' · '.join(detalle)}</blockquote>"])


def respuestas_lineas(d: DatosResumen) -> list[str]:
    """Cada pregunta con su respuesta; el origen va como icono con una leyenda al final."""
    lineas = [f"📝 <b>Tus respuestas</b> · {t.e(d.vacante.titulo or 'Vacante')}"]
    usados: list[str] = []
    for n, resp in enumerate(d.respuestas, 1):
        icono = ICONOS_ORIGEN.get(resp.get("origen") or "", "")
        if icono and icono not in usados:
            usados.append(icono)
        respuesta = t.e(resp.get("respuesta") or "—")
        lineas += ["", f"{n}· {t.e(resp['pregunta'])}", f"<b>{respuesta}</b> {icono}"]
    if usados:
        lineas += ["", " · ".join(f"{i} {LEYENDA_ORIGEN[i]}" for i in usados)]
    return lineas


def respuestas(d: DatosResumen) -> list[str]:
    return partir(respuestas_lineas(d))


def de_que_trata_lineas(d: DatosResumen) -> list[str]:
    """Ficha de la vacante, su descripción (plegable) y lo que piden."""
    v = d.vacante
    ficha = v.ficha or {}
    lineas = [f"📋 <b>{t.e(v.titulo or 'Vacante')}</b>"]
    empresa = v.empresa or ficha.get("empresa")
    datos = [f"🏢 {t.e(empresa)}" if empresa else ""]
    for icono, clave in (("📍", "ubicacion"), ("💰", "salario"), ("🕒", "tipo")):
        if ficha.get(clave):
            datos.append(f"{icono} {t.e(ficha[clave])}")
    if linea := " · ".join(x for x in datos if x):
        lineas.append(linea)
    publicada, vence = _fecha(ficha.get("publicada")), _fecha(ficha.get("vence"))
    if publicada or vence:
        partes = [f"publicada {publicada}" if publicada else "", f"vence {vence}" if vence else ""]
        lineas.append("📅 " + " · ".join(x for x in partes if x).capitalize())
    if v.detalle:
        lineas += ["", f"<blockquote expandable>{t.e(descripcion_corta(v.detalle))}</blockquote>"]
    r = d.requisitos or {}
    piden = []
    if r.get("obligatorios"):
        piden.append("Piden: " + t.e(", ".join(r["obligatorios"][:8])))
    if r.get("deseables"):
        piden.append("Suma: " + t.e(", ".join(r["deseables"][:6])))
    extras = [f"{k}: {t.e(r[c])}" for k, c in (("Nivel", "nivel"), ("Modalidad", "modalidad"))
              if r.get(c)]  # fmt: skip
    if extras:
        piden.append(" · ".join(extras))
    if d.afinidad is not None:
        piden.append(f"🎯 Tu afinidad: {d.afinidad} %")
    if piden:
        lineas += ["", *piden]
    return lineas


def de_que_trata(d: DatosResumen) -> list[str]:
    return partir(de_que_trata_lineas(d))


def recortar(lineas: list[str], maximo: int = MAX_MENSAJE) -> str:
    """Une las líneas en un solo texto de hasta `maximo` caracteres, sin partir etiquetas.

    Si no caben todas, descarta las últimas y termina con «…». Una línea sola que excede se
    corta sin sus etiquetas (un corte a medias dejaría HTML roto, que Telegram rechaza).
    """
    texto = "\n".join(lineas)
    if len(texto) <= maximo:
        return texto
    mantener: list[str] = []
    usado = 0
    for linea in lineas:
        if usado + len(linea) + 2 > maximo - 1:
            break
        mantener.append(linea)
        usado += len(linea) + 1
    if not mantener:
        plano = re.sub(r"<[^>]+>", "", lineas[0])[: maximo - 1]
        return re.sub(r"&[#\w]*$", "", plano) + "…"
    return "\n".join(mantener).rstrip() + "\n…"


def partir(lineas: list[str], maximo: int = MAX_MENSAJE) -> list[str]:
    """Agrupa líneas en mensajes de hasta `maximo` caracteres sin cortar una línea."""
    salida: list[str] = []
    actual = ""
    for linea in lineas:
        linea = linea[:maximo]
        if actual and len(actual) + 1 + len(linea) > maximo:
            salida.append(actual.rstrip())
            actual = ""
        actual = f"{actual}\n{linea}" if actual else linea
    if actual.strip():
        salida.append(actual.rstrip())
    return salida
