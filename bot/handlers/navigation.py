"""Read-only navigation: visit lists, client/vehicle cards, histories.

Callbacks here are not bound to an FSM state, so buttons in old messages
keep working; a deleted entity surfaces as the API's 404 ("Не найдено").
"""
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.api_client import ApiClient
from bot.callback_ids import decode_id, encode_id
from bot.formatting import format_day
from bot.handlers.visits import send_visit_card
from bot.visit_status import visit_status_label

router = Router()

LIST_TRUNCATED = "Показаны последние 30."


def visit_list_markup(visits: list[dict], user_id: str, with_date: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for visit in visits:
        if with_date:
            parts = [format_day(visit["created_at"]), visit["plate_number"]]
        else:
            parts = [visit["plate_number"], visit["client_name"]]
        parts.append(visit_status_label(visit["status"]))
        star = "⭐ " if str(visit["assigned_master_id"]) == str(user_id) else ""
        builder.button(text=star + " · ".join(parts), callback_data=f"visit_open:{encode_id(visit['id'])}")
    builder.adjust(1)
    return builder.as_markup()


async def send_visit_list(
    message: Message, result: dict, user_id: str, title: str, empty_text: str, with_date: bool
) -> None:
    visits = result["items"]
    if not visits:
        await message.answer(empty_text)
        return
    text = f"{title} ({len(visits)})"
    if result["has_more"]:
        text += f"\n{LIST_TRUNCATED}"
    await message.answer(text, reply_markup=visit_list_markup(visits, user_id, with_date))


async def show_active_visits(message: Message, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    """Menu entry point (registered in bot/handlers/menu.py)."""
    await state.clear()
    result = await api.list_visits(active=True)
    await send_visit_list(message, result, user["id"], "Заезды в работе", "Незакрытых заездов нет.", with_date=False)


@router.callback_query(F.data.startswith("visit_open:"))
async def open_visit_callback(callback: CallbackQuery, api: ApiClient, **kwargs) -> None:
    visit_id = decode_id(callback.data.split(":", 1)[1])
    visit = await api.get_visit(visit_id)
    items = await api.list_work_items(visit_id)
    await send_visit_card(callback.message, visit, items)
    await callback.answer()
