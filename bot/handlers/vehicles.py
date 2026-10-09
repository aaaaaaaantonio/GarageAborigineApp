from datetime import date

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot import actions, nav, wizard
from bot.api_client import ApiClient, ApiConflict
from bot.handlers.navigation import STAFF_ROLES
from bot.states import NewVehicleStates, NewVisitStates
from bot.texts import TEXT_REQUIRED
from bot.validators import VIN_FORMAT_ERROR, is_valid_vin, normalize_plate, normalize_vin

router = Router()


@wizard.step(NewVehicleStates.waiting_for_vin)
async def vin_prompt(state: FSMContext, api: ApiClient, user: dict):
    return "Введите VIN или номер кузова:", None


@wizard.step(NewVehicleStates.waiting_for_plate)
async def plate_prompt(state: FSMContext, api: ApiClient, user: dict):
    return "Введите госномер:", None


@wizard.step(NewVehicleStates.waiting_for_make_model)
async def make_model_prompt(state: FSMContext, api: ApiClient, user: dict):
    return "Введите марку и модель через пробел (например: Toyota Camry):", None


@router.message(Command("new_vehicle"))
async def start_new_vehicle(message: Message, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    if user["role"] == "mechanic":
        await message.answer("Недостаточно прав.")
        return
    await wizard.start(message, state, api, user, "new_vehicle", NewVehicleStates.waiting_for_vin)


@router.callback_query(F.data == actions.ADD_VEHICLE)
async def add_vehicle_callback(callback: CallbackQuery, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    """"➕ Добавить автомобиль" on the client card: the client becomes the owner."""
    if user["role"] not in STAFF_ROLES:
        await callback.answer("Недостаточно прав")
        return
    args = await nav.top_args(callback, state, "client")
    if args is None:
        return
    await wizard.start(callback, state, api, user, "add_vehicle", NewVehicleStates.waiting_for_vin, client_id=args["client_id"])


@router.message(NewVehicleStates.waiting_for_vin)
async def receive_vin(message: Message, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    if not message.text:
        await wizard.reprompt(message, state, api, user, TEXT_REQUIRED)
        return
    if not is_valid_vin(message.text):
        await wizard.reprompt(message, state, api, user, VIN_FORMAT_ERROR)
        return
    await state.update_data(vin=normalize_vin(message.text))
    # The plate may already be known from the new-visit search query.
    plate_known = bool((await state.get_data()).get("plate_number"))
    target = NewVehicleStates.waiting_for_make_model if plate_known else NewVehicleStates.waiting_for_plate
    await wizard.goto(message, state, api, user, target)


@router.message(NewVehicleStates.waiting_for_plate)
async def receive_plate(message: Message, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    if not message.text:
        await wizard.reprompt(message, state, api, user, TEXT_REQUIRED)
        return
    await state.update_data(plate_number=normalize_plate(message.text))
    await wizard.goto(message, state, api, user, NewVehicleStates.waiting_for_make_model)


@router.message(NewVehicleStates.waiting_for_make_model)
async def receive_make_model(message: Message, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    if not message.text:
        await wizard.reprompt(message, state, api, user, TEXT_REQUIRED)
        return
    make, _, model = message.text.partition(" ")
    data = await state.get_data()
    try:
        vehicle = await api.create_vehicle(vin=data["vin"], plate_number=data["plate_number"], make=make, model=model)
    except ApiConflict as e:
        await wizard.retry(message, state, api, user, NewVehicleStates.waiting_for_vin, e.message)
        return
    wiz_name = await wizard.name(state)
    if wiz_name in ("new_visit", "add_vehicle"):
        await api.attach_owner(vehicle["id"], data["client_id"], date_from=date.today().isoformat())
    if wiz_name == "new_visit":
        await state.update_data(vehicle_id=str(vehicle["id"]), created_vehicle=vehicle["vin"])
        await wizard.goto(message, state, api, user, NewVisitStates.waiting_for_mileage, commit=True)
        return
    await wizard.finish(state)
    if wiz_name == "add_vehicle":
        await nav.refresh(message, state, api, user, notice=f"Автомобиль добавлен: {vehicle['vin']}")
        return
    await nav.home(message, state, api, user, notice=f"Автомобиль создан: {vehicle['vin']}")
