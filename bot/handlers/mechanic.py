from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.api_client import ApiClient
from bot.work_item_status import FROM_MY_WORK_ITEMS, add_work_status_buttons

router = Router()


async def show_my_work_items(message: Message, state: FSMContext, api: ApiClient, **kwargs) -> None:
    """Menu entry point (registered in bot/handlers/menu.py)."""
    await state.clear()
    items = await api.list_my_work_items()
    if not items:
        await message.answer("У вас нет назначенных работ.")
        return
    for item in items:
        builder = InlineKeyboardBuilder()
        has_buttons = add_work_status_buttons(builder, item["visit_id"], item, FROM_MY_WORK_ITEMS)
        await message.answer(
            f"{item['name']} — {item['status']} (заезд {item['visit_id']})",
            reply_markup=builder.as_markup() if has_buttons else None,
        )
