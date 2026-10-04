from unittest.mock import AsyncMock

from bot.handlers.part_items import receive_part_name, receive_quantity_and_price, start_add_part_item
from bot.states import AddPartItemStates
from tests.bot.helpers import MASTER, MECHANIC, fsm_context, make_callback, make_message, on_screens, shown

VISIT = "11111111-1111-1111-1111-111111111111"
ITEM = "22222222-2222-2222-2222-222222222222"
WORK = ("work", {"visit_id": VISIT, "item_id": ITEM})


def _api():
    api = AsyncMock()
    api.get_visit.return_value = {"id": VISIT, "status": "in_progress", "total_amount": 0}
    api.list_work_items.return_value = [
        {"id": ITEM, "name": "Замена масла", "status": "in_progress", "approved_by_client": True, "assigned_mechanic_name": None},
    ]
    return api


async def test_start_from_work_screen_asks_for_name():
    state = fsm_context()
    await on_screens(state, WORK)
    callback = make_callback("act:add_part")

    await start_add_part_item(callback, state, api=_api(), user=MASTER)

    data = await state.get_data()
    assert (data["visit_id"], data["work_item_id"]) == (VISIT, ITEM)
    assert shown(callback)[0] == "Введите название запчасти:"


async def test_name_then_quantity_and_price_creates_and_returns_to_work():
    state = fsm_context()
    await on_screens(state, WORK)
    await state.set_state(AddPartItemStates.waiting_for_name)
    await state.update_data(wiz_name="add_part", wiz_steps=[], visit_id=VISIT, work_item_id=ITEM)
    api = _api()

    message = make_message("Фильтр")
    await receive_part_name(message, state, api=api, user=MASTER)
    assert shown(message)[0] == "Введите количество и цену через пробел (например: 2 350):"

    await receive_quantity_and_price(make_message("2 350"), state, api=api, user=MASTER)

    api.add_part_item.assert_awaited_once_with(visit_id=VISIT, work_item_id=ITEM, name="Фильтр", quantity=2, unit_price=350.0)
    assert await state.get_state() is None
    assert (await state.get_data())["nav_stack"][-1] == list(WORK)


async def test_malformed_quantity_reprompts():
    state = fsm_context()
    await on_screens(state, WORK)
    await state.set_state(AddPartItemStates.waiting_for_quantity_and_price)
    await state.update_data(wiz_name="add_part", wiz_steps=[], visit_id=VISIT, work_item_id=ITEM, name="Фильтр")
    message = make_message("две")

    await receive_quantity_and_price(message, state, api=_api(), user=MASTER)

    assert shown(message)[0].startswith("Введите количество и цену через пробел, например: 2 350.\n\n")


async def test_part_name_must_be_text():
    state = fsm_context()
    await state.set_state(AddPartItemStates.waiting_for_name)
    await state.update_data(wiz_name="add_part", wiz_steps=[])
    message = make_message(None)

    await receive_part_name(message, state, api=_api(), user=MASTER)

    assert shown(message)[0] == "Пожалуйста, отправьте ответ текстом.\n\nВведите название запчасти:"


async def test_mechanic_cannot_start_add_part():
    state = fsm_context()
    await on_screens(state, WORK)
    callback = make_callback("act:add_part")

    await start_add_part_item(callback, state, api=_api(), user=MECHANIC)

    assert await state.get_state() is None
    callback.answer.assert_awaited_once_with("Недостаточно прав")
