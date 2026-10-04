import json
from unittest.mock import AsyncMock

from bot.api_client import ApiMileageRollback
from bot.callback_ids import encode_id
from bot.handlers.visits import (
    choose_client_callback,
    choose_master_callback,
    choose_vehicle_callback,
    confirm_mileage_callback,
    new_visit_for_callback,
    receive_client_query,
    receive_mileage,
    receive_vehicle_query,
    start_new_visit,
)
from bot.states import NewClientStates, NewVehicleStates, NewVisitStates
from tests.bot.helpers import ADMIN, MASTER, MECHANIC, buttons, fsm_context, make_callback, make_message, on_screens, shown

C1 = "11111111-1111-1111-1111-111111111111"
CAR = "44444444-4444-4444-4444-444444444444"
VISIT = "55555555-5555-5555-5555-555555555555"
MASTER_B = "66666666-6666-6666-6666-666666666666"


def _api():
    api = AsyncMock()
    api.create_visit.return_value = {"id": VISIT, "status": "received", "total_amount": 0}
    api.get_visit.return_value = {"id": VISIT, "status": "received", "total_amount": 0, "plate_number": "А123ВС77"}
    api.list_work_items.return_value = []
    return api


async def _at(state, step, **data):
    await on_screens(state)
    await state.set_state(step)
    await state.update_data(wiz_name="new_visit", wiz_steps=[], **data)


async def test_start_from_menu_asks_for_client():
    state = fsm_context()
    await on_screens(state)
    callback = make_callback("wiz:new_visit")

    await start_new_visit(callback, state, api=_api(), user=MASTER)

    assert await state.get_state() == NewVisitStates.waiting_for_client_query.state
    assert shown(callback)[0] == "Введите телефон или ФИО клиента:"


async def test_start_refused_for_mechanic():
    state = fsm_context()
    callback = make_callback("wiz:new_visit")

    await start_new_visit(callback, state, api=_api(), user=MECHANIC)

    assert await state.get_state() is None
    callback.answer.assert_awaited_once_with("Недостаточно прав")


async def test_client_query_offers_candidates_and_data_is_json():
    state = fsm_context()
    await _at(state, NewVisitStates.waiting_for_client_query)
    api = _api()
    api.search.return_value = [{"entity": "client", "id": C1}, {"entity": "vehicle", "id": CAR}]
    api.get_client.return_value = {"id": C1, "full_name": "Иван Иванов"}
    message = make_message("Иван")

    await receive_client_query(message, state, api=api, user=MASTER)

    assert await state.get_state() == NewVisitStates.choosing_client.state
    text, markup = shown(message)
    assert text == "Выберите клиента:"
    assert buttons(markup)[0] == ("Иван Иванов", f"client_pick:{C1}")
    json.dumps(await state.get_data())  # survives RedisStorage


async def test_client_not_found_goes_to_client_creation():
    state = fsm_context()
    await _at(state, NewVisitStates.waiting_for_client_query)
    api = _api()
    api.search.return_value = []
    message = make_message("Пётр")

    await receive_client_query(message, state, api=api, user=MASTER)

    assert await state.get_state() == NewClientStates.waiting_for_phone.state
    assert shown(message)[0] == "Клиент не найден. Введите телефон клиента:"


async def test_choose_client_then_vehicle_query():
    state = fsm_context()
    await _at(state, NewVisitStates.choosing_client, client_choices=[[C1, "Иван"]])
    callback = make_callback(f"client_pick:{C1}")

    await choose_client_callback(callback, state, api=_api(), user=MASTER)

    assert (await state.get_data())["client_id"] == C1
    assert await state.get_state() == NewVisitStates.waiting_for_vehicle_query.state
    assert shown(callback)[0] == "Введите VIN или гос.номер авто:"


async def test_vehicle_query_offers_candidates():
    state = fsm_context()
    await _at(state, NewVisitStates.waiting_for_vehicle_query, client_id=C1)
    api = _api()
    api.search.return_value = [{"entity": "vehicle", "id": CAR}]
    api.get_vehicle.return_value = {"id": CAR, "plate_number": "А123ВС77"}
    message = make_message("А123")

    await receive_vehicle_query(message, state, api=api, user=MASTER)

    assert await state.get_state() == NewVisitStates.choosing_vehicle.state
    assert buttons(shown(message)[1])[0] == ("А123ВС77", f"vehicle_pick:{CAR}")


async def test_vehicle_not_found_goes_to_vehicle_creation():
    state = fsm_context()
    await _at(state, NewVisitStates.waiting_for_vehicle_query, client_id=C1)
    api = _api()
    api.search.return_value = []
    message = make_message("Х000")

    await receive_vehicle_query(message, state, api=api, user=MASTER)

    assert await state.get_state() == NewVehicleStates.waiting_for_vin.state
    assert shown(message)[0] == "Автомобиль не найден. Введите VIN:"


async def test_choose_vehicle_then_mileage():
    state = fsm_context()
    await _at(state, NewVisitStates.choosing_vehicle, client_id=C1, vehicle_choices=[[CAR, "А123ВС77"]])
    callback = make_callback(f"vehicle_pick:{CAR}")

    await choose_vehicle_callback(callback, state, api=_api(), user=MASTER)

    assert (await state.get_data())["vehicle_id"] == CAR
    assert shown(callback)[0] == "Введите пробег на приёмке:"


async def test_master_mileage_creates_visit_and_opens_card_over_source():
    state = fsm_context()
    await _at(state, NewVisitStates.waiting_for_mileage, client_id=C1, vehicle_id=CAR)
    api = _api()
    message = make_message("45000")

    await receive_mileage(message, state, api=api, user=MASTER)

    api.create_visit.assert_awaited_once_with(
        client_id=C1, vehicle_id=CAR, assigned_master_id=MASTER["id"], mileage_at_intake=45000,
        mileage_manually_confirmed=False,
    )
    assert await state.get_state() is None
    assert (await state.get_data())["nav_stack"] == [["menu", {}], ["visit", {"visit_id": VISIT}]]


async def test_mileage_must_be_a_number():
    state = fsm_context()
    await _at(state, NewVisitStates.waiting_for_mileage, client_id=C1, vehicle_id=CAR)
    message = make_message("много")

    await receive_mileage(message, state, api=_api(), user=MASTER)

    assert shown(message)[0] == "Введите число (пробег в км).\n\nВведите пробег на приёмке:"


async def test_mileage_rollback_asks_confirmation_then_confirm_creates():
    state = fsm_context()
    await _at(state, NewVisitStates.waiting_for_mileage, client_id=C1, vehicle_id=CAR)
    api = _api()
    api.create_visit.side_effect = [ApiMileageRollback("Пробег меньше последнего (50 000)."), api.create_visit.return_value]
    message = make_message("900")

    await receive_mileage(message, state, api=api, user=MASTER)

    assert await state.get_state() == NewVisitStates.confirming_mileage.state
    text, markup = shown(message)
    assert text == "Пробег меньше последнего (50 000).\nИли введите другой пробег."
    assert buttons(markup)[0] == ("Подтвердить пробег", "mileage_confirm")

    await confirm_mileage_callback(make_callback("mileage_confirm"), state, api=api, user=MASTER)

    assert api.create_visit.await_args.kwargs["mileage_manually_confirmed"] is True
    assert await state.get_state() is None


async def test_admin_chooses_master_then_visit_is_created_with_them():
    state = fsm_context()
    await _at(state, NewVisitStates.waiting_for_mileage, client_id=C1, vehicle_id=CAR)
    api = _api()
    api.list_masters.return_value = [{"id": MASTER_B, "full_name": "Петров"}]
    message = make_message("45000")

    await receive_mileage(message, state, api=api, user=ADMIN)

    assert await state.get_state() == NewVisitStates.choosing_master.state
    assert buttons(shown(message)[1])[0] == ("Петров", f"master_pick:{encode_id(MASTER_B)}")

    await choose_master_callback(make_callback(f"master_pick:{encode_id(MASTER_B)}"), state, api=api, user=ADMIN)

    assert api.create_visit.await_args.kwargs["assigned_master_id"] == MASTER_B


async def test_admin_without_masters_is_told_to_add_one():
    state = fsm_context()
    await _at(state, NewVisitStates.waiting_for_mileage, client_id=C1, vehicle_id=CAR)
    api = _api()
    api.list_masters.return_value = []
    message = make_message("45000")

    await receive_mileage(message, state, api=api, user=ADMIN)

    assert await state.get_state() is None
    assert shown(message)[0].startswith("Сначала добавьте мастера через «Добавить сотрудника».")
    api.create_visit.assert_not_awaited()


async def test_new_visit_from_vehicle_card_starts_at_mileage_with_owner():
    state = fsm_context()
    await on_screens(state, ("vehicle", {"vehicle_id": CAR}))
    api = _api()
    api.get_vehicle_owner.return_value = {"id": C1, "full_name": "Иван Иванов"}
    callback = make_callback("act:new_visit_for")

    await new_visit_for_callback(callback, state, api=api, user=MASTER)

    data = await state.get_data()
    assert (data["client_id"], data["vehicle_id"]) == (C1, CAR)
    assert shown(callback)[0] == "Новый заезд: Иван Иванов. Введите пробег на приёмке:"


async def test_new_visit_from_vehicle_without_owner_is_refused():
    state = fsm_context()
    await on_screens(state, ("vehicle", {"vehicle_id": CAR}))
    api = _api()
    api.get_vehicle_owner.return_value = None
    callback = make_callback("act:new_visit_for")

    await new_visit_for_callback(callback, state, api=api, user=MASTER)

    assert await state.get_state() is None
    callback.answer.assert_awaited_once_with("У машины нет владельца — заведите заезд через «Новый заезд».", show_alert=True)


async def test_new_visit_from_vehicle_refused_for_mechanic():
    state = fsm_context()
    await on_screens(state, ("vehicle", {"vehicle_id": CAR}))
    api = _api()
    callback = make_callback("act:new_visit_for")

    await new_visit_for_callback(callback, state, api=api, user=MECHANIC)

    api.get_vehicle_owner.assert_not_awaited()
    callback.answer.assert_awaited_once_with("Недостаточно прав")
