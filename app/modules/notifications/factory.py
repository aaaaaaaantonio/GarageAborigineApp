from functools import lru_cache

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.modules.notifications.interfaces import NotificationSender
from app.modules.notifications.logging_sender import LoggingNotificationSender
from app.modules.notifications.telegram_sender import TelegramNotificationSender


@lru_cache
def _bot() -> Bot | None:
    if not settings.telegram_bot_token:
        return None
    return Bot(token=settings.telegram_bot_token)


def get_notification_sender(session: AsyncSession) -> NotificationSender:
    bot = _bot()
    if bot is None:
        return LoggingNotificationSender(session)
    return TelegramNotificationSender(session, bot)
