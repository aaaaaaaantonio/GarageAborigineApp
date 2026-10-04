"""Read-only screens: visit lists, client/vehicle cards, histories."""
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot import actions, nav
from bot.api_client import ApiClient
from bot.formatting import format_date, format_day, format_number
from bot.visit_status import visit_status_label
from bot.work_item_status import work_item_status_label

LIST_TRUNCATED = "Показаны последние 30."
STAFF_ROLES = {"admin", "master"}


def visit_list(result: dict, user_id: str, title: str, empty_text: str, with_date: bool) -> nav.Rendered:
    builder = InlineKeyboardBuilder()
    visits = result["items"]
    if not visits:
        return empty_text, builder.as_markup()
    for visit in visits:
        if with_date:
            parts = [format_day(visit["created_at"]), visit["plate_number"]]
        else:
            parts = [visit["plate_number"], visit["client_name"]]
        parts.append(visit_status_label(visit["status"]))
        star = "⭐ " if str(visit["assigned_master_id"]) == str(user_id) else ""
        builder.button(text=star + " · ".join(parts), callback_data=nav.go_data("visit", visit["id"]))
    builder.adjust(1)
    text = f"{title} ({len(visits)})"
    if result["has_more"]:
        text += f"\n{LIST_TRUNCATED}"
    return text, builder.as_markup()


@nav.screen("active_visits")
async def render_active_visits(api: ApiClient, user: dict, args: dict) -> nav.Rendered:
    result = await api.list_visits(active=True)
    return visit_list(result, user["id"], "Заезды в работе", "Незакрытых заездов нет.", with_date=False)


@nav.screen("client", params=("client_id",))
async def render_client(api: ApiClient, user: dict, args: dict) -> nav.Rendered:
    client = await api.get_client(args["client_id"])
    vehicles = await api.list_client_vehicles(args["client_id"])
    builder = InlineKeyboardBuilder()
    for v in vehicles:
        builder.button(text=f"🚗 {v['make']} {v['model']} ({v['plate_number']})", callback_data=nav.go_data("vehicle", v["id"]))
    builder.button(text="📋 Заезды клиента", callback_data=nav.go_data("client_visits", args["client_id"]))
    builder.adjust(1)
    return f"👤 {client['full_name']}\n{client['phone_display']}", builder.as_markup()


@nav.screen("vehicle", params=("vehicle_id",))
async def render_vehicle(api: ApiClient, user: dict, args: dict) -> nav.Rendered:
    vehicle_id = args["vehicle_id"]
    vehicle = await api.get_vehicle(vehicle_id)
    builder = InlineKeyboardBuilder()
    if user["role"] in STAFF_ROLES:
        # Owner is personal data: mechanics never request it (the API would 403).
        owner = await api.get_vehicle_owner(vehicle_id)
        if owner is not None:
            builder.button(text=f"👤 Владелец: {owner['full_name']}", callback_data=nav.go_data("client", owner["id"]))
        builder.button(text="📋 Заезды по машине", callback_data=nav.go_data("vehicle_visits", vehicle_id))
        if owner is not None:
            builder.button(text="➕ Новый заезд", callback_data=actions.NEW_VISIT_FOR)
    builder.button(text="🔧 История работ", callback_data=nav.go_data("work_history", vehicle_id))
    builder.adjust(1)
    text = (
        f"🚗 {vehicle['make']} {vehicle['model']} · {vehicle['plate_number']}\n"
        f"VIN: {vehicle['vin']} · Пробег: {format_number(vehicle['mileage_current'])} км"
    )
    return text, builder.as_markup()


@nav.screen("client_visits", params=("client_id",))
async def render_client_visits(api: ApiClient, user: dict, args: dict) -> nav.Rendered:
    result = await api.list_visits(client_id=args["client_id"])
    return visit_list(result, user["id"], "Заезды", "Заездов ещё не было.", with_date=True)


@nav.screen("vehicle_visits", params=("vehicle_id",))
async def render_vehicle_visits(api: ApiClient, user: dict, args: dict) -> nav.Rendered:
    result = await api.list_visits(vehicle_id=args["vehicle_id"])
    return visit_list(result, user["id"], "Заезды", "Заездов ещё не было.", with_date=True)


@nav.screen("work_history", params=("vehicle_id",))
async def render_work_history(api: ApiClient, user: dict, args: dict) -> nav.Rendered:
    vehicle = await api.get_vehicle(args["vehicle_id"])
    history = await api.get_vehicle_work_history(args["vehicle_id"])
    no_buttons = InlineKeyboardBuilder().as_markup()
    if not history["items"]:
        return "Работ по машине ещё не было.", no_buttons
    lines = [f"🔧 История работ · {vehicle['plate_number']}"]
    current_visit = None
    for item in history["items"]:
        if item["visit_id"] != current_visit:
            current_visit = item["visit_id"]
            lines.append(f"{format_date(item['visit_at'])} · {format_number(item['mileage'])} км")
        lines.append(f"  • {item['name']} — {work_item_status_label(item['status'])}")
    if history["has_more"]:
        lines.append("Показаны последние 30 работ.")
    return "\n".join(lines), no_buttons
