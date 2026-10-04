from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot import actions, nav, wizard
from bot.api_client import ApiClient
from bot.states import NewStaffStates
from bot.texts import TEXT_REQUIRED

router = Router()

_ROLE_LABELS = {"admin": "Администратор", "master": "Мастер", "mechanic": "Механик"}


@wizard.step(NewStaffStates.choosing_role)
async def role_prompt(state: FSMContext, api: ApiClient, user: dict):
    builder = InlineKeyboardBuilder()
    for role, label in _ROLE_LABELS.items():
        builder.button(text=label, callback_data=f"staff_role:{role}")
    builder.adjust(1)
    return "Выберите роль:", builder.as_markup()


@wizard.step(NewStaffStates.waiting_for_full_name)
async def staff_name_prompt(state: FSMContext, api: ApiClient, user: dict):
    return "Введите ФИО сотрудника:", None


@wizard.step(NewStaffStates.waiting_for_telegram_id)
async def telegram_id_prompt(state: FSMContext, api: ApiClient, user: dict):
    return "Введите Telegram ID сотрудника (или «-», если пока неизвестен):", None


@router.callback_query(F.data == actions.NEW_STAFF)
async def start_new_staff(callback: CallbackQuery, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    if user["role"] != "admin":
        await callback.answer("Недостаточно прав")
        return
    await wizard.start(callback, state, api, user, "new_staff", NewStaffStates.choosing_role)


@router.callback_query(NewStaffStates.choosing_role, F.data.startswith("staff_role:"))
async def choose_staff_role(callback: CallbackQuery, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    await state.update_data(role=callback.data.split(":", 1)[1])
    await wizard.goto(callback, state, api, user, NewStaffStates.waiting_for_full_name)


@router.message(NewStaffStates.waiting_for_full_name)
async def receive_staff_full_name(message: Message, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    if not message.text:
        await wizard.reprompt(message, state, api, user, TEXT_REQUIRED)
        return
    await state.update_data(full_name=message.text)
    await wizard.goto(message, state, api, user, NewStaffStates.waiting_for_telegram_id)


@router.message(NewStaffStates.waiting_for_telegram_id)
async def receive_telegram_id(message: Message, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    text = (message.text or "").strip()
    if text == "-":
        telegram_id = None
    else:
        try:
            telegram_id = int(text)
        except ValueError:
            await wizard.reprompt(message, state, api, user, "Telegram ID должен быть числом или «-».")
            return
    data = await state.get_data()
    staff = await api.create_staff_user(role=data["role"], full_name=data["full_name"], telegram_id=telegram_id)
    await wizard.finish(state)
    await nav.home(message, state, api, user, notice=f"Сотрудник создан: {staff['full_name']}")
