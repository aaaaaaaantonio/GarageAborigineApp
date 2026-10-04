from unittest.mock import AsyncMock

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from bot.callback_ids import encode_id
from bot.handlers.search import SEARCH_RESULTS_LIMIT, receive_search_query, start_search

C1 = "11111111-1111-1111-1111-111111111111"
V1 = "22222222-2222-2222-2222-222222222222"
MASTER = {"id": "m1", "role": "master"}
MECHANIC = {"id": "k1", "role": "mechanic"}


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

    await receive_search_query(message, api=api, user=MASTER)

    assert message.answer.await_args.args[0] == "Найдено: 2"
    assert _buttons(message) == [
        ("👤 Иван Иванов — +7 999 123-45-67", f"client_open:{encode_id(C1)}"),
        ("🚗 Toyota Camry (А123ВС77)", f"vehicle_open:{encode_id(V1)}"),
    ]


async def test_search_shows_first_results_and_asks_to_refine():
    message = AsyncMock()
    message.text = "Toyota"
    ids = [f"{n:08d}-0000-0000-0000-000000000000" for n in range(SEARCH_RESULTS_LIMIT + 3)]
    api = AsyncMock()
    api.search.return_value = [{"entity": "vehicle", "id": i, "matched_field": "make"} for i in ids]
    api.get_vehicle.return_value = {"make": "Toyota", "model": "Camry", "plate_number": "А1"}

    await receive_search_query(message, api=api, user=MASTER)

    assert api.get_vehicle.await_count == SEARCH_RESULTS_LIMIT
    assert message.answer.await_args.args[0] == "Найдено: 13\nПоказаны первые 10 — уточните запрос."


async def test_search_handles_no_matches():
    message = AsyncMock()
    message.text = "неизвестно"
    api = AsyncMock()
    api.search.return_value = []

    await receive_search_query(message, api=api, user=MASTER)

    message.answer.assert_awaited_once_with("Ничего не найдено.")


async def test_mechanic_no_matches_hint_mentions_vin_and_plate():
    message = AsyncMock()
    message.text = "Сидоров"
    api = AsyncMock()
    api.search.return_value = []

    await receive_search_query(message, api=api, user=MECHANIC)

    message.answer.assert_awaited_once_with("Ничего не найдено. Механик может искать машину по VIN или госномеру.")


async def test_start_search_prompt_depends_on_role():
    state = FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=1, user_id=1))
    master_msg, mechanic_msg = AsyncMock(), AsyncMock()

    await start_search(master_msg, state, user=MASTER)
    await start_search(mechanic_msg, state, user=MECHANIC)

    master_msg.answer.assert_awaited_once_with("Введите телефон, VIN, гос.номер или имя клиента:")
    mechanic_msg.answer.assert_awaited_once_with("Введите VIN или гос.номер:")
