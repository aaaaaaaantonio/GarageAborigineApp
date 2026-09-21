from unittest.mock import AsyncMock

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.base import StorageKey

from bot.handlers.visits import receive_mileage, send_visit_card
from bot.states import NewVisitStates


def _fsm_context() -> FSMContext:
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=1, user_id=1)
    return FSMContext(storage=storage, key=key)


async def test_receive_mileage_creates_visit_via_api():
    message = AsyncMock()
    message.text = "45000"
    state = _fsm_context()
    await state.set_state(NewVisitStates.waiting_for_mileage)
    await state.update_data(client_id="c1", vehicle_id="v1", master_id="m1")
    api = AsyncMock()
    api.create_visit.return_value = {"id": "visit1", "status": "received"}

    await receive_mileage(message, state, api=api)

    api.create_visit.assert_awaited_once_with(
        client_id="c1", vehicle_id="v1", assigned_master_id="m1", mileage_at_intake=45000
    )
    assert (await state.get_state()) is None


async def test_send_visit_card_shows_status_buttons():
    message = AsyncMock()
    visit = {"id": "visit1", "status": "received", "total_amount": "0.00"}

    await send_visit_card(message, visit)

    message.answer.assert_awaited_once()
    _, kwargs = message.answer.await_args
    assert kwargs["reply_markup"] is not None
