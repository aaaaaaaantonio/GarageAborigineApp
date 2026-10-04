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
from bot.formatting import format_date, format_day, format_number
from bot.handlers.visits import send_visit_card
from bot.visit_status import visit_status_label
from bot.work_item_status import work_item_status_label

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


STAFF_ROLES = {"admin", "master"}


async def send_client_card(message: Message, api: ApiClient, client_id: str) -> None:
    client = await api.get_client(client_id)
    vehicles = await api.list_client_vehicles(client_id)
    builder = InlineKeyboardBuilder()
    for v in vehicles:
        builder.button(
            text=f"🚗 {v['make']} {v['model']} ({v['plate_number']})",
            callback_data=f"vehicle_open:{encode_id(v['id'])}",
        )
    builder.button(text="📋 Заезды клиента", callback_data=f"visits_by_client:{encode_id(client_id)}")
    builder.adjust(1)
    await message.answer(f"👤 {client['full_name']}\n{client['phone_display']}", reply_markup=builder.as_markup())


async def send_vehicle_card(message: Message, api: ApiClient, user: dict, vehicle_id: str) -> None:
    vehicle = await api.get_vehicle(vehicle_id)
    vid = encode_id(vehicle_id)
    builder = InlineKeyboardBuilder()
    if user["role"] in STAFF_ROLES:
        # Owner is personal data: mechanics never request it (the API would 403).
        owner = await api.get_vehicle_owner(vehicle_id)
        if owner is not None:
            builder.button(text=f"👤 Владелец: {owner['full_name']}", callback_data=f"client_open:{encode_id(owner['id'])}")
        builder.button(text="📋 Заезды по машине", callback_data=f"visits_by_vehicle:{vid}")
        if owner is not None:
            builder.button(text="➕ Новый заезд", callback_data=f"new_visit_for:{vid}")
    builder.button(text="🔧 История работ", callback_data=f"work_history:{vid}")
    builder.adjust(1)
    text = (
        f"🚗 {vehicle['make']} {vehicle['model']} · {vehicle['plate_number']}\n"
        f"VIN: {vehicle['vin']} · Пробег: {format_number(vehicle['mileage_current'])} км"
    )
    await message.answer(text, reply_markup=builder.as_markup())


def _id_from(callback: CallbackQuery) -> str:
    return decode_id(callback.data.split(":", 1)[1])


@router.callback_query(F.data.startswith("client_open:"))
async def client_open_callback(callback: CallbackQuery, api: ApiClient, **kwargs) -> None:
    await send_client_card(callback.message, api, _id_from(callback))
    await callback.answer()


@router.callback_query(F.data.startswith("vehicle_open:"))
async def vehicle_open_callback(callback: CallbackQuery, api: ApiClient, user: dict, **kwargs) -> None:
    await send_vehicle_card(callback.message, api, user, _id_from(callback))
    await callback.answer()


async def _send_history(callback: CallbackQuery, api: ApiClient, user: dict, **filters) -> None:
    result = await api.list_visits(**filters)
    await send_visit_list(callback.message, result, user["id"], "Заезды", "Заездов ещё не было.", with_date=True)
    await callback.answer()


@router.callback_query(F.data.startswith("visits_by_client:"))
async def visits_by_client_callback(callback: CallbackQuery, api: ApiClient, user: dict, **kwargs) -> None:
    await _send_history(callback, api, user, client_id=_id_from(callback))


@router.callback_query(F.data.startswith("visits_by_vehicle:"))
async def visits_by_vehicle_callback(callback: CallbackQuery, api: ApiClient, user: dict, **kwargs) -> None:
    await _send_history(callback, api, user, vehicle_id=_id_from(callback))


@router.callback_query(F.data.startswith("work_history:"))
async def work_history_callback(callback: CallbackQuery, api: ApiClient, **kwargs) -> None:
    vehicle_id = _id_from(callback)
    vehicle = await api.get_vehicle(vehicle_id)
    history = await api.get_vehicle_work_history(vehicle_id)
    if not history["items"]:
        await callback.message.answer("Работ по машине ещё не было.")
        await callback.answer()
        return
    lines = [f"🔧 История работ · {vehicle['plate_number']}"]
    current_visit = None
    for item in history["items"]:
        if item["visit_id"] != current_visit:
            current_visit = item["visit_id"]
            lines.append(f"{format_date(item['visit_at'])} · {format_number(item['mileage'])} км")
        lines.append(f"  • {item['name']} — {work_item_status_label(item['status'])}")
    if history["has_more"]:
        lines.append("Показаны последние 30 работ.")
    await callback.message.answer("\n".join(lines))
    await callback.answer()
