from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot import actions, nav, wizard
from bot.api_client import ApiClient, ApiForbidden, ApiNotFound
from bot.callback_ids import decode_id, encode_id
from bot.handlers.navigation import STAFF_ROLES
from bot.states import AddWorkItemStates
from bot.texts import TEXT_REQUIRED
from bot.work_item_status import NEXT_WORK_ITEM_STATUSES, work_item_icon, work_item_status_label

router = Router()

_CATEGORY_LABELS = {
    "Диагностика": "diagnostics",
    "ТО": "maintenance",
    "Кузовные": "body",
    "Электрика": "electrical",
    "Ходовая": "chassis",
    "Прочее": "other",
}


def _find(items: list[dict], item_id: str) -> dict | None:
    return next((i for i in items if str(i["id"]) == str(item_id)), None)


def _title(source: dict) -> str:
    return " · ".join(p for p in (source.get("plate_number"), source.get("make_model")) if p)


@nav.screen("work", params=("visit_id", "item_id"))
async def render_work(api: ApiClient, user: dict, args: dict) -> nav.Rendered:
    staff = user["role"] in STAFF_ROLES
    if staff:
        visit = await api.get_visit(args["visit_id"])
        item = _find(await api.list_work_items(args["visit_id"]), args["item_id"])
        if item is None:
            raise ApiNotFound("Работа не найдена.")
        title = _title(visit)
    else:
        # Mechanics can't read the visit; their own list carries the car.
        item = _find(await api.list_my_work_items(), args["item_id"])
        if item is None:
            raise ApiNotFound("Работа больше не назначена вам.")
        title = _title(item)
    lines = [title] if title else []
    lines += [f"{work_item_icon(item['status'])} {item['name']}", f"Статус: {work_item_status_label(item['status'])}"]
    builder = InlineKeyboardBuilder()
    if staff:
        lines.append(f"Исполнитель: {item.get('assigned_mechanic_name') or 'без исполнителя'}")
        lines.append(f"Согласовано клиентом: {'да' if item['approved_by_client'] else 'нет'}")
        if not item["approved_by_client"]:
            builder.button(text="✅ Согласовано клиентом", callback_data=actions.APPROVE)
    for status in NEXT_WORK_ITEM_STATUSES.get(item["status"], []):
        builder.button(text=f"→ {work_item_status_label(status)}", callback_data=f"{actions.WORK_STATUS}:{status}")
    if staff:
        builder.button(text="🔩 Добавить запчасть", callback_data=actions.ADD_PART)
        builder.button(text="👤 Сменить исполнителя", callback_data=nav.go_data("reassign", args["visit_id"], args["item_id"]))
    builder.adjust(1)
    return "\n".join(lines), builder.as_markup()


@router.callback_query(F.data.startswith(f"{actions.WORK_STATUS}:"))
async def work_status_callback(callback: CallbackQuery, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    args = await nav.top_args(callback, state, "work")
    if args is None:
        return
    await api.update_work_item_status(args["visit_id"], args["item_id"], callback.data.rsplit(":", 1)[1])
    await nav.refresh(callback, state, api, user)


@router.callback_query(F.data == actions.APPROVE)
async def approve_callback(callback: CallbackQuery, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    if user["role"] not in STAFF_ROLES:
        await callback.answer("Недостаточно прав")
        return
    args = await nav.top_args(callback, state, "work")
    if args is None:
        return
    await api.approve_work_item(args["visit_id"], args["item_id"])
    await nav.refresh(callback, state, api, user)


@nav.screen("reassign", params=("visit_id", "item_id"))
async def render_reassign(api: ApiClient, user: dict, args: dict) -> nav.Rendered:
    if user["role"] not in STAFF_ROLES:
        raise ApiForbidden("Недостаточно прав")
    builder = InlineKeyboardBuilder()
    for mechanic in await api.list_mechanics():
        builder.button(text=mechanic["full_name"], callback_data=f"{actions.REASSIGN}:{encode_id(mechanic['id'])}")
    builder.button(text="Без исполнителя", callback_data=f"{actions.REASSIGN}:none")
    builder.adjust(1)
    return "Кому передать работу?", builder.as_markup()


@router.callback_query(F.data.startswith(f"{actions.REASSIGN}:"))
async def reassign_callback(callback: CallbackQuery, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    if user["role"] not in STAFF_ROLES:
        await callback.answer("Недостаточно прав")
        return
    args = await nav.top_args(callback, state, "reassign")
    if args is None:
        return
    picked = callback.data.rsplit(":", 1)[1]
    await api.assign_work_item_mechanic(args["visit_id"], args["item_id"], None if picked == "none" else decode_id(picked))
    await nav.pop(callback, state, api, user)


# --- Add-work wizard (started from the visit card).


@wizard.step(AddWorkItemStates.waiting_for_name)
async def work_name_prompt(state: FSMContext, api: ApiClient, user: dict):
    return "Введите название работы:", None


@wizard.step(AddWorkItemStates.choosing_suggestion)
async def suggestion_prompt(state: FSMContext, api: ApiClient, user: dict):
    builder = InlineKeyboardBuilder()
    for item in (await state.get_data())["suggestions"].values():
        builder.button(text=item["name"], callback_data=f"catalog_pick:{item['id']}")
    builder.button(text="Своя формулировка", callback_data="catalog_pick:none")
    builder.adjust(1)
    return "Выберите работу из справочника или укажите свою:", builder.as_markup()


@wizard.step(AddWorkItemStates.choosing_category)
async def category_prompt(state: FSMContext, api: ApiClient, user: dict):
    builder = InlineKeyboardBuilder()
    for label, value in _CATEGORY_LABELS.items():
        builder.button(text=label, callback_data=f"category_pick:{value}")
    builder.adjust(1)
    return "Выберите категорию работы:", builder.as_markup()


@wizard.step(AddWorkItemStates.waiting_for_hours_and_rate)
async def hours_and_rate_prompt(state: FSMContext, api: ApiClient, user: dict):
    if (await state.get_data()).get("catalog_item_id"):
        return "Введите часовую ставку:", None
    return "Введите нормо-часы и ставку через пробел (например: 1.5 800):", None


@wizard.step(AddWorkItemStates.choosing_mechanic)
async def mechanic_prompt(state: FSMContext, api: ApiClient, user: dict):
    builder = InlineKeyboardBuilder()
    for value, name in (await state.get_data())["mechanic_choices"]:
        builder.button(text=name, callback_data=f"assign_mech:{value}")
    builder.button(text="Без исполнителя", callback_data="assign_mech:none")
    builder.adjust(1)
    return "Кому назначить работу?", builder.as_markup()


@router.callback_query(F.data == actions.ADD_WORK)
async def start_add_work_item(callback: CallbackQuery, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    args = await nav.top_args(callback, state, "visit")
    if args is None:
        return
    await wizard.start(callback, state, api, user, "add_work", AddWorkItemStates.waiting_for_name, visit_id=args["visit_id"])


@router.message(AddWorkItemStates.waiting_for_name)
async def receive_work_name(message: Message, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    if message.text is None:
        await wizard.reprompt(message, state, api, user, TEXT_REQUIRED)
        return
    suggestions = await api.suggest_catalog(message.text)
    await state.update_data(free_text_name=message.text, suggestions={str(item["id"]): item for item in suggestions})
    await wizard.goto(message, state, api, user, AddWorkItemStates.choosing_suggestion)


@router.callback_query(AddWorkItemStates.choosing_suggestion, F.data.startswith("catalog_pick:"))
async def choose_catalog_callback(callback: CallbackQuery, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    picked = callback.data.split(":", 1)[1]
    if picked == "none":
        # Forget an earlier catalog pick (the user may have come back here).
        await state.update_data(catalog_item_id=None, norm_hours=None)
        await wizard.goto(callback, state, api, user, AddWorkItemStates.choosing_category)
        return
    suggestion = (await state.get_data())["suggestions"][picked]
    await state.update_data(catalog_item_id=picked, category=suggestion["category"], norm_hours=suggestion["default_norm_hours"])
    await wizard.goto(callback, state, api, user, AddWorkItemStates.waiting_for_hours_and_rate)


@router.callback_query(AddWorkItemStates.choosing_category, F.data.startswith("category_pick:"))
async def choose_category_callback(callback: CallbackQuery, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    await state.update_data(category=callback.data.split(":", 1)[1])
    await wizard.goto(callback, state, api, user, AddWorkItemStates.waiting_for_hours_and_rate)


@router.message(AddWorkItemStates.waiting_for_hours_and_rate)
async def receive_hours_and_rate(message: Message, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    if message.text is None:
        await wizard.reprompt(message, state, api, user, TEXT_REQUIRED)
        return
    from_catalog = bool((await state.get_data()).get("catalog_item_id"))
    try:
        if from_catalog:
            norm_hours = (await state.get_data())["norm_hours"]
            hourly_rate = float(message.text)
        else:
            norm_hours_text, hourly_rate_text = message.text.split()
            norm_hours, hourly_rate = float(norm_hours_text), float(hourly_rate_text)
    except (ValueError, TypeError):
        error = "Введите число (часовую ставку)." if from_catalog else "Введите нормо-часы и ставку через пробел, например: 1.5 800."
        await wizard.reprompt(message, state, api, user, error)
        return
    await state.update_data(norm_hours=norm_hours, hourly_rate=hourly_rate)
    mechanics = await api.list_mechanics()
    if not mechanics:
        await _create_work_item(message, state, api, user, assigned_mechanic_id=None)
        return
    await state.update_data(mechanic_choices=[[encode_id(m["id"]), m["full_name"]] for m in mechanics])
    await wizard.goto(message, state, api, user, AddWorkItemStates.choosing_mechanic)


@router.callback_query(AddWorkItemStates.choosing_mechanic, F.data.startswith("assign_mech:"))
async def choose_mechanic_callback(callback: CallbackQuery, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    picked = callback.data.split(":", 1)[1]
    await _create_work_item(callback, state, api, user, assigned_mechanic_id=None if picked == "none" else decode_id(picked))


async def _create_work_item(event: nav.Event, state: FSMContext, api: ApiClient, user: dict, assigned_mechanic_id: str | None) -> None:
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
    await wizard.finish(state)
    await nav.refresh(event, state, api, user)  # the visit card, now with the new item
