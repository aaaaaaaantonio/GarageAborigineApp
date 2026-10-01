from unittest.mock import AsyncMock

from bot.handlers.search import receive_search_query


async def test_receive_search_query_lists_client_results():
    message = AsyncMock()
    message.text = "Иванов"
    api = AsyncMock()
    api.search.return_value = [{"entity": "client", "id": "c1", "matched_field": "full_name"}]
    api.get_client.return_value = {"id": "c1", "full_name": "Иван Иванов", "phone_display": "+7 999 123-45-67"}

    await receive_search_query(message, api=api)

    api.search.assert_awaited_once_with("Иванов")
    api.get_client.assert_awaited_once_with("c1")
    message.answer.assert_awaited_once()
    assert "Иван Иванов" in message.answer.await_args.args[0]


async def test_receive_search_query_lists_vehicle_results():
    message = AsyncMock()
    message.text = "А123"
    api = AsyncMock()
    api.search.return_value = [{"entity": "vehicle", "id": "v1", "matched_field": "plate_number"}]
    api.get_vehicle.return_value = {"id": "v1", "make": "Toyota", "model": "Camry", "plate_number": "А123"}

    await receive_search_query(message, api=api)

    api.get_vehicle.assert_awaited_once_with("v1")
    assert "Toyota Camry" in message.answer.await_args.args[0]


async def test_receive_search_query_handles_no_matches():
    message = AsyncMock()
    message.text = "неизвестно"
    api = AsyncMock()
    api.search.return_value = []

    await receive_search_query(message, api=api)

    message.answer.assert_awaited_once_with("Ничего не найдено.")
