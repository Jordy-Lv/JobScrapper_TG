import asyncio
from types import SimpleNamespace

import pytest

pytest.importorskip("telegram")

from telegram.error import BadRequest, Forbidden  # noqa: E402

from buscador_vacantes.asistente.bot import SalidaTelegram  # noqa: E402
from buscador_vacantes.asistente.conversacion import Bloqueado  # noqa: E402


class BotFalso:
    def __init__(self, rechaza=None):
        self.rechaza = rechaza  # error que lanza el envío con efecto
        self.llamadas = []

    async def send_message(self, chat_id, texto, **kwargs):
        self.llamadas.append(kwargs)
        if self.rechaza and "message_effect_id" in kwargs:
            raise self.rechaza
        return SimpleNamespace(message_id=7)


def enviar(bot, **kwargs):
    return asyncio.run(SalidaTelegram(bot).enviar(1, "hola", **kwargs))


def test_sin_efecto_no_manda_message_effect_id():
    bot = BotFalso()
    assert enviar(bot) == 7
    assert "message_effect_id" not in bot.llamadas[0]


def test_con_efecto_lo_manda_a_telegram():
    bot = BotFalso()
    assert enviar(bot, efecto="123") == 7
    assert bot.llamadas[0]["message_effect_id"] == "123" and len(bot.llamadas) == 1


def test_si_telegram_rechaza_el_efecto_reenvia_sin_efecto():
    bot = BotFalso(rechaza=BadRequest("Effect_id_invalid"))
    assert enviar(bot, efecto="123") == 7
    assert len(bot.llamadas) == 2 and "message_effect_id" not in bot.llamadas[1]


def test_un_error_sin_efecto_no_se_reintenta():
    class Roto(BotFalso):
        async def send_message(self, chat_id, texto, **kwargs):
            raise BadRequest("Message is too long")

    with pytest.raises(BadRequest):
        enviar(Roto())


def test_usuario_que_bloqueo_al_bot_con_efecto_levanta_bloqueado():
    with pytest.raises(Bloqueado):
        enviar(BotFalso(rechaza=Forbidden("bot was blocked")), efecto="123")
