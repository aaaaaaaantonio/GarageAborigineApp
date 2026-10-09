"""Adding a client or a car when search finds nothing, and from the client card."""
from datetime import date
from unittest.mock import AsyncMock

from bot.api_client import ApiConflict
from bot.handlers.clients import receive_full_name, receive_phone
from bot.handlers.vehicles import add_vehicle_callback, receive_make_model, receive_plate, receive_vin
from bot.handlers.visits import add_client_callback, add_vehicle_in_visit_callback, receive_client_query
from bot.states import NewClientStates, NewVehicleStates, NewVisitStates
from bot.validators import PHONE_FORMAT_ERROR, VIN_FORMAT_ERROR
from tests.bot.helpers import MASTER, MECHANIC, buttons, fsm_context, make_callback, make_message, on_screens, shown

C1 = "11111111-1111-1111-1111-111111111111"
CAR = "44444444-4444-4444-4444-444444444444"
VIN = "JTDBR32E720012345"


async def _at(state, step, wiz_name="new_visit", **data):
    await on_screens(state)
    await state.set_state(step)
    await state.update_data(wiz_name=wiz_name, wiz_steps=[], **data)


# --- client not found in the new-visit wizard


async def test_another_query_on_client_not_found_searches_again():
    state = fsm_context()
    await _at(state, NewVisitStates.client_not_found, client_query="Петров")
    api = AsyncMock()
    api.search.return_value = [{"entity": "client", "id": C1}]
    api.get_client.return_value = {"id": C1, "full_name": "Петров Иван"}
    message = make_message("Петров Иван")

    await receive_client_query(message, state, api=api, user=MASTER)

    assert await state.get_state() == NewVisitStates.choosing_client.state


async def test_add_client_with_phone_query_asks_only_name():
    state = fsm_context()
    await _at(state, NewVisitStates.client_not_found, client_query="8 999 123-45-67")
    callback = make_callback("client_add")

    await add_client_callback(callback, state, api=AsyncMock(), user=MASTER)

    assert await state.get_state() == NewClientStates.waiting_for_full_name.state
    assert (await state.get_data())["phone"] == "8 999 123-45-67"


async def test_add_client_with_name_query_asks_phone_then_creates():
    state = fsm_context()
    await _at(state, NewVisitStates.client_not_found, client_query="Петров Иван")
    api = AsyncMock()
    api.create_client.return_value = {"id": C1, "full_name": "Петров Иван"}

    callback = make_callback("client_add")
    await add_client_callback(callback, state, api=api, user=MASTER)
    assert await state.get_state() == NewClientStates.waiting_for_phone.state

    message = make_message("+7 999 123-45-67")
    await receive_phone(message, state, api=api, user=MASTER)

    api.create_client.assert_awaited_once_with(full_name="Петров Иван", phone="+7 999 123-45-67")
    assert await state.get_state() == NewVisitStates.waiting_for_vehicle_query.state


async def test_add_client_with_unclear_query_asks_phone_and_name():
    state = fsm_context()
    await _at(state, NewVisitStates.client_not_found, client_query="12")
    callback = make_callback("client_add")

    await add_client_callback(callback, state, api=AsyncMock(), user=MASTER)

    assert await state.get_state() == NewClientStates.waiting_for_phone.state
    data = await state.get_data()
    assert not data["phone"] and not data["full_name"]


async def test_invalid_phone_is_asked_again():
    state = fsm_context()
    await _at(state, NewClientStates.waiting_for_phone)
    message = make_message("12345")

    await receive_phone(message, state, api=AsyncMock(), user=MASTER)

    assert await state.get_state() == NewClientStates.waiting_for_phone.state
    assert shown(message)[0] == f"{PHONE_FORMAT_ERROR}\n\nВведите телефон клиента:"


async def test_taken_phone_returns_to_phone_step():
    state = fsm_context()
    await _at(state, NewClientStates.waiting_for_full_name, phone="79991234567")
    api = AsyncMock()
    api.create_client.side_effect = ApiConflict("Клиент с таким телефоном уже есть")
    message = make_message("Иван")

    await receive_full_name(message, state, api=api, user=MASTER)

    assert await state.get_state() == NewClientStates.waiting_for_phone.state
    assert shown(message)[0] == "Клиент с таким телефоном уже есть\n\nВведите телефон клиента:"


# --- car not found in the new-visit wizard


async def test_add_vehicle_with_plate_query_asks_vin_then_skips_plate():
    state = fsm_context()
    await _at(state, NewVisitStates.vehicle_not_found, client_id=C1, vehicle_query="а123вс77")
    callback = make_callback("vehicle_add")

    await add_vehicle_in_visit_callback(callback, state, api=AsyncMock(), user=MASTER)

    assert await state.get_state() == NewVehicleStates.waiting_for_vin.state
    assert (await state.get_data())["plate_number"] == "А123ВС77"

    message = make_message("gx110-6012345")
    await receive_vin(message, state, api=AsyncMock(), user=MASTER)

    assert (await state.get_data())["vin"] == "GX110-6012345"
    assert await state.get_state() == NewVehicleStates.waiting_for_make_model.state


async def test_add_vehicle_with_vin_query_asks_plate():
    state = fsm_context()
    await _at(state, NewVisitStates.vehicle_not_found, client_id=C1, vehicle_query=VIN.lower())
    callback = make_callback("vehicle_add")

    await add_vehicle_in_visit_callback(callback, state, api=AsyncMock(), user=MASTER)

    assert await state.get_state() == NewVehicleStates.waiting_for_plate.state
    assert (await state.get_data())["vin"] == VIN


async def test_add_vehicle_with_unclear_query_asks_vin():
    state = fsm_context()
    await _at(state, NewVisitStates.vehicle_not_found, client_id=C1, vehicle_query="Х000")
    callback = make_callback("vehicle_add")

    await add_vehicle_in_visit_callback(callback, state, api=AsyncMock(), user=MASTER)

    assert await state.get_state() == NewVehicleStates.waiting_for_vin.state
    assert shown(callback)[0] == "Введите VIN или номер кузова:"


async def test_invalid_vin_is_asked_again():
    state = fsm_context()
    await _at(state, NewVehicleStates.waiting_for_vin, client_id=C1)
    message = make_message("А123ВС77")

    await receive_vin(message, state, api=AsyncMock(), user=MASTER)

    assert await state.get_state() == NewVehicleStates.waiting_for_vin.state
    assert shown(message)[0] == f"{VIN_FORMAT_ERROR}\n\nВведите VIN или номер кузова:"


async def test_plate_is_normalized():
    state = fsm_context()
    await _at(state, NewVehicleStates.waiting_for_plate, client_id=C1, vin=VIN)

    await receive_plate(make_message("а 123 вс 77"), state, api=AsyncMock(), user=MASTER)

    assert (await state.get_data())["plate_number"] == "А123ВС77"


async def test_taken_vin_returns_to_vin_step():
    state = fsm_context()
    await _at(state, NewVehicleStates.waiting_for_make_model, client_id=C1, vin=VIN, plate_number="А123ВС77")
    api = AsyncMock()
    api.create_vehicle.side_effect = ApiConflict("Машина с таким VIN уже есть")
    message = make_message("Toyota Camry")

    await receive_make_model(message, state, api=api, user=MASTER)

    assert await state.get_state() == NewVehicleStates.waiting_for_vin.state
    assert shown(message)[0] == "Машина с таким VIN уже есть\n\nВведите VIN или номер кузова:"


# --- "➕ Добавить автомобиль" on the client card


async def test_add_vehicle_from_client_card_creates_and_returns_to_card():
    state = fsm_context()
    await on_screens(state, ("client", {"client_id": C1}))
    api = AsyncMock()
    api.create_vehicle.return_value = {"id": CAR, "vin": VIN}
    api.get_client.return_value = {"id": C1, "full_name": "Иван Иванов", "phone_display": "+7 999 123-45-67"}
    api.list_client_vehicles.return_value = [{"id": CAR, "make": "Toyota", "model": "Camry", "plate_number": "А123ВС77"}]

    callback = make_callback("act:add_vehicle")
    await add_vehicle_callback(callback, state, api=api, user=MASTER)
    assert await state.get_state() == NewVehicleStates.waiting_for_vin.state

    await receive_vin(make_message(VIN), state, api=api, user=MASTER)
    await receive_plate(make_message("А123ВС77"), state, api=api, user=MASTER)
    message = make_message("Toyota Camry")
    await receive_make_model(message, state, api=api, user=MASTER)

    api.create_vehicle.assert_awaited_once_with(vin=VIN, plate_number="А123ВС77", make="Toyota", model="Camry")
    api.attach_owner.assert_awaited_once_with(CAR, C1, date_from=date.today().isoformat())
    assert await state.get_state() is None
    text, markup = shown(message)
    assert text.startswith(f"Автомобиль добавлен: {VIN}\n\n👤 Иван Иванов")
    assert ("🚗 Toyota Camry (А123ВС77)", buttons(markup)[0][1]) == buttons(markup)[0]


async def test_add_vehicle_from_client_card_refused_for_mechanic():
    state = fsm_context()
    await on_screens(state, ("client", {"client_id": C1}))
    callback = make_callback("act:add_vehicle")

    await add_vehicle_callback(callback, state, api=AsyncMock(), user=MECHANIC)

    callback.answer.assert_awaited_once_with("Недостаточно прав")
    assert await state.get_state() is None
