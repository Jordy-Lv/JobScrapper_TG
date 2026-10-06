"""Servicio del asistente: bot, API y tareas periódicas en un solo proceso asyncio.

Se ejecuta con `uv run buscador.py asistente servicio` (unidad buscador-asistente.service).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import shutil
import signal
from datetime import datetime, timedelta
from pathlib import Path

import uvicorn
from telegram import Update

from buscador_vacantes import config as cfg
from buscador_vacantes.asistente.api import crear_app
from buscador_vacantes.asistente.bot import SalidaTelegram, crear_aplicacion
from buscador_vacantes.asistente.cifrado import Cifrador
from buscador_vacantes.asistente.conversacion import Conversacion
from buscador_vacantes.asistente.datos import BaseAsistente, abrir_vacantes_ro
from buscador_vacantes.asistente.detalle import Detalles
from buscador_vacantes.asistente.ia import crear_clientes
from buscador_vacantes.asistente.membresia import Comprobador
from buscador_vacantes.asistente.nucleo import Nucleo
from buscador_vacantes.asistente.respuestas import sembrar_banco
from buscador_vacantes.asistente.vacantes import Indice
from buscador_vacantes.estado import a_texto, ahora_utc, de_texto

log = logging.getLogger(__name__)

INTERVALO_TAREAS_S = 60
INTERVALO_INDICE_S = 300


def ruta(ruta_: Path) -> Path:
    ruta_ = ruta_.expanduser()
    return ruta_ if ruta_.is_absolute() else cfg.RAIZ / ruta_


def construir_nucleo(configuracion: cfg.Configuracion, secretos: cfg.Secretos) -> Nucleo:
    asistente = configuracion.asistente
    assert asistente is not None
    cifrador = Cifrador(secretos.asistente_clave_cifrado)
    base = BaseAsistente.abrir(ruta(asistente.base_datos))
    cifrador.comprobar(base)
    archivos = ruta(asistente.archivos)
    archivos.mkdir(parents=True, exist_ok=True)
    os.chmod(archivos, 0o700)
    ro = abrir_vacantes_ro(ruta(asistente.vacantes_db or configuracion.rutas.base_datos))
    indice = Indice(base, ro, asistente.retencion_dias)
    detalles = Detalles(base, ro, asistente.detalle, configuracion.red)
    ia = crear_clientes(asistente.ia, base, asistente.topes.ia_usuario_dia)
    nucleo = Nucleo(configuracion, base, indice, detalles, ia, cifrador, archivos)
    nucleo.enlace_grupo = enlace_grupo(asistente, secretos)
    sembrar_banco(base, ahora_utc())
    nucleo.cargar_selectores()
    return nucleo


def enlace_grupo(asistente: cfg.Asistente, secretos: cfg.Secretos) -> str | None:
    """Enlace al grupo de vacantes para la extensión.

    Sin invitación configurada se usa t.me/c/<id>, que Telegram abre solo a los miembros.
    """
    if asistente.grupo.enlace:
        return asistente.grupo.enlace
    chat = str(asistente.grupo.chat_id or secretos.telegram_chat_id or "")
    if chat.startswith("-100") and chat[4:].isdigit():
        return f"https://t.me/c/{chat[4:]}/1"
    return None


class Servicio:
    def __init__(self, configuracion: cfg.Configuracion, secretos: cfg.Secretos) -> None:
        self.configuracion = configuracion
        self.config = configuracion.asistente
        self.secretos = secretos
        self.nucleo = construir_nucleo(configuracion, secretos)
        self.detener = asyncio.Event()
        self.conversacion: Conversacion | None = None

    def _comprobador(self, bot) -> Comprobador:
        chat = self.config.grupo.chat_id or self.secretos.telegram_chat_id
        return Comprobador(bot, chat, self.nucleo.usuarios, self.config.grupo.cache_min,
                           self._avisar_dueno)  # fmt: skip

    async def _avisar_dueno(self, texto: str) -> None:
        if self.conversacion and self.config.dueno_telegram_id:
            await self.conversacion._enviar(self.config.dueno_telegram_id, texto)

    def _crear_conversacion(self, bot) -> Conversacion:
        if self.conversacion is None:
            self.conversacion = Conversacion(
                self.nucleo, SalidaTelegram(bot), self._comprobador(bot)
            )
            self.nucleo.notificador = self.conversacion.notificar
        return self.conversacion

    async def tareas_periodicas(self, bot) -> None:
        conversacion = self._crear_conversacion(bot)
        for evento in self.nucleo.cola.recuperar_al_arrancar(self.nucleo.ahora()):
            await conversacion.notificar(evento)
        ultimo_indice = 0.0
        while not self.detener.is_set():
            ahora = self.nucleo.ahora()
            try:
                if asyncio.get_running_loop().time() - ultimo_indice >= INTERVALO_INDICE_S:
                    self.nucleo.indice.indexar(ahora)
                    for p in await self.nucleo.encolar_automaticos():
                        usuario = self.nucleo.usuarios.por_id(p.usuario_id)
                        if usuario:
                            await conversacion.procesar_toque(usuario, p.id_corto,
                                                              origen="automatico")  # fmt: skip
                    ultimo_indice = asyncio.get_running_loop().time()
                for evento in self.nucleo.cola.vigilar(ahora):
                    await conversacion.notificar(evento)
                await conversacion.recordatorios(ahora)
                await conversacion.borrar_vencidos(ahora)
                await self._tareas_diarias(conversacion, ahora)
            except Exception:  # noqa: BLE001 - una tarea fallida no detiene el servicio
                log.exception("Error en las tareas periódicas")
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self.detener.wait(), INTERVALO_TAREAS_S)

    async def _tareas_diarias(self, conversacion: Conversacion, ahora: datetime) -> None:
        base = self.nucleo.base
        ultima = de_texto(base.kv_obtener("tareas_diarias"))
        if ultima and ahora - ultima < timedelta(hours=self.config.grupo.comprobar_cada_h):
            return
        base.kv_guardar("tareas_diarias", a_texto(ahora))
        await conversacion.comprobador.comprobar_todos(ahora)
        for usuario in self.nucleo.usuarios.por_avisar_inactividad(
            ahora, self.config.inactividad_meses
        ):
            await conversacion._enviar(usuario, "Hace mucho no usas el asistente. Si no respondes "
                                                "en 30 días borraré tus datos. Escribe /estado "
                                                "para conservarlos.")  # fmt: skip
            self.nucleo.usuarios.marcar_aviso_inactividad(usuario, ahora)
        for usuario in self.nucleo.usuarios.por_borrar_inactividad(ahora):
            self.nucleo.usuarios.borrar(usuario, ahora)
        self._limpiar_evidencia(ahora)

    def _limpiar_evidencia(self, ahora: datetime) -> None:
        limite = a_texto(ahora - timedelta(days=self.config.evidencia_dias))
        base = self.nucleo.base
        viejas = base.cx.execute("SELECT id, archivo FROM evidencia WHERE ts < ?", (limite,))
        for fila in viejas.fetchall():
            Path(fila["archivo"]).unlink(missing_ok=True)
        with base.transaccion() as cx:
            cx.execute("DELETE FROM evidencia WHERE ts < ?", (limite,))
        carpeta = self.nucleo.archivos / "postulaciones"
        if carpeta.is_dir():
            for sub in carpeta.iterdir():
                if sub.is_dir() and not any(sub.iterdir()):
                    shutil.rmtree(sub, ignore_errors=True)

    async def ejecutar(self) -> None:
        bucle = asyncio.get_running_loop()
        for senal in (signal.SIGTERM, signal.SIGINT):
            with contextlib.suppress(NotImplementedError):
                bucle.add_signal_handler(senal, self.detener.set)
        aplicacion = crear_aplicacion(
            self.secretos.asistente_bot_token, self._crear_conversacion, self.config.cv.max_mb,
            self.config.bot_usuario,
        )  # fmt: skip
        servidor = uvicorn.Server(uvicorn.Config(
            crear_app(self.nucleo), host=self.config.api.host, port=self.config.api.puerto,
            log_level="warning", access_log=False,
        ))  # fmt: skip
        servidor.install_signal_handlers = lambda: None
        async with aplicacion:
            await aplicacion.start()
            # Se piden todos los tipos de update: Telegram recuerda el último filtro usado y sin
            # esto el bot podría dejar de recibir los toques de botones (callback_query)
            await aplicacion.updater.start_polling(
                drop_pending_updates=False, allowed_updates=Update.ALL_TYPES
            )
            self._crear_conversacion(aplicacion.bot)
            log.info("Asistente en marcha: bot @%s y API en %s:%s", self.config.bot_usuario,
                     self.config.api.host, self.config.api.puerto)  # fmt: skip
            tareas = [asyncio.create_task(servidor.serve()),
                      asyncio.create_task(self.tareas_periodicas(aplicacion.bot))]  # fmt: skip
            await self.detener.wait()
            log.info("Deteniendo el asistente")
            servidor.should_exit = True
            await aplicacion.updater.stop()
            await aplicacion.stop()
            if self.conversacion:
                await self.conversacion.esperar_tareas()
            await asyncio.gather(*tareas, return_exceptions=True)
        for cliente in self.nucleo.ia.values():
            await cliente.cerrar()
        await self.nucleo.detalles.cerrar()
        self.nucleo.base.cerrar()
