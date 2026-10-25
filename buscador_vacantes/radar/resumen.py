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

from buscador_vacantes.asistente import recetas
from buscador_vacantes.asistente.datos import BaseAsistente
from buscador_vacantes.asistente.textos import MOTIVOS_RESPALDO, NOMBRES_PLATAFORMA
from buscador_vacantes.comun import config as cfg
from buscador_vacantes.comun.estado import Estado, a_texto
from buscador_vacantes.comun.fechas import ZONA
from buscador_vacantes.comun.modelo import Categoria
from buscador_vacantes.radar.formato import NOMBRES_FUENTE, empaquetar, escapar
from buscador_vacantes.radar.notificador_telegram import Notificador
from buscador_vacantes.radar.reportero import ClienteChat

log = logging.getLogger(__name__)

MESES = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")
DESCARTES = (
    "lista_negra",
    "seniority",
    "antiguedad",
    "ubicacion",
    "presencial_fuera",
    "call_center",
    "no_ti",
)
NOMBRES_DESCARTE = {
    "lista_negra": "lista negra",
    "seniority": "seniority",
    "antiguedad": "antigüedad",
    "ubicacion": "ubicación",
    "presencial_fuera": "presencial fuera de la ciudad base",
    "call_center": "call center no remoto",
    "no_ti": "no TI",
}
MIN_INTENTOS_KEYWORD = 2


class RespuestaResumen(BaseModel):
    titular: str = ""
    recomendaciones: list[str] = Field(min_length=1, max_length=3)


CIFRAS_MOTOR = ("enviadas", "ensayadas", "formulario_desconocido", "incierta", "reparadas",
                "arbitro", "respaldo")  # fmt: skip
ESTADOS_CON_MOTIVO = ("respaldo", "formulario_desconocido", "bloqueada", "fallida")
PASOS_DE_REPARACION = ("reparacion", "respaldo_generico")


def _cifras_vacias() -> dict[str, int]:
    return dict.fromkeys(CIFRAS_MOTOR, 0)


@dataclass
class MetricasAsistente:
    """Cifras agregadas del asistente de postulación: sin ids, nombres ni contenido."""

    usuarios_activos: int = 0
    altas: int = 0
    navegadores_en_linea: int = 0
    enviadas: int = 0
    respaldo: int = 0
    verificaciones: int = 0
    respuestas: int = 0
    respuestas_con_ia: int = 0
    preguntas_nuevas_banco: int = 0
    # Motor genérico: cifras por plataforma y por familia de ATS (CIFRAS_MOTOR) de lo terminado
    # en las 24 h, los respaldos por motivo y lo que aprendió el motor en el día
    por_plataforma: dict[str, dict[str, int]] = field(default_factory=dict)
    por_familia: dict[str, dict[str, int]] = field(default_factory=dict)
    respaldos_por_motivo: dict[str, int] = field(default_factory=dict)
    recetas_nuevas: int = 0
    parches_nuevos: int = 0

    def total_motor(self, cifra: str) -> int:
        return sum(c[cifra] for c in self.por_plataforma.values())

    @property
    def pct_sin_ia(self) -> int | None:
        if not self.respuestas:
            return None
        return round(100 * (self.respuestas - self.respuestas_con_ia) / self.respuestas)

    @property
    def hubo_actividad(self) -> bool:
        return bool(
            self.usuarios_activos
            or self.altas
            or self.enviadas
            or self.respaldo
            or self.verificaciones
            or self.preguntas_nuevas_banco
            or bool(self.por_plataforma)
            or self.recetas_nuevas
            or self.parches_nuevos
        )

    def para_ia(self) -> dict[str, Any]:
        return {
            "usuarios_activos": self.usuarios_activos,
            "altas_en_el_periodo": self.altas,
            "navegadores_en_linea": self.navegadores_en_linea,
            "postulaciones_enviadas": self.enviadas,
            "postulaciones_de_respaldo": self.respaldo,
            "verificaciones": self.verificaciones,
            "porcentaje_respuestas_sin_ia": self.pct_sin_ia,
            "preguntas_nuevas_del_banco": self.preguntas_nuevas_banco,
            # Solo totales: el desglose por plataforma y familia es para el mensaje del dueño
            "motor_postulaciones_ensayadas": self.total_motor("ensayadas"),
            "motor_formulario_desconocido": self.total_motor("formulario_desconocido"),
            "motor_inciertas": self.total_motor("incierta"),
            "motor_reparadas": self.total_motor("reparadas"),
            "motor_con_arbitro": self.total_motor("arbitro"),
            "motor_respaldos_por_motivo": dict(self.respaldos_por_motivo),
            "recetas_nuevas": self.recetas_nuevas,
            "parches_nuevos": self.parches_nuevos,
        }


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
    practicas_recategorizadas: int = 0
    practicas_rechazadas: int = 0
    detalles_pedidos: int = 0
    detalles_fallidos: int = 0
    detalles_recuperadas: int = 0
    detalles_cerradas: int = 0
    detalles_vencidas: int = 0
    detalles_en_cola: int = 0  # la cola de ahora, no una suma de corridas
    requests_por_fuente: Counter = field(default_factory=Counter)
    errores_por_fuente: dict[str, Counter] = field(default_factory=dict)
    crudas_por_fuente: Counter = field(default_factory=Counter)
    incidentes_abiertos: list[str] = field(default_factory=list)
    incidentes_cerrados: list[str] = field(default_factory=list)
    ia_llamadas: Counter = field(default_factory=Counter)
    tokens_in: int = 0
    tokens_out: int = 0
    keywords_sin_resultados_7d: list[str] = field(default_factory=list)
    asistente: MetricasAsistente | None = None

    @property
    def enviadas(self) -> int:
        return sum(self.enviadas_por_fuente.values())

    def para_ia(self) -> dict[str, Any]:
        """Solo métricas agregadas: sin URLs, tokens, claves ni ids de chat."""
        datos = {
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
            "guardarrail_practicas": {
                "recategorizadas": self.practicas_recategorizadas,
                "rechazadas": self.practicas_rechazadas,
            },
            "detalle_de_ofertas": {
                "pedidos": self.detalles_pedidos,
                "fallidos": self.detalles_fallidos,
                "recuperadas": self.detalles_recuperadas,
                "cerradas": self.detalles_cerradas,
                "vencidas": self.detalles_vencidas,
                "en_cola": self.detalles_en_cola,
            },
            "requests_por_fuente": dict(self.requests_por_fuente),
            "errores_por_fuente": {f: dict(c) for f, c in self.errores_por_fuente.items()},
            "incidentes_abiertos": self.incidentes_abiertos,
            "incidentes_cerrados_en_el_periodo": self.incidentes_cerrados,
            "ia_llamadas_por_proposito": dict(self.ia_llamadas),
            "ia_tokens": {"entrada": self.tokens_in, "salida": self.tokens_out},
            "palabras_clave_sin_resultados_7_dias": self.keywords_sin_resultados_7d,
        }
        if self.asistente is not None:
            datos["asistente"] = self.asistente.para_ia()
        return datos


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
        m.practicas_recategorizadas += f["practicas_recategorizadas"]
        m.practicas_rechazadas += f["practicas_rechazadas"]
        m.detalles_pedidos += f["detalles_pedidos"]
        m.detalles_fallidos += f["detalles_fallidos"]
        m.detalles_recuperadas += f["detalles_recuperadas"]
        m.detalles_cerradas += f["detalles_cerradas"]
        m.detalles_vencidas += f["detalles_vencidas"]
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

    m.detalles_en_cola = estado.contar_cola_detalle()

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
            "AND i.keyword NOT LIKE 'detalle %' "
            "AND c.modo IN ('normal', 'prueba') GROUP BY i.keyword "
            "HAVING SUM(i.items) = 0 AND COUNT(*) >= ? ORDER BY i.keyword",
            (a_texto(ahora - timedelta(days=7)), MIN_INTENTOS_KEYWORD),
        )
    ]
    return m


def calcular_metricas_asistente(
    base: BaseAsistente, ahora: datetime, *, navegador_caido_min: int
) -> MetricasAsistente:
    """Métricas de 24 h del asistente, solo con conteos (nunca ids, nombres ni respuestas)."""
    desde = ahora - timedelta(hours=24)
    rango = (a_texto(desde), a_texto(ahora))
    cx = base.cx

    def contar(consulta: str, *parametros: Any) -> int:
        return cx.execute(consulta, parametros).fetchone()[0]

    m = MetricasAsistente()
    m.usuarios_activos = contar("SELECT COUNT(*) FROM usuarios WHERE estado = 'activo'")
    m.altas = contar("SELECT COUNT(*) FROM usuarios WHERE creado >= ? AND creado <= ?", *rango)
    m.navegadores_en_linea = contar(
        "SELECT COUNT(*) FROM navegadores WHERE revocado = 0 AND ultimo_latido >= ?",
        a_texto(ahora - timedelta(minutes=navegador_caido_min)),
    )
    for estado, cantidad in cx.execute(
        "SELECT estado, COUNT(*) FROM postulaciones WHERE tipo = 'postular' "
        "AND estado IN ('enviada', 'respaldo') AND terminada_en >= ? AND terminada_en <= ? "
        "GROUP BY estado",
        rango,
    ):
        if estado == "enviada":
            m.enviadas = cantidad
        else:
            m.respaldo = cantidad
    m.verificaciones = contar(
        "SELECT COUNT(DISTINCT postulacion_id) FROM postulacion_pasos "
        "WHERE estado = 'verificacion' AND ts >= ? AND ts <= ?",
        *rango,
    )
    m.respuestas, m.respuestas_con_ia = cx.execute(
        "SELECT COUNT(*), COALESCE(SUM(r.origen = 'ia'), 0) FROM respuestas r "
        "JOIN postulaciones p ON p.id = r.postulacion_id WHERE p.creada >= ? AND p.creada <= ?",
        rango,
    ).fetchone()
    m.preguntas_nuevas_banco = contar(
        "SELECT COUNT(*) FROM banco_preguntas WHERE origen = 'ia' AND creada >= ? AND creada <= ?",
        *rango,
    )
    _cifras_del_motor(cx, m, rango)
    return m


def _cifras_del_motor(cx, m: MetricasAsistente, rango: tuple[str, str]) -> None:
    """Estados finales, reparaciones, árbitro y respaldos de lo terminado en el periodo, por
    plataforma y por familia de ATS (la del dominio de la vacante; sin ella, la plataforma)."""
    filas = cx.execute(
        "SELECT p.id, p.plataforma, p.estado, p.motivo, v.url FROM postulaciones p "
        "LEFT JOIN vacantes v ON v.id_corto = p.id_corto WHERE p.tipo IN ('postular', 'vigia') "
        "AND p.terminada_en >= ? AND p.terminada_en <= ?",
        rango,
    ).fetchall()
    pasos: dict[int, set[str]] = {}
    if filas:
        marcas = ", ".join("?" for _ in filas)
        for f in cx.execute(
            "SELECT DISTINCT postulacion_id, paso FROM postulacion_pasos WHERE paso IN "
            f"('arbitro', 'reparacion', 'respaldo_generico') AND postulacion_id IN ({marcas})",
            [f["id"] for f in filas],
        ):
            pasos.setdefault(f["postulacion_id"], set()).add(f["paso"])
    for f in filas:
        plataforma = f["plataforma"] or "otras"
        familia = recetas.familia_de_host(recetas.host_de(f["url"]), plataforma)
        vistos = pasos.get(f["id"], set())
        hechas = []
        if f["estado"] in ("enviada", "ensayada", "formulario_desconocido", "incierta"):
            nombre = {"enviada": "enviadas", "ensayada": "ensayadas"}.get(f["estado"], f["estado"])
            hechas.append(nombre)
        if f["estado"] in ("enviada", "ensayada") and vistos & set(PASOS_DE_REPARACION):
            hechas.append("reparadas")
        if "arbitro" in vistos:
            hechas.append("arbitro")
        if f["estado"] == "respaldo" or (
            f["estado"] in ESTADOS_CON_MOTIVO and f["motivo"] in MOTIVOS_RESPALDO
        ):
            hechas.append("respaldo")
            motivo = f["motivo"] or "sin_motivo"
            m.respaldos_por_motivo[motivo] = m.respaldos_por_motivo.get(motivo, 0) + 1
        for grupo in (m.por_plataforma.setdefault(plataforma, _cifras_vacias()),
                      m.por_familia.setdefault(familia, _cifras_vacias())):  # fmt: skip
            for cifra in hechas:
                grupo[cifra] += 1
    m.recetas_nuevas = cx.execute(
        "SELECT COUNT(*) FROM recetas WHERE COALESCE(creada, actualizada) >= ? "
        "AND COALESCE(creada, actualizada) <= ?",
        rango,
    ).fetchone()[0]
    m.parches_nuevos = cx.execute(
        "SELECT COUNT(*) FROM parches_flujo WHERE creado >= ? AND creado <= ?", rango
    ).fetchone()[0]


def _lista(contador: Counter, nombres: Callable[[str], str]) -> str:
    return " · ".join(f"{nombres(k)} {v}" for k, v in contador.most_common())


def _cantidad(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


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


def _lineas_asistente(a: MetricasAsistente) -> list[str]:
    sin_ia = "sin respuestas" if a.pct_sin_ia is None else f"{a.pct_sin_ia} % sin IA"
    lineas = [
        f"⚡ Asistente: {a.usuarios_activos} usuarios activos ({a.altas} altas) · "
        f"{a.navegadores_en_linea} navegadores en línea",
        f"📝 Postulaciones: {a.enviadas} enviadas · {a.respaldo} de respaldo · "
        f"{a.verificaciones} verificaciones · respuestas: {sin_ia} · "
        f"preguntas nuevas del banco: {a.preguntas_nuevas_banco}",
    ]
    if a.por_plataforma:
        lineas += ["🧩 Motor por plataforma:", *_lineas_cifras(a.por_plataforma, plataformas=True)]
        familias = {k: v for k, v in a.por_familia.items() if k not in a.por_plataforma}
        if familias:
            lineas += ["🧬 Por familia de ATS:", *_lineas_cifras(familias)]
    if a.respaldos_por_motivo:
        motivos = _lista(Counter(a.respaldos_por_motivo), escapar)
        lineas.append(f"📦 Respaldos por motivo: {motivos}")
    if a.recetas_nuevas or a.parches_nuevos:
        lineas.append(
            f"🧠 Aprendió hoy: {_cantidad(a.recetas_nuevas, 'receta nueva', 'recetas nuevas')} · "
            f"{_cantidad(a.parches_nuevos, 'parche nuevo', 'parches nuevos')}"
        )
    return lineas


def _lineas_cifras(grupos: dict[str, dict[str, int]], *, plataformas: bool = False) -> list[str]:
    """Una línea por grupo (plataforma o familia) con todas las cifras, también las que están
    en cero, para que un «0 de respaldo» sea una buena noticia y no una ausencia."""
    lineas = []
    for nombre, c in sorted(grupos.items()):
        titulo = NOMBRES_PLATAFORMA.get(nombre, nombre.capitalize()) if plataformas else nombre
        lineas.append(
            f"• {escapar(titulo)}: {c['enviadas']} enviadas · {c['ensayadas']} ensayadas · "
            f"{c['formulario_desconocido']} sin reconocer · {c['incierta']} inciertas · "
            f"{c['reparadas']} reparadas · {c['arbitro']} con árbitro · "
            f"{c['respaldo']} de respaldo"
        )
    return lineas


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
    recategorizadas = _cantidad(m.practicas_recategorizadas, "recategorizada", "recategorizadas")
    rechazadas = _cantidad(m.practicas_rechazadas, "rechazada", "rechazadas")
    lineas.append(f"🛡️ Guardarraíl de prácticas: {recategorizadas} · {rechazadas}")
    lineas.append(
        f"🔗 Detalle de LinkedIn: {m.detalles_pedidos} pedidos · {m.detalles_fallidos} fallidos"
        f" · {m.detalles_recuperadas} recuperadas · {m.detalles_en_cola} en cola"
        f" · {m.detalles_vencidas} vencidas · {m.detalles_cerradas} cerradas"
    )
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
    if m.asistente is not None and m.asistente.hubo_actividad:
        lineas.extend(_lineas_asistente(m.asistente))
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
        asistente: BaseAsistente | None = None,
        navegador_caido_min: int = 2,
        reloj: Callable[[], datetime] = lambda: datetime.now(ZONA),
    ) -> None:
        self.config = config
        self.ia = ia
        self.estado = estado
        self.notificador = notificador
        self.chat_id = chat_id
        self.prueba = prueba
        self.asistente = asistente
        self.navegador_caido_min = navegador_caido_min
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
        if self.asistente is not None:
            metricas.asistente = calcular_metricas_asistente(
                self.asistente, ahora, navegador_caido_min=self.navegador_caido_min
            )
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
