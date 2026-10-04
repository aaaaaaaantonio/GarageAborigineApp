import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramUnauthorizedError
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.token import TokenValidationError

from bot.config import settings
from bot.handlers import (
    admin,
    clients,
    consent,
    documents,
    fallback,
    menu,
    navigation,
    part_items,
    search,
    start,
    vehicles,
    visits,
    work_items,
    work_status,
)
from bot.middlewares.auth import AuthMiddleware
from bot.middlewares.error_handling import ErrorHandlingMiddleware


def setup_routers(dp: Dispatcher) -> None:
    # Order matters: start (commands) and menu (reply-keyboard buttons) come
    # first so they win over any FSM-state handler; fallback answers stale
    # callbacks; search catches all remaining text and must stay last.
    dp.include_router(start.router)
    dp.include_router(menu.router)
    dp.include_router(clients.router)
    dp.include_router(vehicles.router)
    dp.include_router(visits.router)
    dp.include_router(work_items.router)
    dp.include_router(part_items.router)
    dp.include_router(work_status.router)
    dp.include_router(documents.router)
    dp.include_router(consent.router)
    dp.include_router(admin.router)
    dp.include_router(navigation.router)
    dp.include_router(fallback.router)
    dp.include_router(search.router)


logger = logging.getLogger(__name__)

TOKEN_HINT = "Get the token from @BotFather and set BOT_TOKEN in .env (format 123456789:AA...)."


async def create_bot(token: str) -> Bot:
    """Build the Bot and confirm Telegram accepts the token; exit with one clear line if not."""
    try:
        bot = Bot(token=token)
    except TokenValidationError:
        logger.error("BOT_TOKEN is empty or malformed. %s", TOKEN_HINT)
        raise SystemExit(1)
    try:
        me = await bot.get_me()
    except TelegramUnauthorizedError:
        await bot.session.close()
        logger.error("Telegram rejected BOT_TOKEN (revoked or mistyped). %s", TOKEN_HINT)
        raise SystemExit(1)
    logger.info("Authorized as @%s", me.username)
    return bot


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    bot = await create_bot(settings.bot_token)
    dp = Dispatcher(storage=MemoryStorage())
    dp.message.middleware(ErrorHandlingMiddleware())
    dp.message.middleware(AuthMiddleware())
    dp.callback_query.middleware(ErrorHandlingMiddleware())
    dp.callback_query.middleware(AuthMiddleware())
    setup_routers(dp)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
