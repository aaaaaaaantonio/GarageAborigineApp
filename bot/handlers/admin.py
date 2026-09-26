from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.api_client import ApiClient
from bot.states import NewStaffStates

router = Router()


@router.message(F.text == "Добавить сотрудника")
async def start_new_staff(message: Message, state: FSMContext, **kwargs) -> None:
    builder = InlineKeyboardBuilder()
    for role in ("admin", "master", "mechanic"):
        builder.button(text=role, callback_data=f"staff_role:{role}")
    builder.adjust(1)
    await state.set_state(NewStaffStates.choosing_role)
    await message.answer("Выберите роль:", reply_markup=builder.as_markup())


@router.callback_query(lambda c: c.data.startswith("staff_role:"))
async def choose_staff_role(callback, state: FSMContext, **kwargs) -> None:
    _, role = callback.data.split(":")
    await state.update_data(role=role)
    await state.set_state(NewStaffStates.waiting_for_full_name)
    await callback.message.answer("Введите ФИО сотрудника:")
    await callback.answer()


@router.message(NewStaffStates.waiting_for_full_name)
async def receive_staff_full_name(message: Message, state: FSMContext, **kwargs) -> None:
    await state.update_data(full_name=message.text)
    await state.set_state(NewStaffStates.waiting_for_telegram_id)
    await message.answer("Введите Telegram ID сотрудника (или «-», если пока неизвестен):")


@router.message(NewStaffStates.waiting_for_telegram_id)
async def receive_telegram_id(message: Message, state: FSMContext, api: ApiClient, **kwargs) -> None:
    text = message.text.strip()

    # Handle dash as None
    if text == "-":
        telegram_id = None
    else:
        # Validate that it's a valid integer
        try:
            telegram_id = int(text)
        except ValueError:
            await message.answer("Telegram ID должен быть числом или «-».")
            return

    data = await state.get_data()
    user = await api.create_staff_user(role=data["role"], full_name=data["full_name"], telegram_id=telegram_id)
    await state.clear()
    await message.answer(f"Сотрудник создан: {user['full_name']}")
