from unittest.mock import AsyncMock

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.base import StorageKey

from bot.handlers.part_items import receive_part_name, receive_quantity_and_price, start_add_part_item
from bot.handlers.visits import _encode_id
from bot.states import AddPartItemStates


def _fsm_context() -> FSMContext:
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=1, user_id=1)
    return FSMContext(storage=storage, key=key)


async def test_start_add_part_item_asks_for_name_and_stores_ids():
    visit_id = "11111111-1111-1111-1111-111111111111"
    work_item_id = "22222222-2222-2222-2222-222222222222"
    callback = AsyncMock()
    callback.data = f"add_part:{_encode_id(visit_id)}:{_encode_id(work_item_id)}"
    state = _fsm_context()

    await start_add_part_item(callback, state)

    data = await state.get_data()
    assert data == {"visit_id": visit_id, "work_item_id": work_item_id}
    assert (await state.get_state()) == AddPartItemStates.waiting_for_name.state
    callback.message.answer.assert_awaited_once_with("Введите название запчасти:")
    callback.answer.assert_awaited_once()


async def test_receive_part_name_asks_for_quantity_and_price():
    message = AsyncMock()
    message.text = "Фильтр"
    state = _fsm_context()
    await state.update_data(visit_id="visit1", work_item_id="wi1")

    await receive_part_name(message, state)

    data = await state.get_data()
    assert data["name"] == "Фильтр"
    assert (await state.get_state()) == AddPartItemStates.waiting_for_quantity_and_price.state


async def test_receive_quantity_and_price_creates_part_item_and_refreshes_card():
    message = AsyncMock()
    message.text = "2 350"
    state = _fsm_context()
    await state.update_data(visit_id="visit1", work_item_id="wi1", name="Фильтр")
    api = AsyncMock()
    api.add_part_item.return_value = {"id": "p1", "name": "Фильтр"}
    api.get_visit.return_value = {"id": "visit1", "status": "in_progress", "total_amount": "0.00"}
    api.list_work_items.return_value = []

    await receive_quantity_and_price(message, state, api=api)

    api.add_part_item.assert_awaited_once_with(
        visit_id="visit1", work_item_id="wi1", name="Фильтр", quantity=2, unit_price=350.0
    )
    api.get_visit.assert_awaited_once_with("visit1")
    message.answer.assert_awaited()
    assert (await state.get_state()) is None


async def test_receive_quantity_and_price_reprompts_on_malformed_input():
    message = AsyncMock()
    message.text = "две штуки"
    state = _fsm_context()
    await state.update_data(visit_id="visit1", work_item_id="wi1", name="Фильтр")
    api = AsyncMock()

    await receive_quantity_and_price(message, state, api=api)

    api.add_part_item.assert_not_awaited()
    message.answer.assert_awaited_once_with("Введите количество и цену через пробел, например: 2 350.")
    assert (await state.get_state()) == AddPartItemStates.waiting_for_quantity_and_price.state
