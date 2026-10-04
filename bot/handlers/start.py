from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, ReplyKeyboardRemove

from bot import nav
from bot.api_client import ApiClient

router = Router()

WELCOME = "Добро пожаловать в CRM-бот автосервиса."


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    await nav.clear_wizard(state)
    # Also takes the old reply keyboard away for users who still have it.
    await message.answer(WELCOME, reply_markup=ReplyKeyboardRemove())
    await nav.home(message, state, api, user)


@router.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    await nav.clear_wizard(state)
    await nav.home(message, state, api, user)


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    await nav.clear_wizard(state)
    await nav.refresh(message, state, api, user, notice="Действие отменено.")
