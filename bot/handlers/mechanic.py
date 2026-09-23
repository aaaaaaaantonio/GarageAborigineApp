from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.api_client import ApiClient

router = Router()

_STATUS_ORDER = ["not_ready", "in_progress", "waiting_parts", "ready"]


def _next_status(current: str) -> str | None:
    if current not in _STATUS_ORDER:
        return None
    index = _STATUS_ORDER.index(current)
    if index + 1 >= len(_STATUS_ORDER):
        return None
    return _STATUS_ORDER[index + 1]


@router.message(F.text == "Мои работы")
async def show_my_work_items(message: Message, api: ApiClient, **kwargs) -> None:
    items = await api.list_my_work_items()
    if not items:
        await message.answer("У вас нет назначенных работ.")
        return
    for index, item in enumerate(items, start=1):
        name = item["free_text_name"] or f"работа №{index}"
        text = f"{name} — {item['status']} (заезд {item['visit_id']})"
        next_status = _next_status(item["status"])
        markup = None
        if next_status:
            builder = InlineKeyboardBuilder()
            builder.button(
                text=f"→ {next_status}",
                callback_data=f"work_status:{item['id']}:{next_status}",
            )
            markup = builder.as_markup()
        await message.answer(text, reply_markup=markup)


@router.callback_query(lambda c: c.data.startswith("work_status:"))
async def change_work_status_callback(callback: CallbackQuery, api: ApiClient, **kwargs) -> None:
    _, item_id, new_status = callback.data.split(":")
    # The backend route requires a syntactically-valid UUID in the visit_id URL path segment
    # but never reads its value, so reusing item_id satisfies the URL shape without needing
    # the real visit_id here (which is dropped from callback_data to stay under 64 bytes).
    item = await api.update_work_item_status(item_id, item_id, new_status)
    await callback.message.answer(f"Статус обновлён: {item['status']}")
    await callback.answer()
