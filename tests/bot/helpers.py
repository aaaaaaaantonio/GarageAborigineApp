"""Event mocks for screen/wizard tests.

`MagicMock(spec=...)` passes isinstance checks (nav tells callbacks from
messages that way); aiogram's methods return awaitables rather than
coroutines, so each one used is replaced with an AsyncMock explicitly.
"""
from unittest.mock import AsyncMock, MagicMock

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

MASTER = {"id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "role": "master"}
ADMIN = {"id": "cccccccc-cccc-cccc-cccc-cccccccccccc", "role": "admin"}
MECHANIC = {"id": "dddddddd-dddd-dddd-dddd-dddddddddddd", "role": "mechanic"}


def fsm_context() -> FSMContext:
    return FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=1, user_id=1))


def make_message(text: str | None = None, message_id: int = 5) -> MagicMock:
    message = MagicMock(spec=Message)
    message.text = text
    message.message_id = message_id
    message.chat = MagicMock(id=1)
    message.bot = AsyncMock()
    # A message the bot sends gets id = this id + 100.
    message.answer = AsyncMock(return_value=MagicMock(message_id=message_id + 100))
    message.edit_text = AsyncMock()
    message.answer_document = AsyncMock()
    return message


def make_callback(data: str, message_id: int = 5) -> MagicMock:
    callback = MagicMock(spec=CallbackQuery)
    callback.data = data
    callback.message = make_message(message_id=message_id)
    callback.bot = callback.message.bot
    callback.answer = AsyncMock()
    return callback


def buttons(markup: InlineKeyboardMarkup) -> list[tuple[str, str]]:
    return [(b.text, b.callback_data) for row in markup.inline_keyboard for b in row]


def shown(event) -> tuple[str, InlineKeyboardMarkup]:
    """Text and markup last drawn for `event`: an edit for a callback, a new message otherwise."""
    call = event.message.edit_text.await_args if isinstance(event, CallbackQuery) else event.answer.await_args
    return call.args[0], call.kwargs["reply_markup"]


async def on_screens(state: FSMContext, *screens: tuple[str, dict], msg_id: int = 5) -> None:
    """Put the user on a stack: menu + `screens`, live message `msg_id`."""
    await state.update_data(nav_stack=[["menu", {}], *[[name, args] for name, args in screens]], nav_msg_id=msg_id)
