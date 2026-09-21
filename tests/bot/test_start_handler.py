from unittest.mock import AsyncMock

from bot.handlers.start import cmd_start


async def test_start_shows_role_appropriate_menu():
    message = AsyncMock()
    user = {"id": "u1", "role": "mechanic"}

    await cmd_start(message, user=user)

    message.answer.assert_awaited_once()
    args, kwargs = message.answer.await_args
    assert "Мои работы" in [b.text for row in kwargs["reply_markup"].keyboard for b in row]
