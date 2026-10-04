"""Clasificación IA de vacantes dudosas: lotes, caché por huella y pendientes con vencimiento."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from pydantic import BaseModel, ValidationError

from buscador_vacantes import config as cfg
from buscador_vacantes.estado import Estado, a_texto, de_texto, vacante_a_json, vacante_de_json
from buscador_vacantes.filtros import Filtros
from buscador_vacantes.ia_cliente import ClienteIA
from buscador_vacantes.modelo import Categoria, Vacante

log = logging.getLogger(__name__)

TOKENS_POR_VACANTE = 60
TOKENS_BASE = 100


class ItemIA(BaseModel):
    id: int
    aceptar: bool
    categoria: str | None = None
    motivo: str = ""


class RespuestaClasificador(BaseModel):
    vacantes: list[ItemIA]


@dataclass
class Dudosa:
    vacante: Vacante
    huella: str


@dataclass
class ResultadoClasificacion:
    aceptadas: list[Dudosa] = field(default_factory=list)
    rechazadas: list[Dudosa] = field(default_factory=list)
    pendientes: list[Dudosa] = field(default_factory=list)
    vencidas: list[Dudosa] = field(default_factory=list)
    llamadas: int = 0
    desde_cache: int = 0
    motivo_fallo: str | None = None


class Clasificador:
    def __init__(
        self,
        config: cfg.Clasificador,
        ia: ClienteIA | None,
        estado: Estado,
        filtros: Filtros,
        fuentes_con_filtro_nivel: frozenset[str] = frozenset(),
    ) -> None:
        self.config = config
        self.ia = ia
        self.estado = estado
        self.filtros = filtros
        self.fuentes_con_filtro_nivel = fuentes_con_filtro_nivel

    # --- persistencia -----------------------------------------------------------------------

    def _cargar_pendientes(self) -> list[tuple[Dudosa, datetime]]:
        filas = self.estado.cx.execute("SELECT huella, vacante_json, desde FROM pendientes")
        return [
            (Dudosa(vacante_de_json(f["vacante_json"]), f["huella"]), de_texto(f["desde"]))
            for f in filas
        ]

    def _guardar_pendiente(self, dudosa: Dudosa, ahora: datetime) -> None:
        with self.estado.transaccion() as cx:
            cx.execute(
                "INSERT INTO pendientes(huella, vacante_json, desde) VALUES (?, ?, ?) "
                "ON CONFLICT(huella) DO NOTHING",
                (dudosa.huella, vacante_a_json(dudosa.vacante), a_texto(ahora)),
            )

    def _quitar_pendiente(self, huella: str) -> None:
        with self.estado.transaccion() as cx:
            cx.execute("DELETE FROM pendientes WHERE huella = ?", (huella,))

    def _cache(self, huella: str) -> tuple[bool, Categoria | None] | None:
        fila = self.estado.cx.execute(
            "SELECT aceptar, categoria FROM clasificaciones WHERE huella = ?", (huella,)
        ).fetchone()
        if fila is None:
            return None
        categoria = fila["categoria"]
        return bool(fila["aceptar"]), Categoria(categoria) if categoria else None

    def _guardar_clasificacion(
        self, huella: str, aceptar: bool, categoria: Categoria | None, motivo: str, ahora: datetime
    ) -> None:
        with self.estado.transaccion() as cx:
            cx.execute(
                """
                INSERT INTO clasificaciones(huella, aceptar, categoria, motivo, ts)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(huella) DO UPDATE SET aceptar = excluded.aceptar,
                    categoria = excluded.categoria, motivo = excluded.motivo, ts = excluded.ts
                """,
                (
                    huella,
                    int(aceptar),
                    categoria.value if categoria else None,
                    motivo,
                    a_texto(ahora),
                ),
            )
            cx.execute("DELETE FROM pendientes WHERE huella = ?", (huella,))

    # --- clasificación ----------------------------------------------------------------------

    def _aceptar(self, dudosa: Dudosa, categoria: Categoria | None, resultado) -> None:
        dudosa.vacante.categoria = categoria or self.filtros.categoria_por_terminos(dudosa.vacante)
        resultado.aceptadas.append(dudosa)

    def clasificar(self, nuevas: list[Dudosa], ahora: datetime) -> ResultadoClasificacion:
        """Clasifica las dudosas nuevas y las pendientes de corridas anteriores."""
        resultado = ResultadoClasificacion()
        vencimiento = timedelta(hours=self.config.horas_vencimiento_pendiente)

        por_huella: dict[str, Dudosa] = {}
        for dudosa, desde in self._cargar_pendientes():
            if ahora - desde > vencimiento:
                self._quitar_pendiente(dudosa.huella)
                resultado.vencidas.append(dudosa)
                log.warning(
                    "Dudosa descartada sin clasificar tras %s h: %s (%s)",
                    self.config.horas_vencimiento_pendiente,
                    dudosa.vacante.titulo,
                    dudosa.vacante.clave,
                )
            else:
                por_huella[dudosa.huella] = dudosa
        for dudosa in nuevas:
            por_huella.setdefault(dudosa.huella, dudosa)

        sin_clasificar: list[Dudosa] = []
        for dudosa in por_huella.values():
            cache = self._cache(dudosa.huella)
            if cache is None:
                sin_clasificar.append(dudosa)
                continue
            resultado.desde_cache += 1
            self._quitar_pendiente(dudosa.huella)
            aceptar, categoria = cache
            if aceptar:
                self._aceptar(dudosa, categoria, resultado)
            else:
                resultado.rechazadas.append(dudosa)

        if not sin_clasificar:
            return resultado

        if not self.config.activo or self.ia is None:
            for dudosa in sin_clasificar:
                self._quitar_pendiente(dudosa.huella)
                if self.config.politica_sin_ia == "aceptar":
                    self._aceptar(dudosa, None, resultado)
                else:
                    resultado.rechazadas.append(dudosa)
            return resultado

        tamanio = self.config.max_vacantes_por_llamada
        for inicio in range(0, len(sin_clasificar), tamanio):
            self._clasificar_lote(sin_clasificar[inicio : inicio + tamanio], ahora, resultado)
        return resultado

    def _clasificar_lote(
        self, lote: list[Dudosa], ahora: datetime, resultado: ResultadoClasificacion
    ) -> None:
        payload = {
            "vacantes": [
                {
                    "id": indice,
                    "titulo": d.vacante.titulo,
                    "empresa": d.vacante.empresa,
                    "ubicacion": d.vacante.ubicacion,
                    "modalidad": d.vacante.modalidad,
                    "salario": d.vacante.salario,
                    "palabra_clave": d.vacante.keyword,
                    "nivel_filtrado_por_fuente": d.vacante.fuente in self.fuentes_con_filtro_nivel,
                    "descripcion": d.vacante.descripcion,
                }
                for indice, d in enumerate(lote)
            ]
        }
        respuesta = self.ia.chat_json(
            "clasificador",
            self.config.prompt_sistema,
            payload,
            temperatura=self.config.temperatura,
            max_tokens=TOKENS_BASE + TOKENS_POR_VACANTE * len(lote),
        )
        if respuesta.realizada:
            resultado.llamadas += 1
        items: dict[int, ItemIA] = {}
        if respuesta.ok and respuesta.datos is not None:
            try:
                validada = RespuestaClasificador.model_validate(respuesta.datos)
                items = {item.id: item for item in validada.vacantes}
            except ValidationError:
                respuesta.motivo = "respuesta inválida"
        if not items:
            resultado.motivo_fallo = respuesta.motivo or "respuesta inválida"
            log.warning("Clasificador IA sin respuesta válida: %s", resultado.motivo_fallo)

        for indice, dudosa in enumerate(lote):
            item = items.get(indice)
            if item is None:
                self._guardar_pendiente(dudosa, ahora)
                resultado.pendientes.append(dudosa)
                continue
            categoria = None
            if item.categoria:
                try:
                    categoria = Categoria(item.categoria)
                except ValueError:
                    categoria = None  # se usa la categoría por términos
            if item.aceptar:
                self._aceptar(dudosa, categoria, resultado)
                categoria = dudosa.vacante.categoria
            else:
                resultado.rechazadas.append(dudosa)
            self._guardar_clasificacion(dudosa.huella, item.aceptar, categoria, item.motivo, ahora)
            log.info(
                "IA %s: %s (%s) — %s",
                "acepta" if item.aceptar else "rechaza",
                dudosa.vacante.titulo,
                categoria or "-",
                item.motivo,
            )
