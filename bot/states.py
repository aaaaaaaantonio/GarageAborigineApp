from aiogram.fsm.state import State, StatesGroup


class NewClientStates(StatesGroup):
    waiting_for_phone = State()
    waiting_for_full_name = State()


class NewVehicleStates(StatesGroup):
    waiting_for_vin = State()
    waiting_for_plate = State()
    waiting_for_make_model = State()


class NewVisitStates(StatesGroup):
    choosing_client = State()
    choosing_vehicle = State()
    waiting_for_mileage = State()
    choosing_master = State()


class AddWorkItemStates(StatesGroup):
    waiting_for_name = State()
    choosing_suggestion = State()
    waiting_for_hours_and_rate = State()


class AddPartItemStates(StatesGroup):
    choosing_work_item = State()
    waiting_for_name = State()
    waiting_for_quantity_and_price = State()


class NewStaffStates(StatesGroup):
    choosing_role = State()
    waiting_for_full_name = State()
    waiting_for_telegram_id = State()
