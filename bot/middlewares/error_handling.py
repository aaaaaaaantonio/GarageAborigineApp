import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from bot.api_client import ApiError

logger = logging.getLogger(__name__)

GENERIC_ERROR_TEXT = "Что-то пошло не так, попробуйте ещё раз."


class ErrorHandlingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        try:
            return await handler(event, data)
        except ApiError as e:
            await event.answer(e.message)
            return None
        except Exception:
            logger.exception("Unhandled error while processing %s", type(event).__name__)
            await event.answer(GENERIC_ERROR_TEXT)
            return None
