from unittest.mock import AsyncMock

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from bot.handlers.start import cmd_cancel, cmd_start
from bot.states import NewVisitStates


def _fsm_context() -> FSMContext:
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=1, user_id=1)
    return FSMContext(storage=storage, key=key)


async def test_start_shows_role_appropriate_menu():
    message = AsyncMock()
    user = {"id": "u1", "role": "mechanic"}
    state = _fsm_context()

    await cmd_start(message, user=user, state=state)

    message.answer.assert_awaited_once()
    args, kwargs = message.answer.await_args
    assert "Мои работы" in [b.text for row in kwargs["reply_markup"].keyboard for b in row]


async def test_start_clears_pending_wizard_state():
    message = AsyncMock()
    state = _fsm_context()
    await state.set_state(NewVisitStates.waiting_for_mileage)
    await state.update_data(return_flow="new_visit")

    await cmd_start(message, user={"id": "u1", "role": "mechanic"}, state=state)

    assert (await state.get_state()) is None
    assert (await state.get_data()) == {}


async def test_cancel_clears_state_and_confirms():
    message = AsyncMock()
    state = _fsm_context()
    await state.set_state(NewVisitStates.waiting_for_mileage)
    await state.update_data(return_flow="new_visit")

    await cmd_cancel(message, state=state)

    assert (await state.get_state()) is None
    assert (await state.get_data()) == {}
    message.answer.assert_awaited_once_with("Действие отменено.")
