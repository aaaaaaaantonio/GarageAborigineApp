from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.api_client import ApiClient
from bot.handlers.visits import send_visit_card
from bot.states import AddWorkItemStates

router = Router()

_CATEGORY_LABELS = {
    "Диагностика": "diagnostics",
    "ТО": "maintenance",
    "Кузовные": "body",
    "Электрика": "electrical",
    "Ходовая": "chassis",
    "Прочее": "other",
}


@router.message(AddWorkItemStates.waiting_for_name)
async def receive_work_name(message: Message, state: FSMContext, api: ApiClient, **kwargs) -> None:
    suggestions = await api.suggest_catalog(message.text)
    await state.update_data(
        free_text_name=message.text,
        suggestions={item["id"]: item for item in suggestions},
    )
    builder = InlineKeyboardBuilder()
    for item in suggestions:
        builder.button(text=item["name"], callback_data=f"catalog_pick:{item['id']}")
    builder.button(text="Своя формулировка", callback_data="catalog_pick:none")
    builder.adjust(1)
    await state.set_state(AddWorkItemStates.choosing_suggestion)
    await message.answer("Выберите работу из справочника или укажите свою:", reply_markup=builder.as_markup())


@router.callback_query(lambda c: c.data.startswith("catalog_pick:"))
async def choose_catalog_callback(callback: CallbackQuery, state: FSMContext, **kwargs) -> None:
    _, picked = callback.data.split(":")
    if picked == "none":
        builder = InlineKeyboardBuilder()
        for label, value in _CATEGORY_LABELS.items():
            builder.button(text=label, callback_data=f"category_pick:{value}")
        builder.adjust(1)
        await state.set_state(AddWorkItemStates.choosing_category)
        await callback.message.answer("Выберите категорию работы:", reply_markup=builder.as_markup())
        await callback.answer()
        return
    data = await state.get_data()
    suggestion = data["suggestions"][picked]
    await state.update_data(
        catalog_item_id=picked,
        category=suggestion["category"],
        norm_hours=suggestion["default_norm_hours"],
    )
    await state.set_state(AddWorkItemStates.waiting_for_hours_and_rate)
    await callback.message.answer("Введите часовую ставку:")
    await callback.answer()


@router.callback_query(lambda c: c.data.startswith("category_pick:"))
async def choose_category_callback(callback: CallbackQuery, state: FSMContext, **kwargs) -> None:
    _, category = callback.data.split(":")
    await state.update_data(category=category)
    await state.set_state(AddWorkItemStates.waiting_for_hours_and_rate)
    await callback.message.answer("Введите нормо-часы и ставку через пробел (например: 1.5 800):")
    await callback.answer()


@router.message(AddWorkItemStates.waiting_for_hours_and_rate)
async def receive_hours_and_rate(message: Message, state: FSMContext, api: ApiClient, **kwargs) -> None:
    data = await state.get_data()
    try:
        if "norm_hours" in data:
            norm_hours = data["norm_hours"]
            hourly_rate = float(message.text)
        else:
            norm_hours_text, hourly_rate_text = message.text.split()
            norm_hours = float(norm_hours_text)
            hourly_rate = float(hourly_rate_text)
    except (ValueError, TypeError):
        if "norm_hours" in data:
            await message.answer("Введите число (часовую ставку).")
        else:
            await message.answer("Введите нормо-часы и ставку через пробел, например: 1.5 800.")
        return

    await api.add_work_item(
        data["visit_id"],
        catalog_item_id=data.get("catalog_item_id"),
        free_text_name=None if data.get("catalog_item_id") else data["free_text_name"],
        category=data["category"],
        norm_hours=norm_hours,
        hourly_rate=hourly_rate,
    )
    visit_id = data["visit_id"]
    await state.clear()
    visit = await api.get_visit(visit_id)
    items = await api.list_work_items(visit_id)
    await send_visit_card(message, visit, items)
