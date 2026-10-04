from unittest.mock import AsyncMock

from bot import wizard
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
from tests.bot.helpers import MASTER, buttons, fsm_context, make_callback, make_message, on_screens, shown

VISIT = "11111111-1111-1111-1111-111111111111"
MECH = "33333333-3333-3333-3333-333333333333"
SUGGESTION = {"id": "cat1", "name": "Замена масла", "category": "maintenance", "default_norm_hours": 1.0}


def _api():
    api = AsyncMock()
    api.get_visit.return_value = {"id": VISIT, "status": "in_progress", "total_amount": 0, "plate_number": "А1"}
    api.list_work_items.return_value = []
    api.suggest_catalog.return_value = [SUGGESTION]
    api.list_mechanics.return_value = [{"id": MECH, "full_name": "Петров"}]
    return api


async def _at(state, step, **data):
    await on_screens(state, ("visit", {"visit_id": VISIT}))
    await state.set_state(step)
    await state.update_data(wiz_name="add_work", wiz_steps=[], visit_id=VISIT, **data)


async def test_start_from_visit_card_asks_for_name():
    state = fsm_context()
    await on_screens(state, ("visit", {"visit_id": VISIT}))
    callback = make_callback("act:add_work")

    await start_add_work_item(callback, state, api=_api(), user=MASTER)

    assert await state.get_state() == AddWorkItemStates.waiting_for_name.state
    assert (await state.get_data())["visit_id"] == VISIT
    assert shown(callback)[0] == "Введите название работы:"


async def test_name_offers_catalog_suggestions():
    state = fsm_context()
    await _at(state, AddWorkItemStates.waiting_for_name)
    api = _api()
    message = make_message("замена масла")

    await receive_work_name(message, state, api=api, user=MASTER)

    api.suggest_catalog.assert_awaited_once_with("замена масла")
    text, markup = shown(message)
    assert text == "Выберите работу из справочника или укажите свою:"
    assert buttons(markup)[:2] == [("Замена масла", "catalog_pick:cat1"), ("Своя формулировка", "catalog_pick:none")]
    assert buttons(markup)[-2:] == [("‹ Назад", "wiz_back"), ("✖ Отмена", "wiz_cancel")]


async def test_catalog_pick_asks_only_rate():
    state = fsm_context()
    await _at(state, AddWorkItemStates.choosing_suggestion, suggestions={"cat1": SUGGESTION}, free_text_name="масло")
    callback = make_callback("catalog_pick:cat1")

    await choose_catalog_callback(callback, state, api=_api(), user=MASTER)

    data = await state.get_data()
    assert (data["catalog_item_id"], data["category"], data["norm_hours"]) == ("cat1", "maintenance", 1.0)
    assert shown(callback)[0] == "Введите часовую ставку:"


async def test_back_from_rate_then_own_wording_asks_hours_and_rate():
    state = fsm_context()
    await _at(state, AddWorkItemStates.choosing_suggestion, suggestions={"cat1": SUGGESTION}, free_text_name="масло")
    api = _api()
    await choose_catalog_callback(make_callback("catalog_pick:cat1"), state, api=api, user=MASTER)
    await wizard.back_callback(make_callback("wiz_back"), state, api=api, user=MASTER)
    await choose_catalog_callback(make_callback("catalog_pick:none"), state, api=api, user=MASTER)
    callback = make_callback("category_pick:body")

    await choose_category_callback(callback, state, api=api, user=MASTER)

    assert (await state.get_data())["catalog_item_id"] is None
    assert shown(callback)[0] == "Введите нормо-часы и ставку через пробел (например: 1.5 800):"


async def test_rate_then_mechanic_choice_then_create_and_back_to_card():
    state = fsm_context()
    await _at(state, AddWorkItemStates.waiting_for_hours_and_rate, catalog_item_id="cat1", category="maintenance", norm_hours=1.0)
    api = _api()
    message = make_message("1500")

    await receive_hours_and_rate(message, state, api=api, user=MASTER)

    assert buttons(shown(message)[1])[:2] == [("Петров", f"assign_mech:{encode_id(MECH)}"), ("Без исполнителя", "assign_mech:none")]

    callback = make_callback(f"assign_mech:{encode_id(MECH)}")
    await choose_mechanic_callback(callback, state, api=api, user=MASTER)

    api.add_work_item.assert_awaited_once_with(
        VISIT, catalog_item_id="cat1", free_text_name=None, category="maintenance",
        norm_hours=1.0, hourly_rate=1500.0, assigned_mechanic_id=MECH,
    )
    assert await state.get_state() is None
    assert (await state.get_data())["nav_stack"][-1] == ["visit", {"visit_id": VISIT}]


async def test_free_text_path_parses_hours_and_rate_and_unassigned():
    state = fsm_context()
    await _at(state, AddWorkItemStates.waiting_for_hours_and_rate, catalog_item_id=None, free_text_name="Покраска", category="body")
    api = _api()
    await receive_hours_and_rate(make_message("1.5 800"), state, api=api, user=MASTER)

    await choose_mechanic_callback(make_callback("assign_mech:none"), state, api=api, user=MASTER)

    kwargs = api.add_work_item.await_args.kwargs
    assert (kwargs["free_text_name"], kwargs["norm_hours"], kwargs["hourly_rate"], kwargs["assigned_mechanic_id"]) == (
        "Покраска", 1.5, 800.0, None,
    )
    assert (await state.get_data())["nav_stack"][-1] == ["visit", {"visit_id": VISIT}]


async def test_no_mechanics_creates_immediately():
    state = fsm_context()
    await _at(state, AddWorkItemStates.waiting_for_hours_and_rate, catalog_item_id="cat1", category="maintenance", norm_hours=1.0)
    api = _api()
    api.list_mechanics.return_value = []

    await receive_hours_and_rate(make_message("1500"), state, api=api, user=MASTER)

    assert api.add_work_item.await_args.kwargs["assigned_mechanic_id"] is None
    assert (await state.get_data())["nav_stack"][-1] == ["visit", {"visit_id": VISIT}]


async def test_bad_rate_and_bad_pair_reprompt():
    state = fsm_context()
    await _at(state, AddWorkItemStates.waiting_for_hours_and_rate, catalog_item_id="cat1", category="maintenance", norm_hours=1.0)
    message = make_message("дорого")
    await receive_hours_and_rate(message, state, api=_api(), user=MASTER)
    assert shown(message)[0] == "Введите число (часовую ставку).\n\nВведите часовую ставку:"

    await state.update_data(catalog_item_id=None)
    message = make_message("полтора")
    await receive_hours_and_rate(message, state, api=_api(), user=MASTER)
    assert shown(message)[0].startswith("Введите нормо-часы и ставку через пробел, например: 1.5 800.\n\n")


async def test_name_must_be_text():
    state = fsm_context()
    await _at(state, AddWorkItemStates.waiting_for_name)
    message = make_message(None)

    await receive_work_name(message, state, api=_api(), user=MASTER)

    assert shown(message)[0] == "Пожалуйста, отправьте ответ текстом.\n\nВведите название работы:"
