from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from bot.api_client import ApiClient


class AuthMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        telegram_id = event.from_user.id
        client = ApiClient()
        user = await client.get_user_by_telegram(telegram_id)
        if user is None:
            await event.answer("Обратитесь к администратору, ваш Telegram не привязан к учётной записи.")
            return None
        data["user"] = user
        data["api"] = ApiClient(user_id=user["id"])
        return await handler(event, data)
