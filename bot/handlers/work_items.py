from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.api_client import ApiClient
from bot.callback_ids import decode_id, encode_id
from bot.handlers.visits import refresh_visit_card
from bot.states import AddWorkItemStates
from bot.texts import CANCEL_HINT, TEXT_REQUIRED

router = Router()

_CATEGORY_LABELS = {
    "Диагностика": "diagnostics",
    "ТО": "maintenance",
    "Кузовные": "body",
    "Электрика": "electrical",
    "Ходовая": "chassis",
    "Прочее": "other",
}


@router.callback_query(F.data.startswith("add_work:"))
async def start_add_work_item(callback: CallbackQuery, state: FSMContext, **kwargs) -> None:
    _, visit_id = callback.data.split(":")
    await state.clear()
    await state.update_data(visit_id=visit_id)
    await state.set_state(AddWorkItemStates.waiting_for_name)
    await callback.message.answer(f"Введите название работы {CANCEL_HINT}:")
    await callback.answer()


@router.message(AddWorkItemStates.waiting_for_name)
async def receive_work_name(message: Message, state: FSMContext, api: ApiClient, **kwargs) -> None:
    if message.text is None:
        await message.answer(TEXT_REQUIRED)
        return
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


@router.callback_query(AddWorkItemStates.choosing_suggestion, F.data.startswith("catalog_pick:"))
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


@router.callback_query(AddWorkItemStates.choosing_category, F.data.startswith("category_pick:"))
async def choose_category_callback(callback: CallbackQuery, state: FSMContext, **kwargs) -> None:
    _, category = callback.data.split(":")
    await state.update_data(category=category)
    await state.set_state(AddWorkItemStates.waiting_for_hours_and_rate)
    await callback.message.answer("Введите нормо-часы и ставку через пробел (например: 1.5 800):")
    await callback.answer()


@router.message(AddWorkItemStates.waiting_for_hours_and_rate)
async def receive_hours_and_rate(message: Message, state: FSMContext, api: ApiClient, **kwargs) -> None:
    if message.text is None:
        await message.answer(TEXT_REQUIRED)
        return
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

    await state.update_data(norm_hours=norm_hours, hourly_rate=hourly_rate)
    mechanics = await api.list_mechanics()
    if not mechanics:
        await _create_work_item(message, state, api, assigned_mechanic_id=None)
        return

    builder = InlineKeyboardBuilder()
    for mechanic in mechanics:
        builder.button(text=mechanic["full_name"], callback_data=f"assign_mech:{encode_id(mechanic['id'])}")
    builder.button(text="Без исполнителя", callback_data="assign_mech:none")
    builder.adjust(1)
    await state.set_state(AddWorkItemStates.choosing_mechanic)
    await message.answer("Кому назначить работу?", reply_markup=builder.as_markup())


@router.callback_query(AddWorkItemStates.choosing_mechanic, F.data.startswith("assign_mech:"))
async def choose_mechanic_callback(callback: CallbackQuery, state: FSMContext, api: ApiClient, **kwargs) -> None:
    _, picked = callback.data.split(":")
    mechanic_id = None if picked == "none" else decode_id(picked)
    await _create_work_item(callback.message, state, api, assigned_mechanic_id=mechanic_id)
    await callback.answer()


async def _create_work_item(message: Message, state: FSMContext, api: ApiClient, assigned_mechanic_id: str | None) -> None:
    data = await state.get_data()
    await api.add_work_item(
        data["visit_id"],
        catalog_item_id=data.get("catalog_item_id"),
        free_text_name=None if data.get("catalog_item_id") else data["free_text_name"],
        category=data["category"],
        norm_hours=data["norm_hours"],
        hourly_rate=data["hourly_rate"],
        assigned_mechanic_id=assigned_mechanic_id,
    )
    await state.clear()
    await refresh_visit_card(message, api, data["visit_id"])
