"""Adaptador de python-telegram-bot: traduce updates a la Conversacion y envía sus salidas."""

from __future__ import annotations

import logging
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, LinkPreviewOptions, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest, Forbidden
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from buscador_vacantes.asistente import textos as t
from buscador_vacantes.asistente.conversacion import Bloqueado, Botones, Conversacion
from buscador_vacantes.asistente.enlaces import PREFIJO_BOTON

log = logging.getLogger(__name__)

SIN_VISTA_PREVIA = LinkPreviewOptions(is_disabled=True)


def teclado(botones: Botones | None) -> InlineKeyboardMarkup | None:
    if not botones:
        return None
    filas = []
    for fila in botones:
        filas.append([
            InlineKeyboardButton(texto, url=destino[4:]) if destino.startswith("url:")
            else InlineKeyboardButton(texto, callback_data=destino[:64])
            for texto, destino in fila
        ])  # fmt: skip
    return InlineKeyboardMarkup(filas)


class SalidaTelegram:
    def __init__(self, bot) -> None:
        self.bot = bot

    async def enviar(self, chat_id: int, texto: str, botones: Botones | None = None) -> int | None:
        try:
            mensaje = await self.bot.send_message(
                chat_id, texto[:4096], parse_mode=ParseMode.HTML,
                link_preview_options=SIN_VISTA_PREVIA, reply_markup=teclado(botones),
            )  # fmt: skip
        except Forbidden as exc:
            raise Bloqueado(str(exc)) from exc
        return mensaje.message_id

    async def editar(self, chat_id: int, mensaje_id: int, texto: str,
                     botones: Botones | None = None) -> None:  # fmt: skip
        try:
            await self.bot.edit_message_text(
                texto[:4096], chat_id=chat_id, message_id=mensaje_id, parse_mode=ParseMode.HTML,
                link_preview_options=SIN_VISTA_PREVIA, reply_markup=teclado(botones),
            )  # fmt: skip
        except BadRequest as exc:
            if "not modified" not in str(exc).lower():
                raise

    async def documento(self, chat_id: int, ruta: Path, texto: str | None = None) -> None:
        try:
            with ruta.open("rb") as archivo:
                await self.bot.send_document(chat_id, archivo, filename=ruta.name, caption=texto)
        except Forbidden as exc:
            raise Bloqueado(str(exc)) from exc

    async def borrar(self, chat_id: int, mensaje_id: int) -> None:
        await self.bot.delete_message(chat_id, mensaje_id)


def crear_aplicacion(token: str, conversacion_de, max_mb: float, bot_usuario: str) -> Application:
    """``conversacion_de(bot)`` crea la Conversacion con la salida de ese bot."""
    aplicacion = Application.builder().token(token).concurrent_updates(True).build()
    privado = filters.ChatType.PRIVATE
    estado: dict[str, Conversacion] = {}

    def conv(contexto: ContextTypes.DEFAULT_TYPE) -> Conversacion:
        if "c" not in estado:
            estado["c"] = conversacion_de(contexto.bot)
        return estado["c"]

    async def iniciar(update: Update, contexto: ContextTypes.DEFAULT_TYPE) -> None:
        u = update.effective_user
        payload = contexto.args[0] if contexto.args else None
        await conv(contexto).al_iniciar(u.id, u.full_name, payload)

    async def comando(update: Update, contexto: ContextTypes.DEFAULT_TYPE) -> None:
        partes = (update.message.text or "").split()
        nombre = partes[0][1:].split("@")[0].lower()
        await conv(contexto).al_comando(update.effective_user.id, nombre, partes[1:])

    async def texto(update: Update, contexto: ContextTypes.DEFAULT_TYPE) -> None:
        m = update.message
        await conv(contexto).al_texto(update.effective_user.id, m.text or "", m.message_id)

    async def documento(update: Update, contexto: ContextTypes.DEFAULT_TYPE) -> None:
        d = update.message.document
        if d.file_size and d.file_size > max_mb * 1024 * 1024:
            await update.message.reply_text(f"❌ El archivo supera {max_mb:g} MB.")
            return
        archivo = await d.get_file()
        contenido = bytes(await archivo.download_as_bytearray())
        await conv(contexto).al_documento(update.effective_user.id, contenido, d.file_name)

    async def boton(update: Update, contexto: ContextTypes.DEFAULT_TYPE) -> None:
        consulta = update.callback_query
        dato = consulta.data or ""
        if dato.startswith(PREFIJO_BOTON):
            # Botón ⚡ de un mensaje del canal: se postula sin salir del canal
            r = await conv(contexto).al_toque_canal(
                update.effective_user.id, dato.removeprefix(PREFIJO_BOTON)
            )
            await consulta.answer(r.texto or None, show_alert=r.alerta, url=r.url)
            return
        respuesta = await conv(contexto).al_boton(update.effective_user.id, dato)
        await consulta.answer(respuesta)

    async def en_grupo(update: Update, contexto: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(t.EN_GRUPO.format(enlace=f"https://t.me/{bot_usuario}"))

    async def error(update: object, contexto: ContextTypes.DEFAULT_TYPE) -> None:
        log.error("Error atendiendo un update", exc_info=contexto.error)

    aplicacion.add_handler(CommandHandler("start", iniciar, filters=privado))
    aplicacion.add_handler(MessageHandler(privado & filters.COMMAND, comando))
    aplicacion.add_handler(MessageHandler(privado & filters.Document.ALL, documento))
    aplicacion.add_handler(MessageHandler(privado & filters.TEXT & ~filters.COMMAND, texto))
    aplicacion.add_handler(CallbackQueryHandler(boton))
    aplicacion.add_handler(MessageHandler(filters.ChatType.GROUPS & filters.COMMAND, en_grupo))
    aplicacion.add_error_handler(error)
    return aplicacion
