from datetime import date

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot import nav, wizard
from bot.api_client import ApiClient
from bot.states import NewVehicleStates, NewVisitStates
from bot.texts import TEXT_REQUIRED

router = Router()


@wizard.step(NewVehicleStates.waiting_for_vin)
async def vin_prompt(state: FSMContext, api: ApiClient, user: dict):
    if await wizard.name(state) == "new_visit":
        return "Автомобиль не найден. Введите VIN:", None
    return "Введите VIN:", None


@wizard.step(NewVehicleStates.waiting_for_plate)
async def plate_prompt(state: FSMContext, api: ApiClient, user: dict):
    return "Введите гос.номер:", None


@wizard.step(NewVehicleStates.waiting_for_make_model)
async def make_model_prompt(state: FSMContext, api: ApiClient, user: dict):
    return "Введите марку и модель через пробел (например: Toyota Camry):", None


@router.message(Command("new_vehicle"))
async def start_new_vehicle(message: Message, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    if user["role"] == "mechanic":
        await message.answer("Недостаточно прав.")
        return
    await wizard.start(message, state, api, user, "new_vehicle", NewVehicleStates.waiting_for_vin)


@router.message(NewVehicleStates.waiting_for_vin)
async def receive_vin(message: Message, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    if not message.text:
        await wizard.reprompt(message, state, api, user, TEXT_REQUIRED)
        return
    await state.update_data(vin=message.text)
    await wizard.goto(message, state, api, user, NewVehicleStates.waiting_for_plate)


@router.message(NewVehicleStates.waiting_for_plate)
async def receive_plate(message: Message, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    if not message.text:
        await wizard.reprompt(message, state, api, user, TEXT_REQUIRED)
        return
    await state.update_data(plate_number=message.text)
    await wizard.goto(message, state, api, user, NewVehicleStates.waiting_for_make_model)


@router.message(NewVehicleStates.waiting_for_make_model)
async def receive_make_model(message: Message, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    if not message.text:
        await wizard.reprompt(message, state, api, user, TEXT_REQUIRED)
        return
    make, _, model = message.text.partition(" ")
    data = await state.get_data()
    vehicle = await api.create_vehicle(vin=data["vin"], plate_number=data["plate_number"], make=make, model=model)
    if await wizard.name(state) == "new_visit":
        await api.attach_owner(vehicle["id"], data["client_id"], date_from=date.today().isoformat())
        await state.update_data(vehicle_id=str(vehicle["id"]), created_vehicle=vehicle["vin"])
        await wizard.goto(message, state, api, user, NewVisitStates.waiting_for_mileage, commit=True)
        return
    await wizard.finish(state)
    await nav.home(message, state, api, user, notice=f"Автомобиль создан: {vehicle['vin']}")
