from unittest.mock import AsyncMock

from bot.api_client import ApiConflict, ApiNotFound
from bot.middlewares.error_handling import ErrorHandlingMiddleware


async def test_handler_result_is_returned_when_no_error():
    middleware = ErrorHandlingMiddleware()
    handler = AsyncMock(return_value="handled")
    event = AsyncMock()
    data = {}

    result = await middleware(handler, event, data)

    assert result == "handled"
    handler.assert_awaited_once_with(event, data)
    event.answer.assert_not_awaited()


async def test_api_not_found_is_caught_and_replied():
    middleware = ErrorHandlingMiddleware()
    error = ApiNotFound("Клиент не найден")
    handler = AsyncMock(side_effect=error)
    event = AsyncMock()
    data = {}

    result = await middleware(handler, event, data)

    assert result is None
    event.answer.assert_awaited_once_with("Клиент не найден")


async def test_api_conflict_is_caught_and_replied():
    middleware = ErrorHandlingMiddleware()
    error = ApiConflict("Переход между статусами не разрешён")
    handler = AsyncMock(side_effect=error)
    event = AsyncMock()
    data = {}

    result = await middleware(handler, event, data)

    assert result is None
    event.answer.assert_awaited_once_with("Переход между статусами не разрешён")


async def test_unexpected_error_is_logged_and_replied_generically(caplog):
    middleware = ErrorHandlingMiddleware()
    handler = AsyncMock(side_effect=ValueError("boom"))
    event = AsyncMock()
    data = {}

    result = await middleware(handler, event, data)

    assert result is None
    event.answer.assert_awaited_once_with("Что-то пошло не так, попробуйте ещё раз.")
    assert "boom" in caplog.text
