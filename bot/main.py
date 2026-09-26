import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from bot.config import settings
from bot.handlers import start, clients, vehicles, visits, work_items, part_items, mechanic, documents, consent, admin, search
from bot.middlewares.auth import AuthMiddleware
from bot.middlewares.error_handling import ErrorHandlingMiddleware


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    bot = Bot(token=settings.bot_token)
    dp = Dispatcher(storage=MemoryStorage())
    dp.message.middleware(ErrorHandlingMiddleware())
    dp.message.middleware(AuthMiddleware())
    dp.callback_query.middleware(ErrorHandlingMiddleware())
    dp.callback_query.middleware(AuthMiddleware())
    dp.include_router(start.router)
    dp.include_router(clients.router)
    dp.include_router(vehicles.router)
    dp.include_router(visits.router)
    dp.include_router(work_items.router)
    dp.include_router(part_items.router)
    dp.include_router(mechanic.router)
    dp.include_router(documents.router)
    dp.include_router(consent.router)
    dp.include_router(admin.router)
    dp.include_router(search.router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
