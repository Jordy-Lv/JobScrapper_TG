"""Cliente de IA con la clave de cada usuario: salida JSON con esquema, cuota y topes.

Es genérico: lo propio de cada protocolo (gemini, openai, anthropic) vive en su adaptador.
Nunca se usa DeepSeek del buscador ni la clave de otro usuario. El contenido externo (CV,
vacante, preguntas pegadas) va delimitado como datos y toda salida se valida con pydantic.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, time
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from buscador_vacantes.asistente.datos import BaseAsistente
from buscador_vacantes.asistente.ia.anthropic import AdaptadorAnthropic
from buscador_vacantes.asistente.ia.contrato import INSTRUCCION_DATOS, Adaptador, Parte, Resultado
from buscador_vacantes.asistente.ia.errores import (
    CuotaAgotada,
    ErrorIA,
    ModeloNoDisponible,
    Saturado,
    TopeAlcanzado,
)
from buscador_vacantes.asistente.ia.gemini import AdaptadorGemini
from buscador_vacantes.asistente.ia.openai import AdaptadorOpenAI
from buscador_vacantes.asistente.preferencias import NIVEL_IA_DEFECTO, NIVELES_IA, Preferencias
from buscador_vacantes.comun import config as cfg
from buscador_vacantes.comun.estado import a_texto, ahora_utc
from buscador_vacantes.comun.fechas import ZONA

log = logging.getLogger(__name__)

M = TypeVar("M", bound=BaseModel)

ESPERA_MAXIMA_S = 20  # un 429 que pide esperar más se trata como cuota agotada
ESPERAS_SATURADO_S = (3, 8)  # 5xx: modelo saturado; dos reintentos y luego otro modelo
ADAPTADORES: dict[str, Callable[[cfg.ProveedorIA, httpx.AsyncClient], Adaptador]] = {
    "gemini": AdaptadorGemini,
    "openai": AdaptadorOpenAI,
    "anthropic": AdaptadorAnthropic,
}


class ClienteIA:
    """Cliente de un proveedor del catálogo; sin estado por usuario (la clave llega por llamada)."""

    def __init__(
        self,
        config: cfg.ProveedorIA,
        base: BaseAsistente,
        tope_usuario_dia: int,
        *,
        niveles: cfg.AsistenteNivelesIA | None = None,
        cliente: httpx.AsyncClient | None = None,
        reloj: Callable[[], datetime] = ahora_utc,
        dormir: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.config = config
        self.base = base
        self.tope = tope_usuario_dia
        self.niveles = niveles or cfg.AsistenteNivelesIA()
        self.preferencias = Preferencias(base)
        self.reloj = reloj
        self.dormir = dormir
        self.cliente = cliente or httpx.AsyncClient(
            base_url=config.base_url.rstrip("/") + "/", timeout=config.timeout_s
        )
        self.adaptador = ADAPTADORES[config.protocolo](config, self.cliente)

    @property
    def nombre(self) -> str:
        return self.config.nombre

    @property
    def acepta_pdf(self) -> bool:
        return self.config.acepta_pdf

    async def cerrar(self) -> None:
        await self.cliente.aclose()

    async def validar_clave(self, clave: str) -> bool:
        """Llamada mínima al proveedor. False si no acepta la clave."""
        return await self.adaptador.validar_clave(clave)

    # --- topes ---------------------------------------------------------------------

    def llamadas_hoy(self, usuario_id: int | None) -> int:
        inicio = datetime.combine(self.reloj().astimezone(ZONA).date(), time(0), tzinfo=ZONA)
        fila = self.base.cx.execute(
            # Solo cuentan las llamadas exitosas: un 503 del proveedor no gasta el tope del usuario
            "SELECT COUNT(*) FROM ia_uso WHERE usuario_id IS ? AND ts >= ? AND ok = 1",
            (usuario_id, a_texto(inicio)),
        ).fetchone()
        return fila[0]

    def _registrar(self, usuario_id, tarea, ok, tokens_in=0, tokens_out=0, motivo=None) -> None:
        with self.base.transaccion() as cx:
            cx.execute(
                "INSERT INTO ia_uso(usuario_id, ts, tarea, ok, tokens_in, tokens_out, motivo) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (usuario_id, a_texto(self.reloj()), tarea, int(ok), tokens_in, tokens_out, motivo),
            )

    # --- generación ----------------------------------------------------------------

    async def generar(
        self,
        tarea: cfg.NombreTarea,
        clave: str,
        usuario_id: int | None,
        instruccion: str,
        partes: list[Parte],
        esquema: type[M],
        *,
        nivel: str = NIVEL_IA_DEFECTO,
    ) -> M:
        """Una respuesta validada con ``esquema``, con el modelo del nivel efectivo.

        Reintenta una vez si el JSON es inválido. Si la cuota del nivel se agota (o llega al
        tope diario), baja de Máximo a Normal y de Normal a Ahorro en vez de fallar, y deja
        anotado que el usuario no pasa de ese nivel hoy (``Preferencias.bajar_nivel``)."""
        if nivel not in NIVELES_IA:
            nivel = NIVEL_IA_DEFECTO
        completa = f"{instruccion}\n\n{INSTRUCCION_DATOS}"
        bajando = list(reversed(NIVELES_IA[: NIVELES_IA.index(nivel) + 1]))  # nivel, …, ahorro
        intentados: set[tuple] = set()
        ultimo: ErrorIA | None = None
        for i, actual in enumerate(bajando):
            modelos, ajustes = self._modelos_del_nivel(tarea, actual)
            plan = (tuple(modelos), ajustes.pensamiento)
            if plan in intentados:
                continue  # el mismo modelo y razonamiento que ya agotó su cuota: no se repite
            intentados.add(plan)
            try:
                salida = await self._generar_en_nivel(
                    tarea, clave, usuario_id, completa, partes, esquema, modelos, ajustes
                )
            except (CuotaAgotada, TopeAlcanzado) as exc:
                ultimo = exc
                continue
            if i and usuario_id is not None:
                self.preferencias.bajar_nivel(usuario_id, actual, self.reloj())
            return salida
        raise ultimo or ErrorIA("La IA no respondió")

    def _modelos_del_nivel(
        self, tarea: cfg.NombreTarea, nivel: str
    ) -> tuple[list[str], cfg.TareaIA]:
        """La cadena de modelos y los ajustes de la tarea según el preset del nivel: ``ligero``
        usa el modelo de ``clasificar_pregunta``, ``maximo`` el ``modelo_maximo`` de la tarea
        (con su razonamiento) si el proveedor lo define, y ``configurado`` el de siempre."""
        ajustes = self.config.tareas[tarea]
        modo = getattr(self.niveles, nivel).modelo
        if modo == "ligero":
            ligero = self.config.tareas["clasificar_pregunta"]
            return [ligero.modelo, *ligero.respaldo], ajustes
        if modo == "maximo" and ajustes.modelo_maximo:
            pensamiento = ajustes.razonamiento_maximo or ajustes.pensamiento
            return [ajustes.modelo_maximo], ajustes.model_copy(update={"pensamiento": pensamiento})
        return [ajustes.modelo, *ajustes.respaldo], ajustes

    async def _generar_en_nivel(
        self, tarea, clave, usuario_id, instruccion, partes, esquema, modelos, ajustes
    ):
        if self.llamadas_hoy(usuario_id) >= self.tope:
            raise TopeAlcanzado(
                "Llegaste al tope diario de uso de la IA del asistente; se renueva mañana."
            )
        # Cadena de modelos: si uno está saturado, sin cuota o retirado, se usa el siguiente
        # (la cuota suele ser por modelo)
        ultimo: ErrorIA = ErrorIA("La IA no respondió")
        for modelo in modelos:
            try:
                return await self._generar_con(
                    tarea, clave, usuario_id, modelo, instruccion, partes, esquema, ajustes
                )
            except (Saturado, CuotaAgotada, ModeloNoDisponible) as exc:
                log.info("%s %s (%s) no disponible: %s", self.nombre, modelo, tarea,
                         type(exc).__name__)  # fmt: skip
                ultimo = exc
        raise ultimo

    async def _generar_con(
        self, tarea, clave, usuario_id, modelo, instruccion, partes, esquema: type[M], ajustes
    ) -> M:
        ultimo_error = "respuesta inválida"
        for _ in range(2):
            resultado = await self._llamar(
                tarea, clave, usuario_id, modelo, instruccion, partes, esquema, ajustes
            )
            try:
                return esquema.model_validate(json.loads(resultado.texto))
            except (ValueError, ValidationError) as exc:
                ultimo_error = f"JSON inválido: {type(exc).__name__}"
                log.warning("%s (%s) devolvió un JSON que no cumple el esquema", self.nombre, tarea)
        raise ErrorIA(f"La IA no devolvió una respuesta válida ({ultimo_error})")

    async def _llamar(
        self, tarea, clave, usuario_id, modelo, instruccion, partes, esquema, ajustes
    ) -> Resultado:
        esperas_saturado = list(ESPERAS_SATURADO_S)
        espero_429 = False
        while True:
            try:
                resultado = await self.adaptador.generar(
                    modelo, clave, instruccion, partes, esquema, ajustes
                )
            except ErrorIA as exc:
                self._registrar(usuario_id, tarea, False, motivo=exc.motivo or type(exc).__name__)
                if (
                    isinstance(exc, CuotaAgotada)
                    and not espero_429
                    and exc.espera_s is not None
                    and exc.espera_s <= ESPERA_MAXIMA_S
                ):
                    log.info("%s pidió esperar %.0f s (429)", self.nombre, exc.espera_s)
                    espero_429 = True
                    await self.dormir(exc.espera_s)
                    continue
                if isinstance(exc, Saturado) and esperas_saturado:
                    espera = esperas_saturado.pop(0)
                    log.info("%s %s saturado: reintento en %s s", self.nombre, modelo, espera)
                    await self.dormir(espera)
                    continue
                raise
            self._registrar(usuario_id, tarea, True, resultado.tokens_in, resultado.tokens_out)
            return resultado


def crear_clientes(
    ia: cfg.AsistenteIA, base: BaseAsistente, tope_usuario_dia: int, **opciones
) -> dict[str, ClienteIA]:
    """Un cliente por proveedor del catálogo, por id. ``opciones``: reloj, dormir, cliente."""
    return {
        id_: ClienteIA(proveedor, base, tope_usuario_dia, **opciones)
        for id_, proveedor in ia.proveedores.items()
    }
