from unittest.mock import AsyncMock

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.base import StorageKey

from bot.handlers.work_items import (
    choose_catalog_callback,
    choose_category_callback,
    receive_hours_and_rate,
    receive_work_name,
)
from bot.states import AddWorkItemStates


def _fsm_context() -> FSMContext:
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=1, user_id=1)
    return FSMContext(storage=storage, key=key)


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

    await receive_hours_and_rate(message, state, api=api)

    api.add_work_item.assert_awaited_once_with(
        "visit1", catalog_item_id="cat1", free_text_name=None, category="maintenance",
        norm_hours=1.0, hourly_rate=800.0,
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

    await receive_hours_and_rate(message, state, api=api)

    api.add_work_item.assert_awaited_once_with(
        "visit1", catalog_item_id=None, free_text_name="Своя работа", category="body",
        norm_hours=1.5, hourly_rate=900.0,
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
