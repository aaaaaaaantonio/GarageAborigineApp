from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.api_client import ApiClient
from bot.callback_ids import decode_id
from bot.handlers.visits import refresh_visit_card
from bot.states import AddPartItemStates
from bot.texts import CANCEL_HINT, TEXT_REQUIRED

router = Router()


@router.callback_query(F.data.startswith("add_part:"))
async def start_add_part_item(callback: CallbackQuery, state: FSMContext, **kwargs) -> None:
    _, visit_b64, work_item_b64 = callback.data.split(":")
    visit_id = decode_id(visit_b64)
    work_item_id = decode_id(work_item_b64)
    await state.clear()
    await state.update_data(visit_id=visit_id, work_item_id=work_item_id)
    await state.set_state(AddPartItemStates.waiting_for_name)
    await callback.message.answer(f"Введите название запчасти {CANCEL_HINT}:")
    await callback.answer()


@router.message(AddPartItemStates.waiting_for_name)
async def receive_part_name(message: Message, state: FSMContext, **kwargs) -> None:
    if message.text is None:
        await message.answer(TEXT_REQUIRED)
        return
    await state.update_data(name=message.text)
    await state.set_state(AddPartItemStates.waiting_for_quantity_and_price)
    await message.answer("Введите количество и цену через пробел (например: 2 350):")


@router.message(AddPartItemStates.waiting_for_quantity_and_price)
async def receive_quantity_and_price(message: Message, state: FSMContext, api: ApiClient, **kwargs) -> None:
    if message.text is None:
        await message.answer(TEXT_REQUIRED)
        return
    try:
        quantity_str, price_str = message.text.split()
        quantity = int(quantity_str)
        unit_price = float(price_str)
    except (ValueError, TypeError):
        await state.set_state(AddPartItemStates.waiting_for_quantity_and_price)
        await message.answer("Введите количество и цену через пробел, например: 2 350.")
        return
    data = await state.get_data()
    await api.add_part_item(
        visit_id=data["visit_id"],
        work_item_id=data["work_item_id"],
        name=data["name"],
        quantity=quantity,
        unit_price=unit_price,
    )
    await state.clear()
    await refresh_visit_card(message, api, data["visit_id"])
