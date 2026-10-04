from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.api_client import ApiClient, ApiMileageRollback
from bot.callback_ids import decode_id, encode_id
from bot.formatting import format_number
from bot.states import NewClientStates, NewVehicleStates, NewVisitStates, VisitCancelStates
from bot.texts import CANCEL_HINT, TEXT_REQUIRED
from bot.visit_status import visit_status_label
from bot.work_item_status import FROM_VISIT_CARD, add_work_status_buttons, work_item_status_label

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


def visit_header(visit: dict) -> list[str]:
    """Card title from the visit summary; tolerant of a partial dict."""
    title = " · ".join(
        part for part in (visit.get("plate_number"), visit.get("make_model"), visit.get("client_name")) if part
    )
    status_line = f"Статус: {visit_status_label(visit['status'])}"
    if visit.get("master_name"):
        status_line += f" · Мастер: {visit['master_name']}"
    return [title or "Заезд", status_line, f"Сумма: {format_number(visit['total_amount']) if 'total_amount' in visit else '—'}"]


async def send_visit_card(message: Message, visit: dict, work_items: list[dict]) -> None:
    builder = InlineKeyboardBuilder()
    for status in _NEXT_STATUS_BY_CURRENT.get(visit["status"], []):
        builder.button(text=visit_status_label(status), callback_data=f"visit_status:{visit['id']}:{status}")
    lines = visit_header(visit)
    if work_items:
        lines.append("Работы:")
    for index, item in enumerate(work_items, start=1):
        name = item["name"]
        lines.append(f"{index}. {name} — {work_item_status_label(item['status'])}")
        visit_b64, item_b64 = encode_id(visit["id"]), encode_id(item["id"])
        if item.get("approved_by_client") is False:
            builder.button(text=f"✅ {name}", callback_data=f"approve_work:{visit_b64}:{item_b64}")
        add_work_status_buttons(builder, visit["id"], item, FROM_VISIT_CARD, label_prefix=f"🔄 {name} ")
        builder.button(text=f"🔧 {name}", callback_data=f"add_part:{visit_b64}:{item_b64}")
    builder.button(text="➕ Добавить работу", callback_data=f"add_work:{visit['id']}")
    builder.button(text="Сформировать PDF", callback_data=f"gen_doc:{visit['id']}")
    builder.adjust(1)
    await message.answer("\n".join(lines), reply_markup=builder.as_markup())


async def refresh_visit_card(message: Message, api: ApiClient, visit_id: str) -> None:
    visit = await api.get_visit(visit_id)
    items = await api.list_work_items(visit_id)
    await send_visit_card(message, visit, items)


async def start_new_visit(message: Message, state: FSMContext, **kwargs) -> None:
    """Menu entry point (registered in bot/handlers/menu.py)."""
    await state.clear()
    await state.set_state(NewVisitStates.waiting_for_client_query)
    await message.answer(f"Введите телефон или ФИО клиента {CANCEL_HINT}:")


@router.message(NewVisitStates.waiting_for_client_query)
async def receive_client_query(message: Message, state: FSMContext, api: ApiClient, **kwargs) -> None:
    results = await api.search(message.text)
    client_ids = [r["id"] for r in results if r["entity"] == "client"][:5]
    if not client_ids:
        await state.update_data(return_flow="new_visit")
        await state.set_state(NewClientStates.waiting_for_phone)
        await message.answer("Клиент не найден. Введите телефон клиента:")
        return
    builder = InlineKeyboardBuilder()
    for client_id in client_ids:
        client = await api.get_client(client_id)
        builder.button(text=client["full_name"], callback_data=f"client_pick:{client_id}")
    builder.adjust(1)
    await state.set_state(NewVisitStates.choosing_client)
    await message.answer("Выберите клиента:", reply_markup=builder.as_markup())


@router.callback_query(NewVisitStates.choosing_client, F.data.startswith("client_pick:"))
async def choose_client_callback(callback: CallbackQuery, state: FSMContext, **kwargs) -> None:
    _, client_id = callback.data.split(":")
    await state.update_data(client_id=client_id)
    await state.set_state(NewVisitStates.waiting_for_vehicle_query)
    await callback.message.answer("Введите VIN или гос.номер авто:")
    await callback.answer()


@router.message(NewVisitStates.waiting_for_vehicle_query)
async def receive_vehicle_query(message: Message, state: FSMContext, api: ApiClient, **kwargs) -> None:
    results = await api.search(message.text)
    vehicle_ids = [r["id"] for r in results if r["entity"] == "vehicle"][:5]
    if not vehicle_ids:
        await state.update_data(return_flow="new_visit")
        await state.set_state(NewVehicleStates.waiting_for_vin)
        await message.answer("Автомобиль не найден. Введите VIN:")
        return
    builder = InlineKeyboardBuilder()
    for vehicle_id in vehicle_ids:
        vehicle = await api.get_vehicle(vehicle_id)
        builder.button(text=vehicle["plate_number"], callback_data=f"vehicle_pick:{vehicle_id}")
    builder.adjust(1)
    await state.set_state(NewVisitStates.choosing_vehicle)
    await message.answer("Выберите автомобиль:", reply_markup=builder.as_markup())


@router.callback_query(NewVisitStates.choosing_vehicle, F.data.startswith("vehicle_pick:"))
async def choose_vehicle_callback(callback: CallbackQuery, state: FSMContext, **kwargs) -> None:
    _, vehicle_id = callback.data.split(":")
    await state.update_data(vehicle_id=vehicle_id)
    await state.set_state(NewVisitStates.waiting_for_mileage)
    await callback.message.answer("Введите пробег на приёмке:")
    await callback.answer()


async def _create_visit(message: Message, state: FSMContext, api: ApiClient, user: dict) -> None:
    """Create the visit from FSM data: client_id, vehicle_id, mileage, mileage_confirmed,
    and assigned_master_id (ADMIN's pick; a MASTER is always the master)."""
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
        # Keep everything (incl. the chosen master) until the mileage is confirmed
        # or a different mileage is typed — also accepted in this state.
        await state.set_state(NewVisitStates.confirming_mileage)
        builder = InlineKeyboardBuilder()
        builder.button(text="Подтвердить пробег", callback_data=MILEAGE_CONFIRM)
        await message.answer(f"{e.message}\nИли введите другой пробег.", reply_markup=builder.as_markup())
        return
    await state.clear()
    await send_visit_card(message, visit, [])


async def _continue_after_mileage(message: Message, state: FSMContext, api: ApiClient, user: dict) -> None:
    data = await state.get_data()
    if user["role"] == "admin" and "assigned_master_id" not in data:
        masters = await api.list_masters()
        if not masters:
            await state.clear()
            await message.answer("Сначала добавьте мастера через «Добавить сотрудника».")
            return
        builder = InlineKeyboardBuilder()
        for master in masters:
            builder.button(text=master["full_name"], callback_data=f"master_pick:{encode_id(master['id'])}")
        builder.adjust(1)
        await state.set_state(NewVisitStates.choosing_master)
        await message.answer("Выберите мастера:", reply_markup=builder.as_markup())
        return
    await _create_visit(message, state, api, user)


@router.message(NewVisitStates.waiting_for_mileage)
@router.message(NewVisitStates.confirming_mileage)
async def receive_mileage(message: Message, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    try:
        mileage = int(message.text)
    except (ValueError, TypeError):
        await message.answer("Введите число (пробег в км).")
        return
    await state.update_data(mileage=mileage, mileage_confirmed=False)
    await _continue_after_mileage(message, state, api, user)


@router.callback_query(NewVisitStates.confirming_mileage, F.data == MILEAGE_CONFIRM)
async def confirm_mileage_callback(callback: CallbackQuery, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    await state.update_data(mileage_confirmed=True)
    await _continue_after_mileage(callback.message, state, api, user)
    await callback.answer()


@router.callback_query(NewVisitStates.choosing_master, F.data.startswith("master_pick:"))
async def choose_master_callback(callback: CallbackQuery, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    await state.update_data(assigned_master_id=decode_id(callback.data.split(":", 1)[1]))
    await _create_visit(callback.message, state, api, user)
    await callback.answer()


@router.callback_query(F.data.startswith("new_visit_for:"))
async def new_visit_for_vehicle_callback(
    callback: CallbackQuery, state: FSMContext, api: ApiClient, user: dict, **kwargs
) -> None:
    if user["role"] not in ("admin", "master"):
        await callback.answer("Недостаточно прав")
        return
    vehicle_id = decode_id(callback.data.split(":", 1)[1])
    owner = await api.get_vehicle_owner(vehicle_id)
    if owner is None:
        await callback.message.answer("У машины нет владельца — заведите заезд через «Новый заезд».")
        await callback.answer()
        return
    await state.clear()
    await state.update_data(client_id=owner["id"], vehicle_id=vehicle_id)
    await state.set_state(NewVisitStates.waiting_for_mileage)
    await callback.message.answer(f"Новый заезд: {owner['full_name']}. Введите пробег на приёмке {CANCEL_HINT}:")
    await callback.answer()


@router.callback_query(F.data.startswith("visit_status:"))
async def change_status_callback(callback: CallbackQuery, state: FSMContext, api: ApiClient, **kwargs) -> None:
    _, visit_id, new_status = callback.data.split(":")
    if new_status == "cancelled":
        await state.clear()
        await state.update_data(visit_id=visit_id)
        await state.set_state(VisitCancelStates.waiting_for_reason)
        await callback.message.answer(f"Укажите причину отмены заезда {CANCEL_HINT}:")
        await callback.answer()
        return
    await api.change_visit_status(visit_id, new_status)
    await refresh_visit_card(callback.message, api, visit_id)
    await callback.answer()


@router.message(VisitCancelStates.waiting_for_reason)
async def receive_cancel_reason(message: Message, state: FSMContext, api: ApiClient, **kwargs) -> None:
    if not message.text:
        await message.answer(TEXT_REQUIRED)
        return
    visit_id = (await state.get_data())["visit_id"]
    await api.change_visit_status(visit_id, "cancelled", reason=message.text)
    await state.clear()
    await refresh_visit_card(message, api, visit_id)


@router.callback_query(F.data.startswith("approve_work:"))
async def approve_work_callback(callback: CallbackQuery, api: ApiClient, **kwargs) -> None:
    _, visit_b64, item_b64 = callback.data.split(":")
    visit_id = decode_id(visit_b64)
    await api.approve_work_item(visit_id, decode_id(item_b64))
    await refresh_visit_card(callback.message, api, visit_id)
    await callback.answer()
