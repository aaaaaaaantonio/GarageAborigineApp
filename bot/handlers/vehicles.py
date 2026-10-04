from datetime import date

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.api_client import ApiClient
from bot.states import NewVehicleStates, NewVisitStates
from bot.texts import CANCEL_HINT

router = Router()


@router.message(Command("new_vehicle"))
async def start_new_vehicle(message: Message, state: FSMContext, user: dict, **kwargs) -> None:
    if user["role"] == "mechanic":
        await message.answer("Недостаточно прав.")
        return
    await state.clear()
    await state.set_state(NewVehicleStates.waiting_for_vin)
    await message.answer(f"Введите VIN {CANCEL_HINT}:")


@router.message(NewVehicleStates.waiting_for_vin)
async def receive_vin(message: Message, state: FSMContext, **kwargs) -> None:
    await state.update_data(vin=message.text)
    await state.set_state(NewVehicleStates.waiting_for_plate)
    await message.answer("Введите гос.номер:")


@router.message(NewVehicleStates.waiting_for_plate)
async def receive_plate(message: Message, state: FSMContext, **kwargs) -> None:
    await state.update_data(plate_number=message.text)
    await state.set_state(NewVehicleStates.waiting_for_make_model)
    await message.answer("Введите марку и модель через пробел (например: Toyota Camry):")


@router.message(NewVehicleStates.waiting_for_make_model)
async def receive_make_model(message: Message, state: FSMContext, api: ApiClient, **kwargs) -> None:
    make, _, model = message.text.partition(" ")
    data = await state.get_data()
    vehicle = await api.create_vehicle(vin=data["vin"], plate_number=data["plate_number"], make=make, model=model)
    if data.get("return_flow") == "new_visit":
        await api.attach_owner(vehicle["id"], data["client_id"], date_from=date.today().isoformat())
        await state.update_data(vehicle_id=vehicle["id"])
        await state.set_state(NewVisitStates.waiting_for_mileage)
        await message.answer(f"Автомобиль создан: {vehicle['vin']}\nВведите пробег на приёмке:")
        return
    await state.clear()
    await message.answer(f"Автомобиль создан: {vehicle['vin']}")
