from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot import nav
from bot.api_client import ApiClient
from bot.work_item_status import work_item_icon


@nav.screen("my_works")
async def render_my_works(api: ApiClient, user: dict, args: dict) -> nav.Rendered:
    items = await api.list_my_work_items()
    builder = InlineKeyboardBuilder()
    if not items:
        return "У вас нет назначенных работ.", builder.as_markup()
    for item in items:
        label = f"{work_item_icon(item['status'])} {item['name']}"
        if item.get("plate_number"):
            label += f" · {item['plate_number']}"
        builder.button(text=label, callback_data=nav.go_data("work", item["visit_id"], item["id"]))
    builder.adjust(1)
    return f"Мои работы ({len(items)})", builder.as_markup()
