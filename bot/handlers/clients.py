from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot import nav, wizard
from bot.api_client import ApiClient
from bot.states import NewClientStates, NewVisitStates
from bot.texts import TEXT_REQUIRED

router = Router()


@wizard.step(NewClientStates.waiting_for_phone)
async def phone_prompt(state: FSMContext, api: ApiClient, user: dict):
    if await wizard.name(state) == "new_visit":
        return "Клиент не найден. Введите телефон клиента:", None
    return "Введите телефон клиента:", None


@wizard.step(NewClientStates.waiting_for_full_name)
async def full_name_prompt(state: FSMContext, api: ApiClient, user: dict):
    return "Введите ФИО клиента:", None


@router.message(Command("new_client"))
async def start_new_client(message: Message, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    if user["role"] == "mechanic":
        await message.answer("Недостаточно прав.")
        return
    await wizard.start(message, state, api, user, "new_client", NewClientStates.waiting_for_phone)


@router.message(NewClientStates.waiting_for_phone)
async def receive_phone(message: Message, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    if not message.text:
        await wizard.reprompt(message, state, api, user, TEXT_REQUIRED)
        return
    await state.update_data(phone=message.text)
    await wizard.goto(message, state, api, user, NewClientStates.waiting_for_full_name)


@router.message(NewClientStates.waiting_for_full_name)
async def receive_full_name(message: Message, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    if not message.text:
        await wizard.reprompt(message, state, api, user, TEXT_REQUIRED)
        return
    data = await state.get_data()
    client = await api.create_client(full_name=message.text, phone=data["phone"])
    if await wizard.name(state) == "new_visit":
        await state.update_data(client_id=str(client["id"]), created_client=client["full_name"])
        await wizard.goto(message, state, api, user, NewVisitStates.waiting_for_vehicle_query, commit=True)
        return
    await wizard.finish(state)
    await nav.home(message, state, api, user, notice=f"Клиент создан: {client['full_name']}")
