from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot import nav
from bot.api_client import ApiClient
from bot.work_item_status import work_item_icon

MY_WORKS_LIMIT = 30


@nav.screen("my_works")
async def render_my_works(api: ApiClient, user: dict, args: dict) -> nav.Rendered:
    # Finished work stays assigned forever; without the filter and the cap the
    # list would outgrow Telegram's inline-keyboard limit.
    items = [i for i in await api.list_my_work_items() if i["status"] != "ready"]
    builder = InlineKeyboardBuilder()
    if not items:
        return "У вас нет назначенных работ.", builder.as_markup()
    for item in items[:MY_WORKS_LIMIT]:
        label = f"{work_item_icon(item['status'])} {item['name']}"
        if item.get("plate_number"):
            label += f" · {item['plate_number']}"
        builder.button(text=label, callback_data=nav.go_data("work", item["visit_id"], item["id"]))
    builder.adjust(1)
    text = f"Мои работы ({len(items)})"
    if len(items) > MY_WORKS_LIMIT:
        text += f"\nПоказаны первые {MY_WORKS_LIMIT}."
    return text, builder.as_markup()
