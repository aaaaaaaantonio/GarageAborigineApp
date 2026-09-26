from unittest.mock import AsyncMock

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.base import StorageKey

from bot.callback_ids import encode_id as _encode_id
from bot.handlers.visits import (
    approve_work_callback,
    change_status_callback,
    confirm_mileage_callback,
    receive_cancel_reason,
    choose_client_callback,
    choose_vehicle_callback,
    receive_client_query,
    receive_mileage,
    receive_vehicle_query,
    send_visit_card,
    start_new_visit,
)
from bot.states import NewClientStates, NewVehicleStates, NewVisitStates, VisitCancelStates


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
    user = {"id": "m1"}

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


async def test_approve_work_callback_approves_and_refreshes_card():
    visit_id = "11111111-1111-1111-1111-111111111111"
    item_id = "22222222-2222-2222-2222-222222222222"
    callback = AsyncMock()
    callback.data = f"approve_work:{_encode_id(visit_id)}:{_encode_id(item_id)}"
    api = AsyncMock()
    api.get_visit.return_value = {"id": visit_id, "status": "in_progress", "total_amount": "0.00"}
    api.list_work_items.return_value = []

    await approve_work_callback(callback, api=api)

    api.approve_work_item.assert_awaited_once_with(visit_id, item_id)
    api.get_visit.assert_awaited_once_with(visit_id)
    callback.message.answer.assert_awaited_once()
    callback.answer.assert_awaited_once()


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

    await receive_mileage(message, state, api=api, user={"id": "m1"})

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


async def test_change_status_callback_refreshes_visit_card():
    callback = AsyncMock()
    callback.data = f"visit_status:{VISIT_ID}:diagnostics"
    state = _fsm_context()
    api = AsyncMock()
    api.change_visit_status.return_value = {"id": VISIT_ID, "status": "diagnostics", "total_amount": "0.00"}
    api.get_visit.return_value = {"id": VISIT_ID, "status": "diagnostics", "total_amount": "0.00"}
    api.list_work_items.return_value = []

    await change_status_callback(callback, state, api=api)

    api.change_visit_status.assert_awaited_once_with(VISIT_ID, "diagnostics")
    api.get_visit.assert_awaited_once_with(VISIT_ID)
    api.list_work_items.assert_awaited_once_with(VISIT_ID)
    _, kwargs = callback.message.answer.await_args
    assert kwargs["reply_markup"] is not None
    callback.answer.assert_awaited_once()


async def test_change_status_callback_cancelled_asks_for_reason():
    callback = AsyncMock()
    callback.data = f"visit_status:{VISIT_ID}:cancelled"
    state = _fsm_context()
    api = AsyncMock()

    await change_status_callback(callback, state, api=api)

    api.change_visit_status.assert_not_awaited()
    assert await state.get_state() == VisitCancelStates.waiting_for_reason.state
    assert (await state.get_data())["visit_id"] == VISIT_ID
    assert "причину" in callback.message.answer.await_args.args[0]
    callback.answer.assert_awaited_once()


async def test_receive_cancel_reason_cancels_with_reason_and_refreshes_card():
    message = AsyncMock()
    message.text = "Клиент передумал"
    state = _fsm_context()
    await state.set_state(VisitCancelStates.waiting_for_reason)
    await state.update_data(visit_id=VISIT_ID)
    api = AsyncMock()
    api.get_visit.return_value = {"id": VISIT_ID, "status": "cancelled", "total_amount": "0.00"}
    api.list_work_items.return_value = []

    await receive_cancel_reason(message, state, api=api)

    api.change_visit_status.assert_awaited_once_with(VISIT_ID, "cancelled", reason="Клиент передумал")
    assert await state.get_state() is None
    api.get_visit.assert_awaited_once_with(VISIT_ID)


async def test_receive_cancel_reason_rejects_non_text():
    message = AsyncMock()
    message.text = None
    state = _fsm_context()
    await state.set_state(VisitCancelStates.waiting_for_reason)
    await state.update_data(visit_id=VISIT_ID)
    api = AsyncMock()

    await receive_cancel_reason(message, state, api=api)

    api.change_visit_status.assert_not_awaited()
    assert await state.get_state() == VisitCancelStates.waiting_for_reason.state


async def test_receive_mileage_rollback_offers_confirmation_and_keeps_data():
    from bot.api_client import ApiMileageRollback

    message = AsyncMock()
    message.text = "1000"
    state = _fsm_context()
    await state.set_state(NewVisitStates.waiting_for_mileage)
    await state.update_data(client_id="c1", vehicle_id="v1")
    api = AsyncMock()
    api.create_visit.side_effect = ApiMileageRollback("Пробег меньше последнего зафиксированного.")

    await receive_mileage(message, state, api=api, user={"id": "m1"})

    assert await state.get_state() == NewVisitStates.confirming_mileage.state
    data = await state.get_data()
    assert data == {"client_id": "c1", "vehicle_id": "v1", "mileage": 1000}
    args, kwargs = message.answer.await_args
    assert "Пробег меньше" in args[0]
    buttons = [b for row in kwargs["reply_markup"].inline_keyboard for b in row]
    assert [b.callback_data for b in buttons] == ["mileage_confirm"]


async def test_confirm_mileage_callback_resends_with_manual_confirmation():
    callback = AsyncMock()
    callback.data = "mileage_confirm"
    state = _fsm_context()
    await state.set_state(NewVisitStates.confirming_mileage)
    await state.update_data(client_id="c1", vehicle_id="v1", mileage=1000)
    api = AsyncMock()
    api.create_visit.return_value = {"id": VISIT_ID, "status": "received", "total_amount": "0.00"}

    await confirm_mileage_callback(callback, state, api=api, user={"id": "m1"})

    api.create_visit.assert_awaited_once_with(
        client_id="c1", vehicle_id="v1", assigned_master_id="m1", mileage_at_intake=1000,
        mileage_manually_confirmed=True,
    )
    assert await state.get_state() is None
    callback.message.answer.assert_awaited_once()
    callback.answer.assert_awaited_once()
