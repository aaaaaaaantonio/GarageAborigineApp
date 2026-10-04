from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot import actions, nav, wizard
from bot.api_client import ApiClient
from bot.states import AddPartItemStates
from bot.texts import TEXT_REQUIRED

router = Router()


@wizard.step(AddPartItemStates.waiting_for_name)
async def part_name_prompt(state: FSMContext, api: ApiClient, user: dict):
    return "Введите название запчасти:", None


@wizard.step(AddPartItemStates.waiting_for_quantity_and_price)
async def quantity_and_price_prompt(state: FSMContext, api: ApiClient, user: dict):
    return "Введите количество и цену через пробел (например: 2 350):", None


@router.callback_query(F.data == actions.ADD_PART)
async def start_add_part_item(callback: CallbackQuery, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    args = await nav.top_args(callback, state, "work")
    if args is None:
        return
    await wizard.start(
        callback, state, api, user, "add_part", AddPartItemStates.waiting_for_name,
        visit_id=args["visit_id"], work_item_id=args["item_id"],
    )


@router.message(AddPartItemStates.waiting_for_name)
async def receive_part_name(message: Message, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    if message.text is None:
        await wizard.reprompt(message, state, api, user, TEXT_REQUIRED)
        return
    await state.update_data(name=message.text)
    await wizard.goto(message, state, api, user, AddPartItemStates.waiting_for_quantity_and_price)


@router.message(AddPartItemStates.waiting_for_quantity_and_price)
async def receive_quantity_and_price(message: Message, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    if message.text is None:
        await wizard.reprompt(message, state, api, user, TEXT_REQUIRED)
        return
    try:
        quantity_str, price_str = message.text.split()
        quantity = int(quantity_str)
        unit_price = float(price_str)
    except (ValueError, TypeError):
        await wizard.reprompt(message, state, api, user, "Введите количество и цену через пробел, например: 2 350.")
        return
    data = await state.get_data()
    await api.add_part_item(
        visit_id=data["visit_id"], work_item_id=data["work_item_id"], name=data["name"],
        quantity=quantity, unit_price=unit_price,
    )
    await wizard.finish(state)
    await nav.refresh(message, state, api, user)  # back on the work screen
