from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot import nav, wizard
from bot.api_client import ApiClient, ApiConflict
from bot.states import NewClientStates, NewVisitStates
from bot.texts import TEXT_REQUIRED
from bot.validators import PHONE_FORMAT_ERROR, is_valid_phone

router = Router()


@wizard.step(NewClientStates.waiting_for_phone)
async def phone_prompt(state: FSMContext, api: ApiClient, user: dict):
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
    if not is_valid_phone(message.text):
        await wizard.reprompt(message, state, api, user, PHONE_FORMAT_ERROR)
        return
    await state.update_data(phone=message.text)
    full_name = (await state.get_data()).get("full_name")
    if full_name:  # typed as the search query in the new-visit wizard
        await _create_client(message, state, api, user, full_name)
        return
    await wizard.goto(message, state, api, user, NewClientStates.waiting_for_full_name)


@router.message(NewClientStates.waiting_for_full_name)
async def receive_full_name(message: Message, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    if not message.text:
        await wizard.reprompt(message, state, api, user, TEXT_REQUIRED)
        return
    await _create_client(message, state, api, user, message.text)


async def _create_client(message: Message, state: FSMContext, api: ApiClient, user: dict, full_name: str) -> None:
    data = await state.get_data()
    try:
        client = await api.create_client(full_name=full_name, phone=data["phone"])
    except ApiConflict as e:
        await wizard.retry(message, state, api, user, NewClientStates.waiting_for_phone, e.message)
        return
    if await wizard.name(state) == "new_visit":
        await state.update_data(client_id=str(client["id"]), created_client=client["full_name"])
        await wizard.goto(message, state, api, user, NewVisitStates.waiting_for_vehicle_query, commit=True)
        return
    await wizard.finish(state)
    await nav.home(message, state, api, user, notice=f"Клиент создан: {client['full_name']}")
