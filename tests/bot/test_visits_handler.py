from unittest.mock import AsyncMock

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.base import StorageKey

from bot.callback_ids import encode_id as _encode_id
from bot.handlers.visits import (
    confirm_mileage_callback,
    choose_client_callback,
    choose_master_callback,
    choose_vehicle_callback,
    new_visit_for_vehicle_callback,
    receive_client_query,
    receive_mileage,
    receive_vehicle_query,
    send_visit_card,
    start_new_visit,
)
from bot.states import NewClientStates, NewVehicleStates, NewVisitStates


def _fsm_context() -> FSMContext:
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=1, user_id=1)
    return FSMContext(storage=storage, key=key)


async def test_receive_mileage_uses_acting_user_as_master():
    message = AsyncMock()
    message.text = "45000"
    state = _fsm_context()
    await state.set_state(NewVisitStates.waiting_for_mileage)
    await state.update_data(client_id="c1", vehicle_id="v1")
    api = AsyncMock()
    api.create_visit.return_value = {"id": "visit1", "status": "received"}
    user = {"id": "m1", "role": "master"}

    await receive_mileage(message, state, api=api, user=user)

    api.create_visit.assert_awaited_once_with(
        client_id="c1", vehicle_id="v1", assigned_master_id="m1", mileage_at_intake=45000,
        mileage_manually_confirmed=False,
    )
    assert (await state.get_state()) is None


async def test_send_visit_card_shows_status_buttons():
    message = AsyncMock()
    visit = {"id": "visit1", "status": "received", "total_amount": "0.00"}

    await send_visit_card(message, visit, [])

    message.answer.assert_awaited_once()
    _, kwargs = message.answer.await_args
    assert kwargs["reply_markup"] is not None


async def test_send_visit_card_shows_approve_button_for_unapproved_item():
    message = AsyncMock()
    visit = {"id": "11111111-1111-1111-1111-111111111111", "status": "in_progress", "total_amount": "0.00"}
    work_items = [
        {
            "id": "22222222-2222-2222-2222-222222222222",
            "name": "Замена масла",
            "status": "not_ready",
            "approved_by_client": False,
        }
    ]

    await send_visit_card(message, visit, work_items)

    _, kwargs = message.answer.await_args
    markup = kwargs["reply_markup"]
    texts = [button.text for row in markup.inline_keyboard for button in row]
    assert "✅ Замена масла" in texts


async def test_send_visit_card_skips_approve_button_for_approved_item():
    message = AsyncMock()
    visit = {"id": "11111111-1111-1111-1111-111111111111", "status": "in_progress", "total_amount": "0.00"}
    work_items = [
        {
            "id": "22222222-2222-2222-2222-222222222222",
            "name": "Замена масла",
            "status": "not_ready",
            "approved_by_client": True,
        }
    ]

    await send_visit_card(message, visit, work_items)

    _, kwargs = message.answer.await_args
    markup = kwargs["reply_markup"]
    texts = [button.text for row in markup.inline_keyboard for button in row]
    assert not any(t.startswith("✅") for t in texts)


async def test_send_visit_card_shows_add_part_button_for_unapproved_item():
    message = AsyncMock()
    visit_id = "11111111-1111-1111-1111-111111111111"
    item_id = "22222222-2222-2222-2222-222222222222"
    visit = {"id": visit_id, "status": "in_progress", "total_amount": "0.00"}
    work_items = [
        {
            "id": item_id,
            "name": "Замена масла",
            "status": "not_ready",
            "approved_by_client": False,
        }
    ]

    await send_visit_card(message, visit, work_items)

    _, kwargs = message.answer.await_args
    markup = kwargs["reply_markup"]
    add_part_buttons = [
        b for row in markup.inline_keyboard for b in row if b.text == "🔧 Замена масла"
    ]
    assert len(add_part_buttons) == 1
    assert add_part_buttons[0].callback_data == f"add_part:{_encode_id(visit_id)}:{_encode_id(item_id)}"


async def test_send_visit_card_shows_add_part_button_for_approved_item():
    message = AsyncMock()
    visit_id = "11111111-1111-1111-1111-111111111111"
    item_id = "22222222-2222-2222-2222-222222222222"
    visit = {"id": visit_id, "status": "in_progress", "total_amount": "0.00"}
    work_items = [
        {
            "id": item_id,
            "name": "Замена масла",
            "status": "not_ready",
            "approved_by_client": True,
        }
    ]

    await send_visit_card(message, visit, work_items)

    _, kwargs = message.answer.await_args
    markup = kwargs["reply_markup"]
    add_part_buttons = [
        b for row in markup.inline_keyboard for b in row if b.text == "🔧 Замена масла"
    ]
    assert len(add_part_buttons) == 1
    assert add_part_buttons[0].callback_data == f"add_part:{_encode_id(visit_id)}:{_encode_id(item_id)}"


async def test_start_new_visit_asks_for_client():
    message = AsyncMock()
    state = _fsm_context()

    await start_new_visit(message, state)

    assert (await state.get_state()) == NewVisitStates.waiting_for_client_query.state


async def test_receive_client_query_shows_candidates():
    message = AsyncMock()
    message.text = "Иван"
    state = _fsm_context()
    await state.set_state(NewVisitStates.waiting_for_client_query)
    api = AsyncMock()
    api.search.return_value = [{"entity": "client", "id": "c1", "matched_field": "full_name"}]
    api.get_client.return_value = {"id": "c1", "full_name": "Иван Иванов"}

    await receive_client_query(message, state, api=api)

    api.get_client.assert_awaited_once_with("c1")
    assert (await state.get_state()) == NewVisitStates.choosing_client.state


async def test_receive_client_query_falls_back_to_creation_when_no_matches():
    message = AsyncMock()
    message.text = "неизвестный"
    state = _fsm_context()
    await state.set_state(NewVisitStates.waiting_for_client_query)
    api = AsyncMock()
    api.search.return_value = []

    await receive_client_query(message, state, api=api)

    assert (await state.get_state()) == NewClientStates.waiting_for_phone.state
    data = await state.get_data()
    assert data["return_flow"] == "new_visit"


async def test_choose_client_callback_stores_client_id():
    callback = AsyncMock()
    callback.data = "client_pick:c1"
    state = _fsm_context()

    await choose_client_callback(callback, state)

    data = await state.get_data()
    assert data["client_id"] == "c1"
    assert (await state.get_state()) == NewVisitStates.waiting_for_vehicle_query.state


async def test_receive_vehicle_query_shows_candidates():
    message = AsyncMock()
    message.text = "А123"
    state = _fsm_context()
    await state.set_state(NewVisitStates.waiting_for_vehicle_query)
    api = AsyncMock()
    api.search.return_value = [{"entity": "vehicle", "id": "v1", "matched_field": "plate_number"}]
    api.get_vehicle.return_value = {"id": "v1", "plate_number": "А123"}

    await receive_vehicle_query(message, state, api=api)

    api.get_vehicle.assert_awaited_once_with("v1")
    assert (await state.get_state()) == NewVisitStates.choosing_vehicle.state


async def test_receive_vehicle_query_falls_back_to_creation_when_no_matches():
    message = AsyncMock()
    message.text = "неизвестный VIN"
    state = _fsm_context()
    await state.set_state(NewVisitStates.waiting_for_vehicle_query)
    api = AsyncMock()
    api.search.return_value = []

    await receive_vehicle_query(message, state, api=api)

    assert (await state.get_state()) == NewVehicleStates.waiting_for_vin.state
    data = await state.get_data()
    assert data["return_flow"] == "new_visit"


async def test_choose_vehicle_callback_stores_vehicle_id():
    callback = AsyncMock()
    callback.data = "vehicle_pick:v1"
    state = _fsm_context()

    await choose_vehicle_callback(callback, state)

    data = await state.get_data()
    assert data["vehicle_id"] == "v1"
    assert (await state.get_state()) == NewVisitStates.waiting_for_mileage.state


async def test_send_visit_card_callback_data_fits_telegram_limit():
    message = AsyncMock()
    visit = {"id": "11111111-1111-1111-1111-111111111111", "status": "in_progress", "total_amount": "0.00"}
    work_items = [
        {
            "id": "22222222-2222-2222-2222-222222222222",
            "name": "Замена масла",
            "status": "not_ready",
            "approved_by_client": False,
        }
    ]

    await send_visit_card(message, visit, work_items)

    _, kwargs = message.answer.await_args
    markup = kwargs["reply_markup"]
    assert all(len(b.callback_data.encode()) <= 64 for row in markup.inline_keyboard for b in row)


async def test_send_visit_card_uses_resolved_work_item_name():
    message = AsyncMock()
    visit = {"id": "11111111-1111-1111-1111-111111111111", "status": "in_progress", "total_amount": "0.00"}
    work_items = [
        {
            "id": "22222222-2222-2222-2222-222222222222",
            "name": "Диагностика ходовой",
            "free_text_name": None,
            "status": "not_ready",
            "approved_by_client": False,
        },
    ]

    await send_visit_card(message, visit, work_items)

    args, kwargs = message.answer.await_args
    texts = [button.text for row in kwargs["reply_markup"].inline_keyboard for button in row]
    assert "✅ Диагностика ходовой" in texts
    assert "Диагностика ходовой" in args[0]


async def test_send_visit_card_shows_add_work_button():
    message = AsyncMock()
    visit = {"id": "11111111-1111-1111-1111-111111111111", "status": "in_progress", "total_amount": "0.00"}

    await send_visit_card(message, visit, [])

    _, kwargs = message.answer.await_args
    markup = kwargs["reply_markup"]
    buttons = [b for row in markup.inline_keyboard for b in row]
    add_work_buttons = [b for b in buttons if b.text == "➕ Добавить работу"]
    assert len(add_work_buttons) == 1
    assert add_work_buttons[0].callback_data == f"add_work:{visit['id']}"


async def test_receive_mileage_reprompts_on_non_numeric_input():
    message = AsyncMock()
    message.text = "много"
    state = _fsm_context()
    await state.set_state(NewVisitStates.waiting_for_mileage)
    await state.update_data(client_id="c1", vehicle_id="v1")
    api = AsyncMock()

    await receive_mileage(message, state, api=api, user={"id": "m1", "role": "master"})

    api.create_visit.assert_not_awaited()
    message.answer.assert_awaited_once_with("Введите число (пробег в км).")
    assert (await state.get_state()) == NewVisitStates.waiting_for_mileage.state


VISIT_ID = "11111111-1111-1111-1111-111111111111"
ITEM_ID = "22222222-2222-2222-2222-222222222222"


def _buttons(message) -> list:
    _, kwargs = message.answer.await_args
    return [b for row in kwargs["reply_markup"].inline_keyboard for b in row]


async def test_send_visit_card_offers_waiting_parts_and_ready_for_in_progress_item():
    message = AsyncMock()
    visit = {"id": VISIT_ID, "status": "in_progress", "total_amount": "0.00"}
    items = [{"id": ITEM_ID, "name": "Замена масла", "status": "in_progress", "approved_by_client": True}]

    await send_visit_card(message, visit, items)

    data = {b.callback_data for b in _buttons(message)}
    prefix = f"wsc:{_encode_id(VISIT_ID)}:{_encode_id(ITEM_ID)}"
    assert f"{prefix}:waiting_parts" in data
    assert f"{prefix}:ready" in data
    assert all(len(d.encode()) <= 64 for d in data)


async def test_send_visit_card_has_no_status_button_for_ready_item():
    message = AsyncMock()
    visit = {"id": VISIT_ID, "status": "in_progress", "total_amount": "0.00"}
    items = [{"id": ITEM_ID, "name": "Замена масла", "status": "ready", "approved_by_client": True}]

    await send_visit_card(message, visit, items)

    assert not any(b.callback_data.startswith("wsc:") for b in _buttons(message))


async def test_send_visit_card_offers_cancel_from_ready():
    message = AsyncMock()
    visit = {"id": VISIT_ID, "status": "ready", "total_amount": "0.00"}

    await send_visit_card(message, visit, [])

    data = {b.callback_data for b in _buttons(message)}
    assert f"visit_status:{VISIT_ID}:issued" in data
    assert f"visit_status:{VISIT_ID}:cancelled" in data


async def test_receive_mileage_rollback_offers_confirmation_and_keeps_data():
    from bot.api_client import ApiMileageRollback

    message = AsyncMock()
    message.text = "1000"
    state = _fsm_context()
    await state.set_state(NewVisitStates.waiting_for_mileage)
    await state.update_data(client_id="c1", vehicle_id="v1")
    api = AsyncMock()
    api.create_visit.side_effect = ApiMileageRollback("Пробег меньше последнего зафиксированного.")

    await receive_mileage(message, state, api=api, user={"id": "m1", "role": "master"})

    assert await state.get_state() == NewVisitStates.confirming_mileage.state
    data = await state.get_data()
    assert data == {"client_id": "c1", "vehicle_id": "v1", "mileage": 1000, "mileage_confirmed": False}
    args, kwargs = message.answer.await_args
    assert "Пробег меньше" in args[0]
    buttons = [b for row in kwargs["reply_markup"].inline_keyboard for b in row]
    assert [b.callback_data for b in buttons] == ["mileage_confirm"]


async def test_confirm_mileage_callback_resends_with_manual_confirmation():
    callback = AsyncMock()
    callback.data = "mileage_confirm"
    state = _fsm_context()
    await state.set_state(NewVisitStates.confirming_mileage)
    await state.update_data(client_id="c1", vehicle_id="v1", mileage=1000, mileage_confirmed=False)
    api = AsyncMock()
    api.create_visit.return_value = {"id": VISIT_ID, "status": "received", "total_amount": "0.00"}

    await confirm_mileage_callback(callback, state, api=api, user={"id": "m1", "role": "master"})

    api.create_visit.assert_awaited_once_with(
        client_id="c1", vehicle_id="v1", assigned_master_id="m1", mileage_at_intake=1000,
        mileage_manually_confirmed=True,
    )
    assert await state.get_state() is None
    callback.message.answer.assert_awaited_once()
    callback.answer.assert_awaited_once()


async def test_send_visit_card_header_is_human_readable_and_statuses_russian():
    message = AsyncMock()
    visit = {
        "id": "11111111-1111-1111-1111-111111111111",
        "status": "in_progress",
        "total_amount": 12400.0,
        "plate_number": "А123ВС77",
        "make_model": "Toyota Camry",
        "client_name": "Иванов Пётр",
        "master_name": "Петров",
    }
    work_items = [
        {"id": "22222222-2222-2222-2222-222222222222", "name": "Замена масла", "status": "in_progress",
         "approved_by_client": True},
    ]

    await send_visit_card(message, visit, work_items)

    text = message.answer.await_args.args[0]
    assert text.splitlines()[0] == "А123ВС77 · Toyota Camry · Иванов Пётр"
    assert "Статус: Ремонт · Мастер: Петров" in text
    assert "1. Замена масла — В работе" in text
    markup = message.answer.await_args.kwargs["reply_markup"]
    texts = [b.text for row in markup.inline_keyboard for b in row]
    assert "Ждём запчасти" in texts
    assert "🔄 Замена масла → Готово" in texts
    assert "11111111-1111-1111-1111-111111111111" not in text


async def test_send_visit_card_without_summary_falls_back_to_generic_title():
    message = AsyncMock()

    await send_visit_card(message, {"id": "visit1", "status": "received", "total_amount": "0.00"}, [])

    assert message.answer.await_args.args[0].splitlines()[0] == "Заезд"


MASTER_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
VEHICLE_ID = "44444444-4444-4444-4444-444444444444"
ADMIN = {"id": "admin1", "role": "admin"}


async def test_admin_is_asked_to_choose_master_after_mileage():
    message = AsyncMock()
    message.text = "45000"
    state = _fsm_context()
    await state.set_state(NewVisitStates.waiting_for_mileage)
    await state.update_data(client_id="c1", vehicle_id="v1")
    api = AsyncMock()
    api.list_masters.return_value = [{"id": MASTER_A, "full_name": "Анна"}]

    await receive_mileage(message, state, api=api, user=ADMIN)

    api.create_visit.assert_not_awaited()
    assert await state.get_state() == NewVisitStates.choosing_master.state
    markup = message.answer.await_args.kwargs["reply_markup"]
    assert [(b.text, b.callback_data) for row in markup.inline_keyboard for b in row] == [
        ("Анна", f"master_pick:{_encode_id(MASTER_A)}")
    ]


async def test_admin_master_pick_creates_visit_with_that_master():
    callback = AsyncMock()
    callback.data = f"master_pick:{_encode_id(MASTER_A)}"
    state = _fsm_context()
    await state.set_state(NewVisitStates.choosing_master)
    await state.update_data(client_id="c1", vehicle_id="v1", mileage=45000, mileage_confirmed=False)
    api = AsyncMock()
    api.create_visit.return_value = {"id": "visit1", "status": "received"}

    await choose_master_callback(callback, state, api=api, user=ADMIN)

    api.create_visit.assert_awaited_once_with(
        client_id="c1", vehicle_id="v1", assigned_master_id=MASTER_A, mileage_at_intake=45000,
        mileage_manually_confirmed=False,
    )
    assert await state.get_state() is None


async def test_admin_without_masters_is_told_to_add_one():
    message = AsyncMock()
    message.text = "45000"
    state = _fsm_context()
    await state.set_state(NewVisitStates.waiting_for_mileage)
    await state.update_data(client_id="c1", vehicle_id="v1")
    api = AsyncMock()
    api.list_masters.return_value = []

    await receive_mileage(message, state, api=api, user=ADMIN)

    message.answer.assert_awaited_once_with("Сначала добавьте мастера через «Добавить сотрудника».")
    assert await state.get_state() is None
    api.create_visit.assert_not_awaited()


async def test_admin_mileage_rollback_keeps_chosen_master():
    from bot.api_client import ApiMileageRollback

    callback = AsyncMock()
    callback.data = f"master_pick:{_encode_id(MASTER_A)}"
    state = _fsm_context()
    await state.set_state(NewVisitStates.choosing_master)
    await state.update_data(client_id="c1", vehicle_id="v1", mileage=100, mileage_confirmed=False)
    api = AsyncMock()
    api.create_visit.side_effect = [ApiMileageRollback("Пробег меньше"), {"id": "visit1", "status": "received"}]

    await choose_master_callback(callback, state, api=api, user=ADMIN)
    assert await state.get_state() == NewVisitStates.confirming_mileage.state

    confirm = AsyncMock()
    await confirm_mileage_callback(confirm, state, api=api, user=ADMIN)

    api.list_masters.assert_not_awaited()
    assert api.create_visit.await_args_list[1].kwargs["assigned_master_id"] == MASTER_A
    assert api.create_visit.await_args_list[1].kwargs["mileage_manually_confirmed"] is True


async def test_new_visit_from_vehicle_card_starts_at_mileage():
    callback = AsyncMock()
    callback.data = f"new_visit_for:{_encode_id(VEHICLE_ID)}"
    state = _fsm_context()
    await state.update_data(stale="x")
    api = AsyncMock()
    api.get_vehicle_owner.return_value = {"id": "c9", "full_name": "Иванов"}

    await new_visit_for_vehicle_callback(callback, state, api=api, user={"id": "m1", "role": "master"})

    assert await state.get_state() == NewVisitStates.waiting_for_mileage.state
    assert await state.get_data() == {"client_id": "c9", "vehicle_id": VEHICLE_ID}
    callback.message.answer.assert_awaited_once_with("Новый заезд: Иванов. Введите пробег на приёмке (/cancel — отмена):")


async def test_new_visit_from_vehicle_without_owner_is_refused():
    callback = AsyncMock()
    callback.data = f"new_visit_for:{_encode_id(VEHICLE_ID)}"
    state = _fsm_context()
    api = AsyncMock()
    api.get_vehicle_owner.return_value = None

    await new_visit_for_vehicle_callback(callback, state, api=api, user={"id": "m1", "role": "master"})

    assert await state.get_state() is None
    callback.message.answer.assert_awaited_once_with("У машины нет владельца — заведите заезд через «Новый заезд».")


async def test_new_visit_from_vehicle_refused_for_mechanic():
    callback = AsyncMock()
    callback.data = f"new_visit_for:{_encode_id(VEHICLE_ID)}"
    state = _fsm_context()
    api = AsyncMock()

    await new_visit_for_vehicle_callback(callback, state, api=api, user={"id": "k1", "role": "mechanic"})

    api.get_vehicle_owner.assert_not_awaited()
    callback.answer.assert_awaited_once_with("Недостаточно прав")
