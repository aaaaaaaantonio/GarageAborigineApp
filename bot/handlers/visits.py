import base64
import uuid as uuid_lib

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.api_client import ApiClient
from bot.states import NewClientStates, NewVehicleStates, NewVisitStates


def _encode_id(raw_id: str) -> str:
    return base64.urlsafe_b64encode(uuid_lib.UUID(str(raw_id)).bytes).rstrip(b"=").decode()


def _decode_id(encoded: str) -> str:
    padded = encoded + "=" * (-len(encoded) % 4)
    return str(uuid_lib.UUID(bytes=base64.urlsafe_b64decode(padded)))


router = Router()

_NEXT_STATUS_BY_CURRENT = {
    "received": ["diagnostics", "cancelled"],
    "diagnostics": ["approval", "cancelled"],
    "approval": ["in_progress", "cancelled"],
    "in_progress": ["waiting_parts", "ready", "cancelled"],
    "waiting_parts": ["in_progress", "cancelled"],
    "ready": ["issued"],
}


async def send_visit_card(message: Message, visit: dict, work_items: list[dict]) -> None:
    builder = InlineKeyboardBuilder()
    for status in _NEXT_STATUS_BY_CURRENT.get(visit["status"], []):
        builder.button(text=status, callback_data=f"visit_status:{visit['id']}:{status}")
    for index, item in enumerate(work_items, start=1):
        if item.get("approved_by_client") is False:
            name = item.get("free_text_name") or f"работа №{index}"
            builder.button(
                text=f"✅ {name}",
                callback_data=f"approve_work:{_encode_id(visit['id'])}:{_encode_id(item['id'])}",
            )
    builder.adjust(1)
    await message.answer(
        f"Заезд {visit['id']}\nСтатус: {visit['status']}\nСумма: {visit.get('total_amount', '—')}",
        reply_markup=builder.as_markup(),
    )


@router.message(F.text == "Новый заезд")
async def start_new_visit(message: Message, state: FSMContext, **kwargs) -> None:
    await state.clear()
    await state.set_state(NewVisitStates.waiting_for_client_query)
    await message.answer("Введите телефон или ФИО клиента:")


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


@router.callback_query(lambda c: c.data.startswith("client_pick:"))
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


@router.callback_query(lambda c: c.data.startswith("vehicle_pick:"))
async def choose_vehicle_callback(callback: CallbackQuery, state: FSMContext, **kwargs) -> None:
    _, vehicle_id = callback.data.split(":")
    await state.update_data(vehicle_id=vehicle_id)
    await state.set_state(NewVisitStates.waiting_for_mileage)
    await callback.message.answer("Введите пробег на приёмке:")
    await callback.answer()


@router.message(NewVisitStates.waiting_for_mileage)
async def receive_mileage(message: Message, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    try:
        mileage = int(message.text)
    except (ValueError, TypeError):
        await message.answer("Введите число (пробег в км).")
        return
    data = await state.get_data()
    visit = await api.create_visit(
        client_id=data["client_id"],
        vehicle_id=data["vehicle_id"],
        assigned_master_id=user["id"],
        mileage_at_intake=mileage,
    )
    await state.clear()
    await send_visit_card(message, visit, [])


@router.callback_query(lambda c: c.data.startswith("visit_status:"))
async def change_status_callback(callback: CallbackQuery, api: ApiClient, **kwargs) -> None:
    _, visit_id, new_status = callback.data.split(":")
    visit = await api.change_visit_status(visit_id, new_status)
    await callback.message.answer(f"Статус обновлён: {visit['status']}")
    await callback.answer()


@router.callback_query(lambda c: c.data.startswith("approve_work:"))
async def approve_work_callback(callback: CallbackQuery, api: ApiClient, **kwargs) -> None:
    _, visit_b64, item_b64 = callback.data.split(":")
    visit_id = _decode_id(visit_b64)
    item_id = _decode_id(item_b64)
    await api.approve_work_item(visit_id, item_id)
    visit = await api.get_visit(visit_id)
    items = await api.list_work_items(visit_id)
    await send_visit_card(callback.message, visit, items)
    await callback.answer()
