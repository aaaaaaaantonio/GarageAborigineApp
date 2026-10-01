from unittest.mock import AsyncMock

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.base import StorageKey

from bot.callback_ids import encode_id
from bot.handlers.work_items import (
    choose_catalog_callback,
    choose_category_callback,
    choose_mechanic_callback,
    receive_hours_and_rate,
    receive_work_name,
    start_add_work_item,
)
from bot.states import AddWorkItemStates


def _fsm_context() -> FSMContext:
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=1, user_id=1)
    return FSMContext(storage=storage, key=key)


async def test_start_add_work_item_asks_for_name_and_stores_visit_id():
    callback = AsyncMock()
    callback.data = "add_work:visit1"
    state = _fsm_context()
    await state.update_data(stale_key="from_previous_wizard")
    await state.set_state(AddWorkItemStates.choosing_category)

    await start_add_work_item(callback, state)

    data = await state.get_data()
    assert data == {"visit_id": "visit1"}
    assert (await state.get_state()) == AddWorkItemStates.waiting_for_name.state
    callback.message.answer.assert_awaited_once_with("Введите название работы (/cancel — отмена):")
    callback.answer.assert_awaited_once()


async def test_receive_work_name_shows_catalog_suggestions():
    message = AsyncMock()
    message.text = "замена масла"
    state = _fsm_context()
    await state.set_state(AddWorkItemStates.waiting_for_name)
    await state.update_data(visit_id="visit1")
    api = AsyncMock()
    api.suggest_catalog.return_value = [
        {"id": "cat1", "name": "Замена масла", "category": "maintenance", "default_norm_hours": 1.0}
    ]

    await receive_work_name(message, state, api=api)

    api.suggest_catalog.assert_awaited_once_with("замена масла")
    assert (await state.get_state()) == AddWorkItemStates.choosing_suggestion.state
    data = await state.get_data()
    assert data["suggestions"]["cat1"]["category"] == "maintenance"


async def test_choose_catalog_callback_carries_category_and_hours():
    callback = AsyncMock()
    callback.data = "catalog_pick:cat1"
    state = _fsm_context()
    await state.update_data(
        visit_id="visit1",
        suggestions={"cat1": {"id": "cat1", "category": "maintenance", "default_norm_hours": 1.0}},
    )

    await choose_catalog_callback(callback, state)

    data = await state.get_data()
    assert data["category"] == "maintenance"
    assert data["norm_hours"] == 1.0
    assert (await state.get_state()) == AddWorkItemStates.waiting_for_hours_and_rate.state


async def test_choose_catalog_callback_none_asks_for_category():
    callback = AsyncMock()
    callback.data = "catalog_pick:none"
    state = _fsm_context()

    await choose_catalog_callback(callback, state)

    assert (await state.get_state()) == AddWorkItemStates.choosing_category.state


async def test_choose_category_callback_stores_category():
    callback = AsyncMock()
    callback.data = "category_pick:body"
    state = _fsm_context()

    await choose_category_callback(callback, state)

    data = await state.get_data()
    assert data["category"] == "body"
    assert (await state.get_state()) == AddWorkItemStates.waiting_for_hours_and_rate.state


async def test_receive_hours_and_rate_from_catalog_path_asks_only_rate():
    message = AsyncMock()
    message.text = "800"
    state = _fsm_context()
    await state.update_data(visit_id="visit1", catalog_item_id="cat1", category="maintenance", norm_hours=1.0)
    api = AsyncMock()
    api.get_visit.return_value = {"id": "visit1", "status": "received", "total_amount": "0.00"}
    api.list_work_items.return_value = []
    api.list_mechanics.return_value = []

    await receive_hours_and_rate(message, state, api=api)

    api.add_work_item.assert_awaited_once_with(
        "visit1", catalog_item_id="cat1", free_text_name=None, category="maintenance",
        norm_hours=1.0, hourly_rate=800.0, assigned_mechanic_id=None,
    )
    assert (await state.get_state()) is None


async def test_receive_hours_and_rate_from_free_text_path_parses_both():
    message = AsyncMock()
    message.text = "1.5 900"
    state = _fsm_context()
    await state.update_data(visit_id="visit1", free_text_name="Своя работа", category="body")
    api = AsyncMock()
    api.get_visit.return_value = {"id": "visit1", "status": "received", "total_amount": "0.00"}
    api.list_work_items.return_value = []
    api.list_mechanics.return_value = []

    await receive_hours_and_rate(message, state, api=api)

    api.add_work_item.assert_awaited_once_with(
        "visit1", catalog_item_id=None, free_text_name="Своя работа", category="body",
        norm_hours=1.5, hourly_rate=900.0, assigned_mechanic_id=None,
    )


async def test_receive_hours_and_rate_reprompts_on_bad_rate_from_catalog_path():
    message = AsyncMock()
    message.text = "дорого"
    state = _fsm_context()
    await state.update_data(visit_id="visit1", catalog_item_id="cat1", category="maintenance", norm_hours=1.0)
    api = AsyncMock()

    await receive_hours_and_rate(message, state, api=api)

    api.add_work_item.assert_not_awaited()
    message.answer.assert_awaited_once_with("Введите число (часовую ставку).")


async def test_receive_hours_and_rate_reprompts_on_malformed_free_text_input():
    message = AsyncMock()
    message.text = "полтора"
    state = _fsm_context()
    await state.update_data(visit_id="visit1", free_text_name="Своя работа", category="body")
    api = AsyncMock()

    await receive_hours_and_rate(message, state, api=api)

    api.add_work_item.assert_not_awaited()
    message.answer.assert_awaited_once_with(
        "Введите нормо-часы и ставку через пробел, например: 1.5 800."
    )


async def test_receive_hours_and_rate_asks_for_text_on_non_text_message():
    message = AsyncMock()
    message.text = None
    state = _fsm_context()
    await state.set_state(AddWorkItemStates.waiting_for_hours_and_rate)
    await state.update_data(visit_id="visit1", free_text_name="Своя работа", category="body")
    api = AsyncMock()

    await receive_hours_and_rate(message, state, api=api)

    api.add_work_item.assert_not_awaited()
    message.answer.assert_awaited_once_with("Пожалуйста, отправьте ответ текстом.")
    assert (await state.get_state()) == AddWorkItemStates.waiting_for_hours_and_rate.state


async def test_receive_work_name_asks_for_text_on_non_text_message():
    message = AsyncMock()
    message.text = None
    state = _fsm_context()
    await state.set_state(AddWorkItemStates.waiting_for_name)
    api = AsyncMock()

    await receive_work_name(message, state, api=api)

    api.suggest_catalog.assert_not_awaited()
    message.answer.assert_awaited_once_with("Пожалуйста, отправьте ответ текстом.")


MECH_ID = "11111111-1111-1111-1111-111111111111"


async def test_receive_hours_and_rate_offers_mechanics_before_creating():
    message = AsyncMock()
    message.text = "1.5 900"
    state = _fsm_context()
    await state.set_state(AddWorkItemStates.waiting_for_hours_and_rate)
    await state.update_data(visit_id="visit1", free_text_name="Своя работа", category="body")
    api = AsyncMock()
    api.list_mechanics.return_value = [{"id": MECH_ID, "full_name": "Анна"}]

    await receive_hours_and_rate(message, state, api=api)

    api.add_work_item.assert_not_awaited()
    assert (await state.get_state()) == AddWorkItemStates.choosing_mechanic.state
    data = await state.get_data()
    assert (data["norm_hours"], data["hourly_rate"]) == (1.5, 900.0)
    markup = message.answer.await_args.kwargs["reply_markup"]
    buttons = [(b.text, b.callback_data) for row in markup.inline_keyboard for b in row]
    assert buttons == [("Анна", f"assign_mech:{encode_id(MECH_ID)}"), ("Без исполнителя", "assign_mech:none")]


async def _state_choosing_mechanic():
    state = _fsm_context()
    await state.set_state(AddWorkItemStates.choosing_mechanic)
    await state.update_data(
        visit_id="visit1", free_text_name="Своя работа", category="body", norm_hours=1.5, hourly_rate=900.0
    )
    return state


async def test_choose_mechanic_callback_creates_item_assigned_to_mechanic():
    callback = AsyncMock()
    callback.data = f"assign_mech:{encode_id(MECH_ID)}"
    state = await _state_choosing_mechanic()
    api = AsyncMock()
    api.get_visit.return_value = {"id": "visit1", "status": "received", "total_amount": "0.00"}
    api.list_work_items.return_value = []

    await choose_mechanic_callback(callback, state, api=api)

    api.add_work_item.assert_awaited_once_with(
        "visit1", catalog_item_id=None, free_text_name="Своя работа", category="body",
        norm_hours=1.5, hourly_rate=900.0, assigned_mechanic_id=MECH_ID,
    )
    assert (await state.get_state()) is None
    api.get_visit.assert_awaited_once_with("visit1")
    callback.answer.assert_awaited_once()


async def test_choose_mechanic_callback_none_creates_unassigned_item():
    callback = AsyncMock()
    callback.data = "assign_mech:none"
    state = await _state_choosing_mechanic()
    api = AsyncMock()
    api.get_visit.return_value = {"id": "visit1", "status": "received", "total_amount": "0.00"}
    api.list_work_items.return_value = []

    await choose_mechanic_callback(callback, state, api=api)

    assert api.add_work_item.await_args.kwargs["assigned_mechanic_id"] is None
    assert (await state.get_state()) is None
