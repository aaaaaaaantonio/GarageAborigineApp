from unittest.mock import AsyncMock

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.base import StorageKey

from bot.handlers.visits import (
    approve_work_callback,
    choose_client_callback,
    choose_vehicle_callback,
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
    user = {"id": "m1"}

    await receive_mileage(message, state, api=api, user=user)

    api.create_visit.assert_awaited_once_with(
        client_id="c1", vehicle_id="v1", assigned_master_id="m1", mileage_at_intake=45000
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
    visit = {"id": "visit1", "status": "in_progress", "total_amount": "0.00"}
    work_items = [{"id": "wi1", "free_text_name": "Замена масла", "approved_by_client": False}]

    await send_visit_card(message, visit, work_items)

    _, kwargs = message.answer.await_args
    markup = kwargs["reply_markup"]
    texts = [button.text for row in markup.inline_keyboard for button in row]
    assert "✅ Замена масла" in texts


async def test_send_visit_card_skips_approve_button_for_approved_item():
    message = AsyncMock()
    visit = {"id": "visit1", "status": "in_progress", "total_amount": "0.00"}
    work_items = [{"id": "wi1", "free_text_name": "Замена масла", "approved_by_client": True}]

    await send_visit_card(message, visit, work_items)

    _, kwargs = message.answer.await_args
    markup = kwargs["reply_markup"]
    texts = [button.text for row in markup.inline_keyboard for button in row]
    assert not any(t.startswith("✅") for t in texts)


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
    callback = AsyncMock()
    callback.data = "approve_work:visit1:wi1"
    api = AsyncMock()
    api.get_visit.return_value = {"id": "visit1", "status": "in_progress", "total_amount": "0.00"}
    api.list_work_items.return_value = []

    await approve_work_callback(callback, api=api)

    api.approve_work_item.assert_awaited_once_with("visit1", "wi1")
    api.get_visit.assert_awaited_once_with("visit1")
    callback.message.answer.assert_awaited_once()
    callback.answer.assert_awaited_once()
