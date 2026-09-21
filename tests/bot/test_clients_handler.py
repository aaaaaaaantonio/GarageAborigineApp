from unittest.mock import AsyncMock

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.base import StorageKey

from bot.handlers.clients import receive_full_name, start_new_client
from bot.states import NewClientStates


def _fsm_context() -> FSMContext:
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=1, user_id=1)
    return FSMContext(storage=storage, key=key)


async def test_start_new_client_asks_for_phone():
    message = AsyncMock()
    state = _fsm_context()

    await start_new_client(message, state)

    message.answer.assert_awaited_once()
    assert (await state.get_state()) == NewClientStates.waiting_for_phone.state


async def test_receive_full_name_creates_client_via_api():
    message = AsyncMock()
    message.text = "Иван Иванов"
    state = _fsm_context()
    await state.update_data(phone="79991234567")
    api = AsyncMock()
    api.create_client.return_value = {"id": "c1", "full_name": "Иван Иванов"}

    await receive_full_name(message, state, api=api)

    api.create_client.assert_awaited_once_with(full_name="Иван Иванов", phone="79991234567")
    assert (await state.get_state()) is None
    message.answer.assert_awaited()
