"""Diagnóstico de una vacante: ¿se buscó, llegó y por qué no se publicó?

Solo lee la base de estado. Es la herramienta del dueño para responder «¿por qué no llegó esta
vacante?» sin leer la base a mano (`buscador.py diagnosticar <url | título>`).
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

from buscador_vacantes.comun.estado import a_texto, de_texto, vacante_de_json
from buscador_vacantes.comun.fechas import ZONA
from buscador_vacantes.comun.modelo import Vacante, Veredicto
from buscador_vacantes.comun.normalizar import huella, normalizar_titulo
from buscador_vacantes.radar.clasificador import Clasificador, Dudosa
from buscador_vacantes.radar.filtros import Filtros

# Dominio (sin «www.») → nombre de la fuente que lo busca
DOMINIOS_FUENTE = {
    "linkedin.com": "linkedin",
    "computrabajo.com": "computrabajo",
    "elempleo.com": "elempleo",
    "magneto365.com": "magneto",
    "getonbrd.com": "getonboard",
    "buscadordeempleo.gov.co": "spe",
}
MAX_HALLAZGOS = 10

_ES_URL = re.compile(r"^(https?://|www\.)", re.IGNORECASE)
_ES_CLAVE = re.compile(r"^([a-z]+):(\S+)$")
_ETAPAS = {
    "reglas": "rechazada por las reglas",
    "ia": "rechazada por la IA",
    "guardarrail": "rechazada por el guardarraíl de prácticas",
    "nivel": "rechazada por el nivel pausado",
    "vencida": "venció sin clasificarse",
}


@dataclass
class Hallazgo:
    """Una fila de alguna tabla que coincide con la consulta."""

    donde: str  # vistas | por_enviar | pendientes | pendientes_detalle | descartes
    titulo: str
    lineas: list[str] = field(default_factory=list)


@dataclass
class Diagnostico:
    consulta: str
    fuente: str | None
    hallazgos: list[Hallazgo] = field(default_factory=list)
    # (palabra clave, peticiones, resultados) de los últimos días de la fuente
    intentos: list[tuple[str, int, int]] = field(default_factory=list)
    dias_intentos: int = 3

    @property
    def encontrada(self) -> bool:
        return bool(self.hallazgos)


def normalizar_url(url: str) -> str:
    """Dominio y ruta en minúsculas, sin esquema, «www.», consulta ni barra final."""
    partes = urlsplit(url.strip() if "//" in url else f"//{url.strip()}")
    dominio = partes.netloc.lower().removeprefix("www.")
    ruta = partes.path.rstrip("/").lower()
    return f"{dominio}{ruta}" if ruta else f"{dominio}?{partes.query.lower()}"


def fuente_del_dominio(url: str) -> str | None:
    dominio = urlsplit(url if "//" in url else f"//{url}").netloc.lower().split(":")[0]
    for sufijo, fuente in DOMINIOS_FUENTE.items():
        if dominio == sufijo or dominio.endswith(f".{sufijo}"):
            return fuente
    return None


class _Consulta:
    """Cómo se reconoce una fila: por enlace, por clave de la fuente o por texto del título."""

    def __init__(self, texto: str) -> None:
        self.texto = texto.strip()
        clave = _ES_CLAVE.match(self.texto)
        self.url = normalizar_url(self.texto) if _ES_URL.match(self.texto) else None
        self.clave = self.texto if clave and clave.group(1) in DOMINIOS_FUENTE.values() else None
        self.titulo = None if self.url or self.clave else normalizar_titulo(self.texto)
        self.fuente = (
            fuente_del_dominio(self.texto)
            if self.url
            else (self.clave.split(":")[0] if self.clave else None)
        )

    def coincide(self, clave: str | None, url: str | None, titulo: str | None) -> bool:
        if self.clave:
            return clave == self.clave
        if self.url:
            return bool(url) and normalizar_url(url) == self.url
        return bool(self.titulo) and self.titulo in normalizar_titulo(titulo)


def _fecha(texto: str | None) -> str:
    momento = de_texto(texto)
    return momento.astimezone(ZONA).strftime("%Y-%m-%d %H:%M") if momento else "—"


def _encabezado(titulo: str | None, empresa: str | None, url: str | None) -> str:
    base = f"{titulo or '(sin título)'} — {empresa or 'sin empresa'}"
    return f"{base}\n      {url}" if url else base


def abrir_solo_lectura(ruta: Path | str) -> sqlite3.Connection:
    """Abre la base sin permiso de escritura: el diagnóstico nunca modifica el estado."""
    cx = sqlite3.connect(f"{Path(ruta).resolve().as_uri()}?mode=ro", uri=True, timeout=30)
    cx.row_factory = sqlite3.Row
    return cx


def diagnosticar(
    cx: sqlite3.Connection, texto: str, ahora: datetime, *, dias_intentos: int = 3
) -> Diagnostico:
    """Busca la vacante en vistas, colas y descartes; si no está, resume los intentos recientes."""
    consulta = _Consulta(texto)
    diag = Diagnostico(texto, consulta.fuente, dias_intentos=dias_intentos)
    cx.row_factory = sqlite3.Row

    for fila in cx.execute(
        "SELECT clave, titulo, empresa, url, categoria, primera_vez, enviada_en, prueba_en "
        "FROM vistas ORDER BY primera_vez DESC"
    ):
        if consulta.coincide(fila["clave"], fila["url"], fila["titulo"]):
            if fila["enviada_en"]:
                estado = f"publicada en el canal el {_fecha(fila['enviada_en'])}"
            elif fila["prueba_en"]:
                estado = f"enviada solo al chat de prueba el {_fecha(fila['prueba_en'])}"
            else:
                estado = "vista, pero aún no enviada"
            lineas = [f"Estado: {estado}", f"Vista por primera vez: {_fecha(fila['primera_vez'])}"]
            if fila["categoria"]:
                lineas.append(f"Categoría: {fila['categoria']}")
            diag.hallazgos.append(
                Hallazgo(
                    "vistas", _encabezado(fila["titulo"], fila["empresa"], fila["url"]), lineas
                )
            )

    for tabla, descripcion in (
        ("por_enviar", "aceptada, en la cola de envío"),
        ("pendientes", "dudosa, esperando la respuesta de la IA"),
        ("pendientes_detalle", "esperando que se lea el detalle de la oferta"),
    ):
        extra = ", intentos, ultimo_error" if tabla == "pendientes_detalle" else ""
        for fila in cx.execute(f"SELECT vacante_json, desde{extra} FROM {tabla}"):  # noqa: S608
            vacante = vacante_de_json(fila["vacante_json"])
            if consulta.coincide(vacante.clave, vacante.url, vacante.titulo):
                lineas = [f"Estado: {descripcion} desde el {_fecha(fila['desde'])}"]
                if tabla == "pendientes_detalle":
                    lineas.append(f"Intentos de detalle: {fila['intentos']}")
                    if fila["ultimo_error"]:
                        lineas.append(f"Último error: {fila['ultimo_error']}")
                diag.hallazgos.append(
                    Hallazgo(
                        tabla, _encabezado(vacante.titulo, vacante.empresa, vacante.url), lineas
                    )
                )

    for fila in cx.execute("SELECT * FROM descartes ORDER BY ultima_vez DESC"):
        if consulta.coincide(fila["clave"], fila["url"], fila["titulo"]):
            lineas = [
                f"Estado: {_ETAPAS.get(fila['etapa'], fila['etapa'])} (etapa «{fila['etapa']}»)",
                f"Motivo: {fila['motivo']}" + (f" — {fila['detalle']}" if fila["detalle"] else ""),
                f"Palabra clave que la trajo: {fila['keyword'] or '—'}",
                f"Vista {fila['veces']} {'vez' if fila['veces'] == 1 else 'veces'}: "
                f"del {_fecha(fila['primera_vez'])} al {_fecha(fila['ultima_vez'])}",
            ]
            diag.hallazgos.append(
                Hallazgo(
                    "descartes", _encabezado(fila["titulo"], fila["empresa"], fila["url"]), lineas
                )
            )

    if not diag.encontrada and diag.fuente:
        desde = a_texto(ahora - timedelta(days=dias_intentos))
        diag.intentos = [
            (f["keyword"] or "(sin palabra clave)", f["peticiones"], f["items"] or 0)
            for f in cx.execute(
                "SELECT keyword, COUNT(*) AS peticiones, SUM(items) AS items FROM intentos "
                "WHERE fuente = ? AND ts >= ? GROUP BY keyword ORDER BY items DESC, keyword",
                (diag.fuente, desde),
            )
        ]
    return diag


def formatear(diag: Diagnostico) -> str:
    if diag.encontrada:
        lineas = [f"Diagnóstico de «{diag.consulta}»:"]
        for h in diag.hallazgos[:MAX_HALLAZGOS]:
            lineas.append(f"\n[{h.donde}] {h.titulo}")
            lineas.extend(f"   {linea}" for linea in h.lineas)
        extra = len(diag.hallazgos) - MAX_HALLAZGOS
        if extra > 0:
            lineas.append(f"\n… y {extra} coincidencias más; afina el texto o usa el enlace.")
        return "\n".join(lineas)

    lineas = [
        f"Diagnóstico de «{diag.consulta}»:",
        "El buscador nunca recibió esta vacante: no está en vistas, en las colas ni en los "
        "descartes (los descartes se guardan 14 días).",
    ]
    if not diag.fuente:
        lineas.append(
            "No se pudo deducir la fuente. Prueba con el enlace de la oferta para ver qué se "
            "buscó en su portal."
        )
    elif diag.intentos:
        lineas.append(
            f"\nPalabras clave buscadas en {diag.fuente} en los últimos {diag.dias_intentos} días:"
        )
        lineas.extend(
            f"   {keyword}: {peticiones} {'petición' if peticiones == 1 else 'peticiones'}, "
            f"{items} resultados"
            for keyword, peticiones, items in diag.intentos
        )
    else:
        lineas.append(
            f"\n{diag.fuente} no registra ninguna búsqueda en los últimos {diag.dias_intentos} "
            "días: la fuente puede estar desactivada, en cooldown o sin presupuesto."
        )
    return "\n".join(lineas)


# --- evaluación en seco ------------------------------------------------------------------------


def vacante_manual(
    titulo: str,
    *,
    empresa: str = "",
    ubicacion: str | None = None,
    modalidad: str | None = None,
    descripcion: str | None = None,
    fuente: str = "manual",
) -> Vacante:
    return Vacante(
        fuente=fuente,
        id_fuente="diagnostico",
        titulo=titulo,
        empresa=empresa,
        url="",
        keyword="diagnosticar",
        ubicacion=ubicacion,
        modalidad=modalidad,
        descripcion=descripcion,
    )


def _guardarrail(filtros: Filtros, vacante: Vacante) -> str:
    correccion = filtros.guardarrail_practicas(vacante)
    if correccion is None:
        return "no la cambia"
    if correccion.rechaza:
        return f"la rechaza ({correccion.detalle})"
    return (
        f"la pasa de {correccion.original.value} a {correccion.nueva.value} ({correccion.detalle})"
    )


def evaluar(
    filtros: Filtros,
    vacante: Vacante,
    ahora: datetime,
    *,
    clasificador: Clasificador | None = None,
) -> str:
    """Evalúa una vacante con las reglas vigentes y, con ``clasificador``, también con la IA.

    El clasificador debe tener un ``Estado`` en memoria: así no se escribe en la caché real.
    """
    evaluacion = filtros.evaluar(vacante, ahora)
    lineas = [
        f"Evaluación de «{vacante.titulo}»:",
        f"   Veredicto de las reglas: {evaluacion.veredicto.value}",
        f"   Motivo: {evaluacion.motivo.value}"
        + (f" — {evaluacion.detalle}" if evaluacion.detalle else ""),
    ]
    if evaluacion.veredicto == Veredicto.ACEPTAR:
        vacante.categoria = evaluacion.categoria
        lineas.append(f"   Categoría: {evaluacion.categoria.value}")
        lineas.append(f"   Guardarraíl de prácticas: {_guardarrail(filtros, vacante)}")
    elif evaluacion.veredicto == Veredicto.DUDOSA:
        if clasificador is None:
            lineas.append("   Decidiría la IA (usa --con-ia para ver su respuesta).")
        else:
            lineas.extend(_con_ia(filtros, clasificador, vacante, ahora))
    return "\n".join(lineas)


def _con_ia(
    filtros: Filtros, clasificador: Clasificador, vacante: Vacante, ahora: datetime
) -> list[str]:
    dudosa = Dudosa(vacante, huella(vacante.titulo, vacante.empresa, vacante.clave))
    resultado = clasificador.clasificar([dudosa], ahora)
    if resultado.aceptadas:
        lineas = [
            "   IA: aceptar" + (f" — {dudosa.motivo}" if dudosa.motivo else ""),
            f"   Categoría: {vacante.categoria.value}",
            f"   Guardarraíl de prácticas: {_guardarrail(filtros, vacante)}",
        ]
    elif resultado.rechazadas:
        lineas = [f"   IA: rechazar — {dudosa.motivo or 'sin motivo'}"]
    else:
        lineas = [f"   IA: sin respuesta ({resultado.motivo_fallo or 'pendiente'})"]
    lineas.append("   (La respuesta no se guardó en la caché de clasificaciones.)")
    return lineas
