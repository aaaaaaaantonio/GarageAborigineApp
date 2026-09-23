from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.api_client import ApiClient
from bot.states import NewVisitStates

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
    for item in work_items:
        if item.get("approved_by_client") is False:
            name = item.get("free_text_name") or "работа"
            builder.button(text=f"✅ {name}", callback_data=f"approve_work:{visit['id']}:{item['id']}")
    builder.adjust(1)
    await message.answer(
        f"Заезд {visit['id']}\nСтатус: {visit['status']}\nСумма: {visit.get('total_amount', '—')}",
        reply_markup=builder.as_markup(),
    )


@router.message(NewVisitStates.waiting_for_mileage)
async def receive_mileage(message: Message, state: FSMContext, api: ApiClient, **kwargs) -> None:
    data = await state.get_data()
    visit = await api.create_visit(
        client_id=data["client_id"],
        vehicle_id=data["vehicle_id"],
        assigned_master_id=data["master_id"],
        mileage_at_intake=int(message.text),
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
    _, visit_id, item_id = callback.data.split(":")
    await api.approve_work_item(visit_id, item_id)
    visit = await api.get_visit(visit_id)
    items = await api.list_work_items(visit_id)
    await send_visit_card(callback.message, visit, items)
    await callback.answer()
