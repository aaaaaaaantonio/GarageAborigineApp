from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from app.core.enums import UserRole
from bot.keyboards import main_menu

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, user: dict, **kwargs) -> None:
    role = UserRole(user["role"])
    await message.answer("Добро пожаловать в CRM-бот автосервиса.", reply_markup=main_menu(role))
