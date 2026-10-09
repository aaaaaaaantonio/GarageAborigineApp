from unittest.mock import AsyncMock

from bot.callback_ids import encode_id
from bot.handlers.search import SEARCH_RESULTS_LIMIT, receive_search_query, render_search, render_search_results, search_page_callback
from tests.bot.helpers import MASTER, MECHANIC, buttons, fsm_context, make_callback, make_message, on_screens, shown

C1 = "11111111-1111-1111-1111-111111111111"
V1 = "22222222-2222-2222-2222-222222222222"


def _vehicles(n):
    return [{"entity": "vehicle", "id": f"{i:08d}-0000-0000-0000-000000000000", "matched_field": "make"} for i in range(n)]


def _api(results):
    api = AsyncMock()
    api.search.return_value = results
    api.get_client.return_value = {"id": C1, "full_name": "Иван Иванов", "phone_display": "+7 999 123-45-67"}
    api.get_vehicle.return_value = {"id": V1, "make": "Toyota", "model": "Camry", "plate_number": "А123ВС77"}
    return api


async def test_search_prompt_depends_on_role():
    assert (await render_search(AsyncMock(), MASTER, {}))[0] == "Введите телефон, VIN, гос.номер или имя клиента:"
    assert (await render_search(AsyncMock(), MECHANIC, {}))[0] == "Введите VIN или гос.номер:"


async def test_typed_text_pushes_results_screen():
    state = fsm_context()
    await on_screens(state, ("search", {}))
    api = _api([{"entity": "client", "id": C1}, {"entity": "vehicle", "id": V1}])
    message = make_message("Иванов")

    await receive_search_query(message, state, api=api, user=MASTER)

    assert (await state.get_data())["nav_stack"][-1] == ["search_results", {"query": "Иванов", "page": 0}]
    text, markup = shown(message)
    assert text == "Найдено: 2"
    assert buttons(markup)[:2] == [
        ("👤 Иван Иванов — +7 999 123-45-67", f"go:client:{encode_id(C1)}"),
        ("🚗 Toyota Camry (А123ВС77)", f"go:vehicle:{encode_id(V1)}"),
    ]


async def test_results_over_limit_show_first_page_with_next():
    text, markup = await render_search_results(_api(_vehicles(12)), MASTER, {"query": "Toyota", "page": 0})

    assert text == "Найдено: 12 · стр. 1/2\nМожно уточнить запрос."
    assert len(buttons(markup)) == SEARCH_RESULTS_LIMIT + 1
    assert buttons(markup)[-1] == ("Далее ›", "act:spage:1")


async def test_middle_page_has_both_arrows_in_one_row():
    _, markup = await render_search_results(_api(_vehicles(25)), MASTER, {"query": "Toyota", "page": 1})

    assert [(b.text, b.callback_data) for b in markup.inline_keyboard[-1]] == [("‹ Пред.", "act:spage:0"), ("Далее ›", "act:spage:2")]


async def test_page_out_of_range_is_clamped():
    text, _ = await render_search_results(_api(_vehicles(12)), MASTER, {"query": "Toyota", "page": 9})

    assert text.startswith("Найдено: 12 · стр. 2/2")


async def test_page_button_replaces_results_in_place():
    state = fsm_context()
    await on_screens(state, ("search_results", {"query": "Toyota", "page": 0}))
    callback = make_callback("act:spage:1")

    await search_page_callback(callback, state, api=_api(_vehicles(12)), user=MASTER)

    stack = (await state.get_data())["nav_stack"]
    assert stack == [["menu", {}], ["search_results", {"query": "Toyota", "page": 1}]]
    assert shown(callback)[0].startswith("Найдено: 12 · стр. 2/2")


async def test_no_matches_texts_by_role():
    assert (await render_search_results(_api([]), MASTER, {"query": "x", "page": 0}))[0] == "Ничего не найдено."
    assert (await render_search_results(_api([]), MECHANIC, {"query": "x", "page": 0}))[0] == (
        "Ничего не найдено. Механик может искать машину по VIN или госномеру."
    )
