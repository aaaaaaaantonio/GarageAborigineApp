from unittest.mock import AsyncMock

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.base import StorageKey

from bot.handlers.consent import receive_paper_full_name, start_paper_consent


def _fsm_context() -> FSMContext:
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=1, user_id=1)
    return FSMContext(storage=storage, key=key)


async def test_receive_paper_full_name_registers_via_api():
    message = AsyncMock()
    message.text = "Пётр Петров"
    api = AsyncMock()
    api.register_paper_consent.return_value = {"client_id": "c1"}
    state = _fsm_context()
    await state.update_data(phone="79997654321")

    await receive_paper_full_name(message, state, api=api)

    api.register_paper_consent.assert_awaited_once_with(full_name="Пётр Петров", phone="79997654321")
    message.answer.assert_awaited_once_with("Клиент зарегистрирован (бумажное согласие): Пётр Петров")
    assert (await state.get_state()) is None


async def test_start_paper_consent_asks_for_phone():
    message = AsyncMock()
    state = _fsm_context()

    await start_paper_consent(message, state)

    message.answer.assert_awaited_once_with("Введите телефон клиента:")
    assert (await state.get_state()) is not None
