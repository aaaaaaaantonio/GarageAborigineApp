from unittest.mock import AsyncMock

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.base import StorageKey

from bot.handlers.vehicles import receive_make_model, start_new_vehicle
from bot.states import NewVehicleStates, NewVisitStates


def _fsm_context() -> FSMContext:
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=1, user_id=1)
    return FSMContext(storage=storage, key=key)


async def test_start_new_vehicle_asks_for_vin():
    message = AsyncMock()
    state = _fsm_context()

    await start_new_vehicle(message, state, user={"role": "master"})

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


async def test_receive_make_model_continues_new_visit_wizard_when_return_flow_set():
    message = AsyncMock()
    message.text = "Toyota Camry"
    state = _fsm_context()
    await state.update_data(vin="X" * 17, plate_number="А123", return_flow="new_visit", client_id="c1")
    api = AsyncMock()
    api.create_vehicle.return_value = {"id": "v1", "vin": "X" * 17}

    await receive_make_model(message, state, api=api)

    assert (await state.get_state()) == NewVisitStates.waiting_for_mileage.state
    data = await state.get_data()
    assert data["vehicle_id"] == "v1"


async def test_receive_make_model_links_new_vehicle_to_client_in_new_visit_flow():
    from datetime import date

    message = AsyncMock()
    message.text = "Toyota Camry"
    state = _fsm_context()
    await state.update_data(vin="X" * 17, plate_number="А123", return_flow="new_visit", client_id="c1")
    api = AsyncMock()
    api.create_vehicle.return_value = {"id": "v1", "vin": "X" * 17}

    await receive_make_model(message, state, api=api)

    api.attach_owner.assert_awaited_once_with("v1", "c1", date_from=date.today().isoformat())


async def test_receive_make_model_standalone_does_not_attach_owner():
    message = AsyncMock()
    message.text = "Toyota Camry"
    state = _fsm_context()
    await state.update_data(vin="X" * 17, plate_number="А123")
    api = AsyncMock()
    api.create_vehicle.return_value = {"id": "v1", "vin": "X" * 17}

    await receive_make_model(message, state, api=api)

    api.attach_owner.assert_not_awaited()


async def test_start_new_vehicle_rejects_mechanic():
    message = AsyncMock()
    state = _fsm_context()

    await start_new_vehicle(message, state, user={"role": "mechanic"})

    message.answer.assert_awaited_once_with("Недостаточно прав.")
    assert (await state.get_state()) is None
