from unittest.mock import AsyncMock, MagicMock, patch

from bot.middlewares.auth import AuthMiddleware


async def test_known_user_is_injected_and_handler_called():
    middleware = AuthMiddleware()
    handler = AsyncMock(return_value="handled")
    event = AsyncMock()
    event.from_user.id = 42
    data = {}

    # ApiClient is instantiated twice by the middleware (once to look up the
    # user, once to build the authenticated data["api"] client). A plain
    # `patch(...)` mock shares a single `.return_value` across every call
    # regardless of the constructor args it was given, so both instances
    # would collapse into one object and `.user_id` would never reflect the
    # `user_id=...` kwarg. Use a side_effect so each call gets its own mock
    # configured from its own kwargs, matching how the real ApiClient behaves.
    def make_client(*args, **kwargs):
        client = MagicMock(**kwargs)
        client.get_user_by_telegram = AsyncMock(
            return_value={"id": "u1", "role": "master"}
        )
        return client

    with patch("bot.middlewares.auth.ApiClient", side_effect=make_client):
        result = await middleware(handler, event, data)

    assert result == "handled"
    handler.assert_awaited_once_with(event, data)
    assert data["user"] == {"id": "u1", "role": "master"}
    assert data["api"].user_id == "u1"


async def test_unknown_user_is_rejected_without_calling_handler():
    middleware = AuthMiddleware()
    handler = AsyncMock()
    event = AsyncMock()
    event.from_user.id = 99
    data = {}

    with patch("bot.middlewares.auth.ApiClient") as MockClient:
        MockClient.return_value.get_user_by_telegram = AsyncMock(return_value=None)
        result = await middleware(handler, event, data)

    assert result is None
    handler.assert_not_awaited()
    event.answer.assert_awaited_once()
    assert "администратору" in event.answer.await_args.args[0]
