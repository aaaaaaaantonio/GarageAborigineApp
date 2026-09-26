from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.api_client import ApiClient
from bot.states import NewClientStates, NewVisitStates
from bot.texts import CANCEL_HINT

router = Router()


@router.message(Command("new_client"))
async def start_new_client(message: Message, state: FSMContext, **kwargs) -> None:
    await state.clear()
    await state.set_state(NewClientStates.waiting_for_phone)
    await message.answer(f"Введите телефон клиента {CANCEL_HINT}:")


@router.message(NewClientStates.waiting_for_phone)
async def receive_phone(message: Message, state: FSMContext, **kwargs) -> None:
    await state.update_data(phone=message.text)
    await state.set_state(NewClientStates.waiting_for_full_name)
    await message.answer("Введите ФИО клиента:")


@router.message(NewClientStates.waiting_for_full_name)
async def receive_full_name(message: Message, state: FSMContext, api: ApiClient, **kwargs) -> None:
    data = await state.get_data()
    client = await api.create_client(full_name=message.text, phone=data["phone"])
    if data.get("return_flow") == "new_visit":
        await state.update_data(client_id=client["id"])
        await state.set_state(NewVisitStates.waiting_for_vehicle_query)
        await message.answer(f"Клиент создан: {client['full_name']}\nВведите VIN или гос.номер авто:")
        return
    await state.clear()
    await message.answer(f"Клиент создан: {client['full_name']}")
