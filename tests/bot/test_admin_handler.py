from unittest.mock import AsyncMock

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.base import StorageKey

from bot.handlers.admin import receive_telegram_id
from bot.states import NewStaffStates


def _fsm_context() -> FSMContext:
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=1, user_id=1)
    return FSMContext(storage=storage, key=key)


async def test_receive_telegram_id_creates_staff_user():
    message = AsyncMock()
    message.text = "555222"
    state = _fsm_context()
    await state.update_data(role="mechanic", full_name="Механик Вася")
    api = AsyncMock()
    api.create_staff_user.return_value = {"id": "u2", "full_name": "Механик Вася"}

    await receive_telegram_id(message, state, api=api)

    api.create_staff_user.assert_awaited_once_with(role="mechanic", full_name="Механик Вася", telegram_id=555222)
    assert (await state.get_state()) is None


async def test_receive_telegram_id_dash_means_skip():
    message = AsyncMock()
    message.text = "-"
    state = _fsm_context()
    await state.update_data(role="mechanic", full_name="Механик Вася")
    api = AsyncMock()
    api.create_staff_user.return_value = {"id": "u2", "full_name": "Механик Вася"}

    await receive_telegram_id(message, state, api=api)

    api.create_staff_user.assert_awaited_once_with(role="mechanic", full_name="Механик Вася", telegram_id=None)


async def test_receive_telegram_id_rejects_non_numeric():
    message = AsyncMock()
    message.text = "abc"
    state = _fsm_context()
    await state.set_state(NewStaffStates.waiting_for_telegram_id)
    await state.update_data(role="mechanic", full_name="Механик Вася")
    api = AsyncMock()

    await receive_telegram_id(message, state, api=api)

    api.create_staff_user.assert_not_awaited()
    message.answer.assert_awaited_once_with("Telegram ID должен быть числом или «-».")
    assert (await state.get_state()) == NewStaffStates.waiting_for_telegram_id.state
