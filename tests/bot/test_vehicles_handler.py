from datetime import date
from unittest.mock import AsyncMock

from bot.handlers.vehicles import receive_make_model, start_new_vehicle
from bot.states import NewVehicleStates, NewVisitStates
from tests.bot.helpers import MASTER, MECHANIC, fsm_context, make_message, on_screens, shown

C1 = "11111111-1111-1111-1111-111111111111"
CAR = "44444444-4444-4444-4444-444444444444"


async def test_new_vehicle_command_asks_for_vin():
    state = fsm_context()
    message = make_message("/new_vehicle")

    await start_new_vehicle(message, state, api=AsyncMock(), user=MASTER)

    assert await state.get_state() == NewVehicleStates.waiting_for_vin.state
    assert shown(message)[0] == "Введите VIN:"


async def test_new_vehicle_refused_for_mechanic():
    message = make_message("/new_vehicle")

    await start_new_vehicle(message, fsm_context(), api=AsyncMock(), user=MECHANIC)

    message.answer.assert_awaited_once_with("Недостаточно прав.")


async def test_standalone_vehicle_is_created_without_owner():
    state = fsm_context()
    await on_screens(state)
    await state.set_state(NewVehicleStates.waiting_for_make_model)
    await state.update_data(wiz_name="new_vehicle", wiz_steps=[], vin="X" * 17, plate_number="А123ВС77")
    api = AsyncMock()
    api.create_vehicle.return_value = {"id": CAR, "vin": "X" * 17}
    message = make_message("Toyota Camry")

    await receive_make_model(message, state, api=api, user=MASTER)

    api.create_vehicle.assert_awaited_once_with(vin="X" * 17, plate_number="А123ВС77", make="Toyota", model="Camry")
    api.attach_owner.assert_not_awaited()
    assert shown(message)[0] == f"Автомобиль создан: {'X' * 17}\n\nГлавное меню"


async def test_vehicle_in_new_visit_is_linked_to_client_and_asks_mileage():
    state = fsm_context()
    await on_screens(state)
    await state.set_state(NewVehicleStates.waiting_for_make_model)
    await state.update_data(wiz_name="new_visit", wiz_steps=[], client_id=C1, vin="X" * 17, plate_number="А1")
    api = AsyncMock()
    api.create_vehicle.return_value = {"id": CAR, "vin": "X" * 17}
    message = make_message("Toyota Camry")

    await receive_make_model(message, state, api=api, user=MASTER)

    api.attach_owner.assert_awaited_once_with(CAR, C1, date_from=date.today().isoformat())
    assert (await state.get_data())["vehicle_id"] == CAR
    assert await state.get_state() == NewVisitStates.waiting_for_mileage.state
    assert shown(message)[0] == f"Автомобиль создан: {'X' * 17}\nВведите пробег на приёмке:"
    assert (await state.get_data())["wiz_steps"] == []
