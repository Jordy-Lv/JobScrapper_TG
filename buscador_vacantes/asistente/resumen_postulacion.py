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

ORIGENES = {
    "perfil": "dato de tu perfil",
    "banco": "pregunta conocida, respondida con tu perfil",
    "aprendida": "lo que me respondiste en otra postulación",
    "ia": "redactada con IA a partir de tu CV y la vacante",
    "usuario": "me lo dijiste para esta vacante",
}


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


def hoja_de_vida(d: DatosResumen) -> str:
    """Qué hoja de vida recibió el portal, según los pasos que reportó la extensión."""
    portal = t.NOMBRES_PLATAFORMA.get(d.plataforma or "", d.plataforma or "el portal")
    if d.cv_adjunto:
        return f"Adjunté tu CV adaptado a esta vacante (te lo paso abajo): {t.e(d.cv_adjunto)}"
    if "cv_subir" in d.pasos and "cv_verificar_fallo" not in d.pasos:
        return (
            f"Actualicé la hoja de vida de tu perfil de {portal} con tu CV adaptado a esta "
            "vacante y con esa se postuló (te lo paso abajo)."
        )
    if "cv_sin_autorizacion" in d.pasos:
        return (
            f"{portal} envió la hoja de vida que tienes guardada en tu perfil del portal: no me "
            "autorizaste a cambiarla."
        )
    return (
        f"{portal} envió la hoja de vida que tienes guardada en tu perfil del portal (su "
        "formulario no permite adjuntar otra)."
    )


def mensajes(d: DatosResumen) -> list[str]:
    """El resumen en uno o más mensajes HTML de Telegram (se parte por líneas si es largo)."""
    v = d.vacante
    ficha = v.ficha or {}
    portal = t.NOMBRES_PLATAFORMA.get(d.plataforma or "", d.plataforma or "el portal")
    lineas = ["📋 <b>Resumen de tu postulación</b>"]
    if d.enviada_en:
        cuando = d.enviada_en.astimezone().strftime("%d/%m a las %H:%M")
        lineas.append(f"✅ Confirmada por {t.e(portal)} el {cuando}")
    lineas += ["", f"💼 <b>{t.e(v.titulo or 'Vacante')}</b>"]
    empresa = v.empresa or ficha.get("empresa")
    if empresa:
        lineas.append(f"🏢 {t.e(empresa)}")
    if ficha.get("ubicacion"):
        lineas.append(f"📍 {t.e(ficha['ubicacion'])}")
    if ficha.get("salario"):
        lineas.append(f"💰 {t.e(ficha['salario'])}")
    if ficha.get("tipo"):
        lineas.append(f"🕒 {t.e(ficha['tipo'])}")
    publicada, vence = _fecha(ficha.get("publicada")), _fecha(ficha.get("vence"))
    if publicada or vence:
        partes = [f"publicada {publicada}" if publicada else "", f"vence {vence}" if vence else ""]
        lineas.append("📅 " + " · ".join(p for p in partes if p).capitalize())
    if v.url:
        lineas.append(f'🔗 <a href="{t.e(v.url)}">Ver la oferta</a>')

    if v.detalle:
        lineas += ["", "<b>De qué trata</b>", t.e(descripcion_corta(v.detalle))]
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
    if piden or d.afinidad is not None:
        lineas += ["", "<b>Lo que piden</b>", *piden]
        if d.afinidad is not None:
            lineas.append(f"🎯 Tu afinidad: {d.afinidad} %")

    lineas += ["", "📄 <b>Hoja de vida enviada</b>", hoja_de_vida(d)]

    lineas.append("")
    if d.respuestas:
        lineas.append(f"📝 <b>Lo que respondí ({len(d.respuestas)})</b>")
        for n, resp in enumerate(d.respuestas, 1):
            origen = ORIGENES.get(resp.get("origen") or "", resp.get("origen") or "")
            lineas.append(f"{n}. <b>{t.e(resp['pregunta'])}</b>")
            lineas.append(f"   → {t.e(resp.get('respuesta') or '—')}")
            if origen:
                lineas.append(f"   <i>{t.e(origen)}</i>")
    else:
        lineas.append(f"📝 {t.e(portal)} no hizo preguntas en esta postulación.")
    return partir(lineas)


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
