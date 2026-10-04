from unittest.mock import AsyncMock, patch

import pytest
from aiogram.exceptions import TelegramUnauthorizedError
from aiogram.methods import GetMe

from bot.main import create_bot

VALID_SHAPE = "123456789:AAEexampleexampleexampleexample1234"


@pytest.mark.parametrize("token", ["", "not-a-token", "mybot_name_here"])
async def test_create_bot_rejects_malformed_token_with_short_message(token, caplog):
    with pytest.raises(SystemExit) as exc:
        await create_bot(token)

    assert exc.value.code == 1
    assert "BOT_TOKEN" in caplog.text
    assert "Traceback" not in caplog.text


async def test_create_bot_rejects_token_telegram_does_not_accept(caplog):
    unauthorized = TelegramUnauthorizedError(method=GetMe(), message="Unauthorized")
    with patch("aiogram.Bot.get_me", AsyncMock(side_effect=unauthorized)):
        with pytest.raises(SystemExit) as exc:
            await create_bot(VALID_SHAPE)

    assert exc.value.code == 1
    assert "BOT_TOKEN" in caplog.text


async def test_create_bot_returns_bot_for_accepted_token():
    with patch("aiogram.Bot.get_me", AsyncMock(return_value=AsyncMock(username="garage_bot"))):
        bot = await create_bot(VALID_SHAPE)

    assert bot.token == VALID_SHAPE
    await bot.session.close()


from aiogram.exceptions import TelegramNetworkError
from aiogram.methods import SetMyCommands

from bot.main import BOT_COMMANDS, set_commands


async def test_set_commands_registers_menu_commands():
    bot = AsyncMock()

    await set_commands(bot)

    bot.set_my_commands.assert_awaited_once_with(BOT_COMMANDS)
    assert [c.command for c in BOT_COMMANDS] == ["start", "cancel", "new_client", "new_vehicle"]


async def test_set_commands_failure_does_not_stop_startup(caplog):
    bot = AsyncMock()
    bot.set_my_commands.side_effect = TelegramNetworkError(method=SetMyCommands(commands=[]), message="timeout")

    await set_commands(bot)

    assert "Could not register bot commands" in caplog.text
