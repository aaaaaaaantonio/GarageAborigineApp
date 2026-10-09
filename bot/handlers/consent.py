from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot import actions, nav, wizard
from bot.api_client import ApiClient, ApiConflict
from bot.handlers.navigation import STAFF_ROLES
from bot.states import PaperConsentStates
from bot.texts import TEXT_REQUIRED
from bot.validators import PHONE_FORMAT_ERROR, is_valid_phone

router = Router()


@wizard.step(PaperConsentStates.waiting_for_phone)
async def paper_phone_prompt(state: FSMContext, api: ApiClient, user: dict):
    return "Введите телефон клиента:", None


@wizard.step(PaperConsentStates.waiting_for_full_name)
async def paper_name_prompt(state: FSMContext, api: ApiClient, user: dict):
    return "Введите ФИО клиента:", None


@router.callback_query(F.data == actions.PAPER_CONSENT)
async def start_paper_consent(callback: CallbackQuery, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    if user["role"] not in STAFF_ROLES:
        await callback.answer("Недостаточно прав")
        return
    await wizard.start(callback, state, api, user, "paper_consent", PaperConsentStates.waiting_for_phone)


@router.message(PaperConsentStates.waiting_for_phone)
async def receive_paper_phone(message: Message, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    if not message.text:
        await wizard.reprompt(message, state, api, user, TEXT_REQUIRED)
        return
    if not is_valid_phone(message.text):
        await wizard.reprompt(message, state, api, user, PHONE_FORMAT_ERROR)
        return
    await state.update_data(phone=message.text)
    await wizard.goto(message, state, api, user, PaperConsentStates.waiting_for_full_name)


@router.message(PaperConsentStates.waiting_for_full_name)
async def receive_paper_full_name(message: Message, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    if not message.text:
        await wizard.reprompt(message, state, api, user, TEXT_REQUIRED)
        return
    phone = (await state.get_data())["phone"]
    try:
        result = await api.register_paper_consent(full_name=message.text, phone=phone)
    except ApiConflict as e:
        await wizard.retry(message, state, api, user, PaperConsentStates.waiting_for_phone, e.message)
        return
    await wizard.finish(state)
    # The card offers "➕ Добавить автомобиль" right away.
    notice = f"Клиент зарегистрирован (бумажное согласие): {message.text}"
    await nav.push(message, state, api, user, "client", {"client_id": result["client_id"]}, notice=notice)
