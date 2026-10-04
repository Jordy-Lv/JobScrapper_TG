"""Resumen diario: métricas de 24 h → una llamada a la IA → mensaje; respaldo plano sin IA."""

from __future__ import annotations

import json
import logging
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field, ValidationError

import config as cfg
from estado import Estado, a_texto
from fechas import ZONA
from formato import NOMBRES_FUENTE, empaquetar, escapar
from modelo import Categoria
from notificador_telegram import Notificador
from reportero import ClienteChat

log = logging.getLogger(__name__)

MESES = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")
DESCARTES = ("seniority", "antiguedad", "ubicacion", "no_ti")
NOMBRES_DESCARTE = {
    "seniority": "seniority",
    "antiguedad": "antigüedad",
    "ubicacion": "ubicación",
    "no_ti": "no TI",
}
MIN_INTENTOS_KEYWORD = 2


class RespuestaResumen(BaseModel):
    titular: str = ""
    recomendaciones: list[str] = Field(min_length=1, max_length=3)


@dataclass
class Metricas:
    desde: datetime
    hasta: datetime
    enviadas_por_fuente: Counter = field(default_factory=Counter)
    enviadas_por_categoria: Counter = field(default_factory=Counter)
    corridas: int = 0
    corridas_sin_red: int = 0
    crudas: int = 0
    descartes: Counter = field(default_factory=Counter)
    duplicadas: int = 0
    dudosas: int = 0
    ia_aceptadas: int = 0
    ia_rechazadas: int = 0
    pendientes: int = 0
    requests_por_fuente: Counter = field(default_factory=Counter)
    errores_por_fuente: dict[str, Counter] = field(default_factory=dict)
    crudas_por_fuente: Counter = field(default_factory=Counter)
    incidentes_abiertos: list[str] = field(default_factory=list)
    incidentes_cerrados: list[str] = field(default_factory=list)
    ia_llamadas: Counter = field(default_factory=Counter)
    tokens_in: int = 0
    tokens_out: int = 0
    keywords_sin_resultados_7d: list[str] = field(default_factory=list)

    @property
    def enviadas(self) -> int:
        return sum(self.enviadas_por_fuente.values())

    def para_ia(self) -> dict[str, Any]:
        """Solo métricas agregadas: sin URLs, tokens, claves ni ids de chat."""
        return {
            "periodo": f"{self.desde.astimezone(ZONA):%Y-%m-%d %H:%M} a "
            f"{self.hasta.astimezone(ZONA):%Y-%m-%d %H:%M} (hora Colombia)",
            "corridas": self.corridas,
            "corridas_sin_red": self.corridas_sin_red,
            "enviadas_total": self.enviadas,
            "enviadas_por_fuente": dict(self.enviadas_por_fuente),
            "enviadas_por_categoria": dict(self.enviadas_por_categoria),
            "vacantes_crudas": self.crudas,
            "crudas_por_fuente": dict(self.crudas_por_fuente),
            "descartes_por_regla": {d: self.descartes.get(d, 0) for d in DESCARTES},
            "duplicadas": self.duplicadas,
            "dudosas": self.dudosas,
            "ia_aceptadas": self.ia_aceptadas,
            "ia_rechazadas": self.ia_rechazadas,
            "pendientes": self.pendientes,
            "requests_por_fuente": dict(self.requests_por_fuente),
            "errores_por_fuente": {f: dict(c) for f, c in self.errores_por_fuente.items()},
            "incidentes_abiertos": self.incidentes_abiertos,
            "incidentes_cerrados_en_el_periodo": self.incidentes_cerrados,
            "ia_llamadas_por_proposito": dict(self.ia_llamadas),
            "ia_tokens": {"entrada": self.tokens_in, "salida": self.tokens_out},
            "palabras_clave_sin_resultados_7_dias": self.keywords_sin_resultados_7d,
        }


def calcular_metricas(estado: Estado, ahora: datetime, *, prueba: bool = False) -> Metricas:
    """Métricas de 24 h. Con ``prueba`` cuenta los envíos al chat de prueba.

    En el canal real no cuentan las vacantes promovidas desde la fase de prueba (``enviada_en``
    copiado de ``prueba_en`` por ``promover-prueba``): nunca se publicaron en el canal.
    """
    desde = ahora - timedelta(hours=24)
    m = Metricas(desde, ahora)
    rango = (a_texto(desde), a_texto(ahora))

    if prueba:
        consulta = "SELECT fuente, categoria FROM vistas WHERE prueba_en >= ? AND prueba_en <= ?"
    else:
        consulta = (
            "SELECT fuente, categoria FROM vistas WHERE enviada_en >= ? AND enviada_en <= ? "
            "AND (prueba_en IS NULL OR prueba_en != enviada_en)"
        )
    for f in estado.cx.execute(consulta, rango):
        m.enviadas_por_fuente[f["fuente"]] += 1
        m.enviadas_por_categoria[f["categoria"] or Categoria.OTROS_TI.value] += 1

    for f in estado.cx.execute(
        "SELECT * FROM corridas WHERE inicio >= ? AND inicio <= ? AND modo IN ('normal', 'prueba') "
        "ORDER BY inicio",
        rango,
    ):
        m.corridas += 1
        m.corridas_sin_red += f["sin_red"]
        m.crudas += f["crudas"]
        m.duplicadas += f["duplicadas"]
        m.dudosas += f["dudosas"]
        m.ia_aceptadas += f["ia_aceptadas"]
        m.ia_rechazadas += f["ia_rechazadas"]
        m.pendientes = f["pendientes"]  # las pendientes son un estado, no se suman
        m.descartes.update(json.loads(f["descartes_json"] or "{}"))

    for f in estado.cx.execute(
        "SELECT i.fuente, i.tipo_error, i.items FROM intentos i "
        "JOIN corridas c ON c.id = i.corrida_id "
        "WHERE i.ts >= ? AND i.ts <= ? AND c.modo IN ('normal', 'prueba')",
        rango,
    ):
        m.requests_por_fuente[f["fuente"]] += 1
        m.crudas_por_fuente[f["fuente"]] += f["items"] or 0
        if f["tipo_error"]:
            m.errores_por_fuente.setdefault(f["fuente"], Counter())[f["tipo_error"]] += 1

    for f in estado.cx.execute("SELECT fuente, tipo FROM incidentes WHERE cerrado_en IS NULL"):
        m.incidentes_abiertos.append(f"{f['fuente']}:{f['tipo']}")
    for f in estado.cx.execute(
        "SELECT fuente, tipo FROM incidentes WHERE cerrado_en >= ? AND cerrado_en <= ?", rango
    ):
        m.incidentes_cerrados.append(f"{f['fuente']}:{f['tipo']}")

    for f in estado.cx.execute(
        "SELECT proposito, COUNT(*) AS n, COALESCE(SUM(tokens_in), 0) AS ti, "
        "COALESCE(SUM(tokens_out), 0) AS to_ FROM ia_uso WHERE ts >= ? AND ts <= ? "
        "GROUP BY proposito",
        rango,
    ):
        m.ia_llamadas[f["proposito"]] = f["n"]
        m.tokens_in += f["ti"]
        m.tokens_out += f["to_"]

    m.keywords_sin_resultados_7d = [
        f["keyword"]
        for f in estado.cx.execute(
            "SELECT i.keyword FROM intentos i JOIN corridas c ON c.id = i.corrida_id "
            "WHERE i.ts >= ? AND i.keyword IS NOT NULL AND i.status IS NOT NULL "
            "AND c.modo IN ('normal', 'prueba') GROUP BY i.keyword "
            "HAVING SUM(i.items) = 0 AND COUNT(*) >= ? ORDER BY i.keyword",
            (a_texto(ahora - timedelta(days=7)), MIN_INTENTOS_KEYWORD),
        )
    ]
    return m


def _lista(contador: Counter, nombres: Callable[[str], str]) -> str:
    return " · ".join(f"{nombres(k)} {v}" for k, v in contador.most_common())


NOMBRES_CATEGORIA = {
    Categoria.PRACTICAS: "Prácticas",
    Categoria.DESARROLLO: "Desarrollo",
    Categoria.INFRAESTRUCTURA: "Infra/DevOps/Cloud",
    Categoria.BASES_DATOS: "Bases de datos",
    Categoria.SOPORTE: "Soporte IT",
    Categoria.DATOS: "Datos",
    Categoria.QA: "QA",
    Categoria.CIBERSEGURIDAD: "Ciberseguridad",
    Categoria.OTROS_TI: "Otros TI",
}


def _nombre_categoria(valor: str) -> str:
    try:
        return NOMBRES_CATEGORIA[Categoria(valor)]
    except ValueError:
        return valor


def componer_resumen(
    m: Metricas, titular: str | None, recomendaciones: list[str] | None, motivo: str | None
) -> list[str]:
    fecha = m.hasta.astimezone(ZONA)
    bloques = [f"📊 <b>Resumen diario · {fecha.day} {MESES[fecha.month - 1]}</b>"]
    if titular:
        bloques[0] += f"\n<i>{escapar(titular)}</i>"

    lineas = [f"📨 Enviadas: {m.enviadas}"]
    if m.enviadas:
        lineas[0] += f" ({_lista(m.enviadas_por_fuente, lambda f: NOMBRES_FUENTE.get(f, f))})"
        lineas.append(f"🗂 Por categoría: {_lista(m.enviadas_por_categoria, _nombre_categoria)}")
    descartes = " · ".join(f"{NOMBRES_DESCARTE[d]} {m.descartes.get(d, 0)}" for d in DESCARTES)
    lineas.append(f"🔎 Crudas: {m.crudas} · ya vistas: {m.duplicadas} · corridas: {m.corridas}")
    lineas.append(f"🧹 Descartes: {descartes}")
    lineas.append(
        f"🤖 Dudosas: {m.dudosas} → {m.ia_aceptadas} aceptadas · {m.ia_rechazadas} rechazadas"
        f" · {m.pendientes} pendientes"
    )
    abiertos = ", ".join(escapar(i) for i in m.incidentes_abiertos) or "ninguno"
    lineas.append(
        f"🚨 Incidentes abiertos: {abiertos} · cerrados hoy: {len(m.incidentes_cerrados)}"
    )
    if m.corridas_sin_red:
        lineas.append(f"📡 Corridas sin internet: {m.corridas_sin_red}")
    llamadas = sum(m.ia_llamadas.values())
    tokens = f"{m.tokens_in + m.tokens_out:,}".replace(",", ".")
    lineas.append(f"💳 Consumo IA: {llamadas} llamadas · {tokens} tokens")
    bloques.append("\n".join(lineas))

    if recomendaciones:
        lista = "\n".join(f"{n}. {escapar(r)}" for n, r in enumerate(recomendaciones, 1))
        bloques.append(f"💡 <b>Recomendaciones</b>\n{lista}")
    else:
        bloques.append(f"Recomendaciones IA no disponibles (motivo: {escapar(motivo or '-')})")
    return bloques


class Resumen:
    def __init__(
        self,
        config: cfg.Resumen,
        ia: ClienteChat | None,
        estado: Estado,
        notificador: Notificador,
        chat_id: str,
        *,
        prueba: bool = False,
        reloj: Callable[[], datetime] = lambda: datetime.now(ZONA),
    ) -> None:
        self.config = config
        self.ia = ia
        self.estado = estado
        self.notificador = notificador
        self.chat_id = chat_id
        self.prueba = prueba
        self.reloj = reloj

    @property
    def _clave(self) -> str:
        return "ultimo_resumen_prueba" if self.prueba else "ultimo_resumen"

    def _recomendaciones(self, m: Metricas) -> tuple[str | None, list[str] | None, str | None]:
        if self.ia is None:
            return None, None, "sin clave de API"
        respuesta = self.ia.chat_json(
            "resumen",
            self.config.prompt_sistema,
            {"metricas": m.para_ia()},
            temperatura=self.config.temperatura,
            max_tokens=self.config.max_tokens,
        )
        if not respuesta.ok or respuesta.datos is None:
            return None, None, respuesta.motivo or "respuesta inválida"
        try:
            datos = RespuestaResumen.model_validate(respuesta.datos)
        except ValidationError:
            return None, None, "respuesta inválida"
        return datos.titular or None, datos.recomendaciones, None

    def enviar(self, *, registrar: bool = True) -> bool:
        """Envía el resumen si está activo y no se envió hoy. Devuelve si se envió.

        Con ``registrar=False`` (dry-run) no se controla ni se marca el envío del día.
        """
        if not self.config.activo:
            log.info("Resumen diario desactivado en la configuración")
            return False
        ahora = self.reloj()
        hoy = ahora.astimezone(ZONA).date().isoformat()
        if registrar and self.estado.kv_obtener(self._clave) == hoy:
            log.info("El resumen de hoy ya se envió")
            return False
        metricas = calcular_metricas(self.estado, ahora, prueba=self.prueba)
        titular, recomendaciones, motivo = self._recomendaciones(metricas)
        if motivo:
            log.warning("Resumen sin recomendaciones IA: %s", motivo)
        bloques = componer_resumen(metricas, titular, recomendaciones, motivo)
        ok = True
        for mensaje in empaquetar(bloques):
            envio = self.notificador.enviar_mensaje(self.chat_id, mensaje)
            if not envio.ok:
                ok = False
                log.error("No se pudo enviar el resumen diario: %s", envio.error)
        if ok and registrar:
            self.estado.kv_guardar(self._clave, hoy)
        return ok
