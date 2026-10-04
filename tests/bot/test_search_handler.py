from unittest.mock import AsyncMock

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from bot.callback_ids import encode_id
from bot.handlers.search import SEARCH_RESULTS_LIMIT, receive_search_query, search_page_callback, start_search

C1 = "11111111-1111-1111-1111-111111111111"
V1 = "22222222-2222-2222-2222-222222222222"
MASTER = {"id": "m1", "role": "master"}
MECHANIC = {"id": "k1", "role": "mechanic"}


def _state() -> FSMContext:
    return FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=1, user_id=1))


def _buttons(message):
    markup = message.answer.await_args.kwargs["reply_markup"]
    return [(b.text, b.callback_data) for row in markup.inline_keyboard for b in row]


async def test_search_results_are_buttons_to_cards():
    message = AsyncMock()
    message.text = "Иванов"
    api = AsyncMock()
    api.search.return_value = [
        {"entity": "client", "id": C1, "matched_field": "full_name"},
        {"entity": "vehicle", "id": V1, "matched_field": "plate_number"},
    ]
    api.get_client.return_value = {"id": C1, "full_name": "Иван Иванов", "phone_display": "+7 999 123-45-67"}
    api.get_vehicle.return_value = {"id": V1, "make": "Toyota", "model": "Camry", "plate_number": "А123ВС77"}

    await receive_search_query(message, _state(), api=api, user=MASTER)

    assert message.answer.await_args.args[0] == "Найдено: 2"
    assert _buttons(message) == [
        ("👤 Иван Иванов — +7 999 123-45-67", f"client_open:{encode_id(C1)}"),
        ("🚗 Toyota Camry (А123ВС77)", f"vehicle_open:{encode_id(V1)}"),
    ]


def _vehicles(count):
    ids = [f"{n:08d}-0000-0000-0000-000000000000" for n in range(count)]
    return [{"entity": "vehicle", "id": i, "matched_field": "make"} for i in ids]


def _api_with(results):
    api = AsyncMock()
    api.search.return_value = results
    api.get_vehicle.side_effect = lambda vid: {"make": "Toyota", "model": "Camry", "plate_number": vid[:8]}
    return api


async def test_search_over_limit_shows_first_page_with_next_button():
    message = AsyncMock()
    message.text = "Toyota"
    api = _api_with(_vehicles(23))
    state = _state()

    await receive_search_query(message, state, api=api, user=MASTER)

    assert api.get_vehicle.await_count == SEARCH_RESULTS_LIMIT
    assert message.answer.await_args.args[0] == "Найдено: 23 · стр. 1/3\nМожно уточнить запрос."
    buttons = _buttons(message)
    assert len(buttons) == SEARCH_RESULTS_LIMIT + 1
    assert buttons[0][0] == "🚗 Toyota Camry (00000000)"
    assert buttons[-1] == ("Далее ›", "search_page:1")
    assert (await state.get_data())["search_query"] == "Toyota"


async def test_search_page_callback_edits_message_to_requested_page():
    api = _api_with(_vehicles(23))
    state = _state()
    await state.update_data(search_query="Toyota")
    callback = AsyncMock()
    callback.data = "search_page:2"

    await search_page_callback(callback, state, api=api)

    api.search.assert_awaited_once_with("Toyota")
    text = callback.message.edit_text.await_args.args[0]
    markup = callback.message.edit_text.await_args.kwargs["reply_markup"]
    buttons = [(b.text, b.callback_data) for row in markup.inline_keyboard for b in row]
    assert text == "Найдено: 23 · стр. 3/3\nМожно уточнить запрос."
    assert [t for t, _ in buttons[:-1]] == [f"🚗 Toyota Camry ({n:08d})" for n in range(20, 23)]
    assert buttons[-1] == ("‹ Назад", "search_page:1")
    callback.answer.assert_awaited_once()


async def test_search_middle_page_has_both_arrows_in_one_row():
    api = _api_with(_vehicles(23))
    state = _state()
    await state.update_data(search_query="Toyota")
    callback = AsyncMock()
    callback.data = "search_page:1"

    await search_page_callback(callback, state, api=api)

    markup = callback.message.edit_text.await_args.kwargs["reply_markup"]
    assert [b.callback_data for b in markup.inline_keyboard[-1]] == ["search_page:0", "search_page:2"]


async def test_search_page_without_saved_query_asks_to_search_again():
    api = AsyncMock()
    callback = AsyncMock()
    callback.data = "search_page:1"

    await search_page_callback(callback, _state(), api=api)

    api.search.assert_not_awaited()
    callback.answer.assert_awaited_once_with("Поиск устарел — введите запрос заново.", show_alert=True)


async def test_search_within_limit_has_no_page_buttons():
    message = AsyncMock()
    message.text = "Toyota"
    api = _api_with(_vehicles(SEARCH_RESULTS_LIMIT))

    await receive_search_query(message, _state(), api=api, user=MASTER)

    assert message.answer.await_args.args[0] == f"Найдено: {SEARCH_RESULTS_LIMIT}"
    assert not any(cb.startswith("search_page:") for _, cb in _buttons(message))


async def test_search_handles_no_matches():
    message = AsyncMock()
    message.text = "неизвестно"
    api = AsyncMock()
    api.search.return_value = []

    await receive_search_query(message, _state(), api=api, user=MASTER)

    message.answer.assert_awaited_once_with("Ничего не найдено.")


async def test_mechanic_no_matches_hint_mentions_vin_and_plate():
    message = AsyncMock()
    message.text = "Сидоров"
    api = AsyncMock()
    api.search.return_value = []

    await receive_search_query(message, _state(), api=api, user=MECHANIC)

    message.answer.assert_awaited_once_with("Ничего не найдено. Механик может искать машину по VIN или госномеру.")


async def test_start_search_prompt_depends_on_role():
    state = FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=1, user_id=1))
    master_msg, mechanic_msg = AsyncMock(), AsyncMock()

    await start_search(master_msg, state, user=MASTER)
    await start_search(mechanic_msg, state, user=MECHANIC)

    master_msg.answer.assert_awaited_once_with("Введите телефон, VIN, гос.номер или имя клиента:")
    mechanic_msg.answer.assert_awaited_once_with("Введите VIN или гос.номер:")
