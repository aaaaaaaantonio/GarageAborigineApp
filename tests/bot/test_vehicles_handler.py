from unittest.mock import AsyncMock

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.base import StorageKey

from bot.handlers.vehicles import receive_make_model, start_new_vehicle
from bot.states import NewVehicleStates


def _fsm_context() -> FSMContext:
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=1, user_id=1)
    return FSMContext(storage=storage, key=key)


async def test_start_new_vehicle_asks_for_vin():
    message = AsyncMock()
    state = _fsm_context()

    await start_new_vehicle(message, state)

    assert (await state.get_state()) == NewVehicleStates.waiting_for_vin.state


async def test_receive_make_model_creates_vehicle_via_api():
    message = AsyncMock()
    message.text = "Toyota Camry"
    state = _fsm_context()
    await state.update_data(vin="X" * 17, plate_number="А123")
    api = AsyncMock()
    api.create_vehicle.return_value = {"id": "v1", "vin": "X" * 17}

    await receive_make_model(message, state, api=api)

    api.create_vehicle.assert_awaited_once_with(
        vin="X" * 17, plate_number="А123", make="Toyota", model="Camry"
    )
    assert (await state.get_state()) is None
