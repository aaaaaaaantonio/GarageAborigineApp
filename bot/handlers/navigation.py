"""Read-only screens: visit lists, client/vehicle cards, histories."""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot import actions, nav
from bot.api_client import ApiClient
from bot.callback_ids import decode_id, encode_id
from bot.formatting import format_date, format_day, format_number
from bot.periods import days_since
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


ACTIVE_FILTERS = [
    ("all", "Все"), ("mine", "Мои"), ("appr", "Согласование"), ("parts", "Запчасти"),
    ("ready", "Готовы"), ("free", "Без механика"), ("stale", "Долго стоят"),
]
ACTIVE_SORTS = [("date", "По дате"), ("stale", "Долго стоят"), ("status", "По статусу")]


def _active_filter_params(code: str, user_id: str) -> dict:
    return {
        "mine": {"master_id": user_id},
        "appr": {"status": ["approval"]},
        "parts": {"status": ["waiting_parts"]},
        "ready": {"status": ["ready"]},
        "free": {"unassigned_work": True},
        "stale": {"stale": True},
    }.get(code, {})


def option_rows(key: str, options: list[tuple[str, str]], current: str, per_row: int = 3) -> list[list[InlineKeyboardButton]]:
    row_buttons = [nav.option_button(label, key, value, current) for value, label in options]
    return [row_buttons[i : i + per_row] for i in range(0, len(row_buttons), per_row)]


async def master_cycle(api: ApiClient, current: str) -> InlineKeyboardButton:
    """Admin-only picker over masters; '-' means all of them."""
    masters = await api.list_masters()
    options = [("-", "Все мастера"), *[(encode_id(m["id"]), m["full_name"]) for m in masters]]
    return nav.cycle_button("👤", "m", options, current)


@nav.screen("active_visits")
async def render_active_visits(api: ApiClient, user: dict, args: dict) -> nav.Rendered:
    is_admin = user["role"] == "admin"
    code, sort, master = args.get("f", "all"), args.get("s", "date"), args.get("m", "-")
    filters = ACTIVE_FILTERS if not is_admin else [f for f in ACTIVE_FILTERS if f[0] != "mine"]
    params = _active_filter_params(code, user["id"])
    if is_admin and master != "-":
        params["master_id"] = decode_id(master)
    result = await api.list_visits(active=True, sort=sort, **params)
    rows = option_rows("f", filters, code)
    controls = [nav.cycle_button("↕", "s", ACTIVE_SORTS, sort)]
    if is_admin:
        controls.append(await master_cycle(api, master))
    rows.append(controls)
    visits = result["items"]
    for visit in visits:
        label = " · ".join([visit["plate_number"], visit["client_name"], visit_status_label(visit["status"])])
        if (days := days_since(visit.get("status_changed_at"))) >= 1:
            label += f" · {days} дн."
        star = "⭐ " if str(visit["assigned_master_id"]) == str(user["id"]) else ""
        rows.append([InlineKeyboardButton(text=star + label, callback_data=nav.go_data("visit", visit["id"]))])
    markup = InlineKeyboardMarkup(inline_keyboard=rows)
    if not visits:
        return ("Незакрытых заездов нет." if code == "all" and master == "-" else "Нет заездов с этим фильтром."), markup
    text = f"Заезды в работе ({result.get('total_count', len(visits))})"
    if result["has_more"]:
        text += f"\nПоказаны первые {len(visits)}."
    return text, markup


@nav.screen("client", params=("client_id",))
async def render_client(api: ApiClient, user: dict, args: dict) -> nav.Rendered:
    client = await api.get_client(args["client_id"])
    vehicles = await api.list_client_vehicles(args["client_id"])
    builder = InlineKeyboardBuilder()
    for v in vehicles:
        builder.button(text=f"🚗 {v['make']} {v['model']} ({v['plate_number']})", callback_data=nav.go_data("vehicle", v["id"]))
    if user["role"] in STAFF_ROLES:
        builder.button(text="➕ Добавить автомобиль", callback_data=actions.ADD_VEHICLE)
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
