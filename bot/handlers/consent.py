from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.api_client import ApiClient
from bot.states import PaperConsentStates
from bot.texts import CANCEL_HINT

router = Router()


async def start_paper_consent(message: Message, state: FSMContext, **kwargs) -> None:
    """Menu entry point (registered in bot/handlers/menu.py)."""
    await state.clear()
    await state.set_state(PaperConsentStates.waiting_for_phone)
    await message.answer(f"Введите телефон клиента {CANCEL_HINT}:")


@router.message(PaperConsentStates.waiting_for_phone)
async def receive_paper_phone(message: Message, state: FSMContext, **kwargs) -> None:
    await state.update_data(phone=message.text)
    await state.set_state(PaperConsentStates.waiting_for_full_name)
    await message.answer("Введите ФИО клиента:")


@router.message(PaperConsentStates.waiting_for_full_name)
async def receive_paper_full_name(message: Message, state: FSMContext, api: ApiClient, **kwargs) -> None:
    data = await state.get_data()
    full_name = message.text
    await api.register_paper_consent(full_name=full_name, phone=data["phone"])
    await state.clear()
    await message.answer(f"Клиент зарегистрирован (бумажное согласие): {full_name}")
