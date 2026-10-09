from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot import actions, nav, wizard
from bot.api_client import ApiClient, ApiMileageRollback
from bot.callback_ids import decode_id, encode_id
from bot.formatting import format_number
from bot.handlers.navigation import STAFF_ROLES
from bot.states import NewClientStates, NewVehicleStates, NewVisitStates, VisitCancelStates
from bot.texts import TEXT_REQUIRED
from bot.validators import is_valid_phone, is_valid_vin, looks_like_plate, normalize_plate, normalize_vin
from bot.visit_status import visit_status_label
from bot.work_item_status import work_item_icon, work_item_status_label

router = Router()

# Mirrors app/modules/visits/fsm.py ALLOWED_TRANSITIONS (UI hint only; backend enforces).
_NEXT_STATUS_BY_CURRENT = {
    "received": ["diagnostics", "cancelled"],
    "diagnostics": ["approval", "cancelled"],
    "approval": ["in_progress", "cancelled"],
    "in_progress": ["waiting_parts", "ready", "cancelled"],
    "waiting_parts": ["in_progress", "cancelled"],
    "ready": ["issued", "cancelled"],
}

MILEAGE_CONFIRM = "mileage_confirm"
CLIENT_ADD = "client_add"
VEHICLE_ADD = "vehicle_add"


def visit_header(visit: dict) -> list[str]:
    """Card title from the visit summary; tolerant of a partial dict."""
    title = " · ".join(
        part for part in (visit.get("plate_number"), visit.get("make_model"), visit.get("client_name")) if part
    )
    status_line = f"Статус: {visit_status_label(visit['status'])}"
    if visit.get("master_name"):
        status_line += f" · Мастер: {visit['master_name']}"
    return [title or "Заезд", status_line, f"Сумма: {format_number(visit['total_amount']) if 'total_amount' in visit else '—'}"]


def visit_card(visit: dict, work_items: list[dict]) -> nav.Rendered:
    """Header + numbered work list; one button per work item opens its screen."""
    lines = visit_header(visit)
    builder = InlineKeyboardBuilder()
    if work_items:
        lines.append("Работы:")
    for index, item in enumerate(work_items, start=1):
        mechanic = item.get("assigned_mechanic_name") or "без исполнителя"
        lines.append(f"{index}. {item['name']} — {work_item_status_label(item['status'])} · {mechanic}")
        builder.button(
            text=f"{work_item_icon(item['status'])} {index}. {item['name']} · {mechanic}",
            callback_data=nav.go_data("work", visit["id"], item["id"]),
        )
    builder.button(text="➕ Добавить работу", callback_data=actions.ADD_WORK)
    if visit["status"] in _NEXT_STATUS_BY_CURRENT:
        builder.button(text="🔄 Статус заезда", callback_data=nav.go_data("visit_status", visit["id"]))
    builder.button(text="📄 PDF", callback_data=actions.PDF)
    builder.adjust(1)
    return "\n".join(lines), builder.as_markup()


@nav.screen("visit", params=("visit_id",))
async def render_visit(api: ApiClient, user: dict, args: dict) -> nav.Rendered:
    visit = await api.get_visit(args["visit_id"])
    items = await api.list_work_items(args["visit_id"])
    return visit_card(visit, items)


@nav.screen("visit_status", params=("visit_id",))
async def render_visit_status(api: ApiClient, user: dict, args: dict) -> nav.Rendered:
    visit = await api.get_visit(args["visit_id"])
    builder = InlineKeyboardBuilder()
    for status in _NEXT_STATUS_BY_CURRENT.get(visit["status"], []):
        builder.button(text=visit_status_label(status), callback_data=f"{actions.VISIT_STATUS}:{status}")
    builder.adjust(1)
    return f"Статус сейчас: {visit_status_label(visit['status'])}\nСменить на:", builder.as_markup()


@router.callback_query(F.data.startswith(f"{actions.VISIT_STATUS}:"))
async def visit_status_callback(callback: CallbackQuery, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    args = await nav.top_args(callback, state, "visit_status")
    if args is None:
        return
    new_status = callback.data.rsplit(":", 1)[1]
    if new_status == "cancelled":
        await wizard.start(callback, state, api, user, "cancel_visit", VisitCancelStates.waiting_for_reason, visit_id=args["visit_id"])
        return
    await api.change_visit_status(args["visit_id"], new_status)
    await nav.pop(callback, state, api, user)


@wizard.step(VisitCancelStates.waiting_for_reason)
async def cancel_reason_prompt(state: FSMContext, api: ApiClient, user: dict):
    return "Укажите причину отмены заезда:", None


@router.message(VisitCancelStates.waiting_for_reason)
async def receive_cancel_reason(message: Message, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    if not message.text:
        await wizard.reprompt(message, state, api, user, TEXT_REQUIRED)
        return
    visit_id = (await state.get_data())["visit_id"]
    await api.change_visit_status(visit_id, "cancelled", reason=message.text)
    await wizard.finish(state)
    await nav.pop(message, state, api, user)  # off the status screen, back to the card


# --- New-visit wizard. Its client/vehicle creation steps live in clients.py
# and vehicles.py; they continue this wizard when wiz_name == "new_visit".


def _choices(rows: list[list[str]], prefix: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for value, label in rows:
        builder.button(text=label, callback_data=f"{prefix}:{value}")
    builder.adjust(1)
    return builder.as_markup()


@wizard.step(NewVisitStates.waiting_for_client_query)
async def client_query_prompt(state: FSMContext, api: ApiClient, user: dict):
    return "Введите телефон или ФИО клиента:", None


@wizard.step(NewVisitStates.client_not_found)
async def client_not_found_prompt(state: FSMContext, api: ApiClient, user: dict):
    query = (await state.get_data())["client_query"]
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Добавить клиента", callback_data=CLIENT_ADD)
    text = f"Клиент «{query}» не найден.\nВведите другой телефон или ФИО либо добавьте нового клиента."
    return text, builder.as_markup()


@wizard.step(NewVisitStates.choosing_client)
async def choosing_client_prompt(state: FSMContext, api: ApiClient, user: dict):
    return "Выберите клиента:", _choices((await state.get_data())["client_choices"], "client_pick")


@wizard.step(NewVisitStates.waiting_for_vehicle_query)
async def vehicle_query_prompt(state: FSMContext, api: ApiClient, user: dict):
    created = (await state.get_data()).get("created_client")
    prefix = f"Клиент создан: {created}\n" if created else ""
    return f"{prefix}Введите VIN или госномер авто:", None


@wizard.step(NewVisitStates.vehicle_not_found)
async def vehicle_not_found_prompt(state: FSMContext, api: ApiClient, user: dict):
    query = (await state.get_data())["vehicle_query"]
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Добавить автомобиль", callback_data=VEHICLE_ADD)
    text = f"Автомобиль «{query}» не найден.\nВведите другой VIN или госномер либо добавьте автомобиль."
    return text, builder.as_markup()


@wizard.step(NewVisitStates.choosing_vehicle)
async def choosing_vehicle_prompt(state: FSMContext, api: ApiClient, user: dict):
    return "Выберите автомобиль:", _choices((await state.get_data())["vehicle_choices"], "vehicle_pick")


@wizard.step(NewVisitStates.waiting_for_mileage)
async def mileage_prompt(state: FSMContext, api: ApiClient, user: dict):
    data = await state.get_data()
    if data.get("owner_name"):
        return f"Новый заезд: {data['owner_name']}. Введите пробег на приёмке:", None
    if data.get("created_vehicle"):
        return f"Автомобиль создан: {data['created_vehicle']}\nВведите пробег на приёмке:", None
    return "Введите пробег на приёмке:", None


@wizard.step(NewVisitStates.confirming_mileage)
async def confirm_mileage_prompt(state: FSMContext, api: ApiClient, user: dict):
    builder = InlineKeyboardBuilder()
    builder.button(text="Подтвердить пробег", callback_data=MILEAGE_CONFIRM)
    return f"{(await state.get_data())['rollback_message']}\nИли введите другой пробег.", builder.as_markup()


@wizard.step(NewVisitStates.choosing_master)
async def choosing_master_prompt(state: FSMContext, api: ApiClient, user: dict):
    return "Выберите мастера:", _choices((await state.get_data())["master_choices"], "master_pick")


@router.callback_query(F.data == actions.NEW_VISIT)
async def start_new_visit(callback: CallbackQuery, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    if user["role"] not in STAFF_ROLES:
        await callback.answer("Недостаточно прав")
        return
    await wizard.start(callback, state, api, user, "new_visit", NewVisitStates.waiting_for_client_query)


@router.callback_query(F.data == actions.NEW_VISIT_FOR)
async def new_visit_for_callback(callback: CallbackQuery, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    if user["role"] not in STAFF_ROLES:
        await callback.answer("Недостаточно прав")
        return
    args = await nav.top_args(callback, state, "vehicle")
    if args is None:
        return
    owner = await api.get_vehicle_owner(args["vehicle_id"])
    if owner is None:
        await callback.answer("У машины нет владельца — заведите заезд через «Новый заезд».", show_alert=True)
        return
    await wizard.start(
        callback, state, api, user, "new_visit", NewVisitStates.waiting_for_mileage,
        client_id=str(owner["id"]), vehicle_id=args["vehicle_id"], owner_name=owner["full_name"],
    )


@router.message(NewVisitStates.waiting_for_client_query)
@router.message(NewVisitStates.client_not_found)
async def receive_client_query(message: Message, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    if not message.text:
        await wizard.reprompt(message, state, api, user, TEXT_REQUIRED)
        return
    results = await api.search(message.text)
    client_ids = [r["id"] for r in results if r["entity"] == "client"][:5]
    if not client_ids:
        await state.update_data(client_query=message.text)
        await wizard.goto(message, state, api, user, NewVisitStates.client_not_found)
        return
    choices = [[str(cid), (await api.get_client(cid))["full_name"]] for cid in client_ids]
    await state.update_data(client_choices=choices)
    await wizard.goto(message, state, api, user, NewVisitStates.choosing_client)


@router.callback_query(NewVisitStates.choosing_client, F.data.startswith("client_pick:"))
async def choose_client_callback(callback: CallbackQuery, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    await state.update_data(client_id=callback.data.split(":", 1)[1])
    await wizard.goto(callback, state, api, user, NewVisitStates.waiting_for_vehicle_query)


@router.callback_query(NewVisitStates.client_not_found, F.data == CLIENT_ADD)
async def add_client_callback(callback: CallbackQuery, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    """Reuse the search query: a phone or a name is not asked again."""
    query = (await state.get_data())["client_query"]
    phone = query if is_valid_phone(query) else None
    is_name = any(c.isalpha() for c in query) and not any(c.isdigit() for c in query)
    await state.update_data(phone=phone, full_name=query if is_name else None)
    target = NewClientStates.waiting_for_full_name if phone else NewClientStates.waiting_for_phone
    await wizard.goto(callback, state, api, user, target)


@router.message(NewVisitStates.waiting_for_vehicle_query)
@router.message(NewVisitStates.vehicle_not_found)
async def receive_vehicle_query(message: Message, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    if not message.text:
        await wizard.reprompt(message, state, api, user, TEXT_REQUIRED)
        return
    results = await api.search(message.text)
    vehicle_ids = [r["id"] for r in results if r["entity"] == "vehicle"][:5]
    if not vehicle_ids:
        await state.update_data(vehicle_query=message.text)
        await wizard.goto(message, state, api, user, NewVisitStates.vehicle_not_found)
        return
    choices = [[str(vid), (await api.get_vehicle(vid))["plate_number"]] for vid in vehicle_ids]
    await state.update_data(vehicle_choices=choices)
    await wizard.goto(message, state, api, user, NewVisitStates.choosing_vehicle)


@router.callback_query(NewVisitStates.vehicle_not_found, F.data == VEHICLE_ADD)
async def add_vehicle_in_visit_callback(callback: CallbackQuery, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    """Reuse the search query: a plate or a VIN is not asked again."""
    query = (await state.get_data())["vehicle_query"]
    plate = normalize_plate(query) if looks_like_plate(query) else None
    vin = normalize_vin(query) if not plate and is_valid_vin(query) else None
    await state.update_data(plate_number=plate, vin=vin)
    target = NewVehicleStates.waiting_for_plate if vin else NewVehicleStates.waiting_for_vin
    await wizard.goto(callback, state, api, user, target)


@router.callback_query(NewVisitStates.choosing_vehicle, F.data.startswith("vehicle_pick:"))
async def choose_vehicle_callback(callback: CallbackQuery, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    await state.update_data(vehicle_id=callback.data.split(":", 1)[1])
    await wizard.goto(callback, state, api, user, NewVisitStates.waiting_for_mileage)


@router.message(NewVisitStates.waiting_for_mileage)
@router.message(NewVisitStates.confirming_mileage)
async def receive_mileage(message: Message, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    try:
        mileage = int(message.text)
    except (ValueError, TypeError):
        await wizard.reprompt(message, state, api, user, "Введите число (пробег в км).")
        return
    await state.update_data(mileage=mileage, mileage_confirmed=False)
    await _continue_after_mileage(message, state, api, user)


@router.callback_query(NewVisitStates.confirming_mileage, F.data == MILEAGE_CONFIRM)
async def confirm_mileage_callback(callback: CallbackQuery, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    await state.update_data(mileage_confirmed=True)
    await _continue_after_mileage(callback, state, api, user)


@router.callback_query(NewVisitStates.choosing_master, F.data.startswith("master_pick:"))
async def choose_master_callback(callback: CallbackQuery, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    await state.update_data(assigned_master_id=decode_id(callback.data.split(":", 1)[1]))
    await _create_visit(callback, state, api, user)


async def _continue_after_mileage(event: nav.Event, state: FSMContext, api: ApiClient, user: dict) -> None:
    data = await state.get_data()
    if user["role"] == "admin" and "assigned_master_id" not in data:
        masters = await api.list_masters()
        if not masters:
            await wizard.finish(state)
            await nav.refresh(event, state, api, user, notice="Сначала добавьте мастера через «Добавить сотрудника».")
            return
        await state.update_data(master_choices=[[encode_id(m["id"]), m["full_name"]] for m in masters])
        await wizard.goto(event, state, api, user, NewVisitStates.choosing_master)
        return
    await _create_visit(event, state, api, user)


async def _create_visit(event: nav.Event, state: FSMContext, api: ApiClient, user: dict) -> None:
    """Create the visit from wizard data; a MASTER is always the visit's master, an ADMIN picked one."""
    data = await state.get_data()
    try:
        visit = await api.create_visit(
            client_id=data["client_id"],
            vehicle_id=data["vehicle_id"],
            assigned_master_id=data.get("assigned_master_id", user["id"]),
            mileage_at_intake=data["mileage"],
            mileage_manually_confirmed=data["mileage_confirmed"],
        )
    except ApiMileageRollback as e:
        # Everything (incl. the chosen master) is kept until the mileage is
        # confirmed or a different one is typed — also accepted in this step.
        await state.update_data(rollback_message=e.message)
        await wizard.goto(event, state, api, user, NewVisitStates.confirming_mileage)
        return
    await wizard.finish(state)
    await nav.push(event, state, api, user, "visit", {"visit_id": str(visit["id"])})
