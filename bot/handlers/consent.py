from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from bot.api_client import ApiClient

router = Router()


class PaperConsentStates(StatesGroup):
    waiting_for_phone = State()
    waiting_for_full_name = State()


@router.message(F.text == "Регистрация клиента (бумага)")
async def start_paper_consent(message: Message, state: FSMContext, **kwargs) -> None:
    await state.set_state(PaperConsentStates.waiting_for_phone)
    await message.answer("Введите телефон клиента:")


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
