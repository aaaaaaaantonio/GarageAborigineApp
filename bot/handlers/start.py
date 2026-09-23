from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.core.enums import UserRole
from bot.keyboards import main_menu

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, user: dict, state: FSMContext, **kwargs) -> None:
    await state.clear()
    role = UserRole(user["role"])
    await message.answer("Добро пожаловать в CRM-бот автосервиса.", reply_markup=main_menu(role))


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext, **kwargs) -> None:
    await state.clear()
    await message.answer("Действие отменено.")
