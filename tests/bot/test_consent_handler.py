from unittest.mock import AsyncMock

from bot.api_client import ApiConflict
from bot.handlers.consent import receive_paper_full_name, receive_paper_phone, start_paper_consent
from bot.states import PaperConsentStates
from bot.validators import PHONE_FORMAT_ERROR
from tests.bot.helpers import MASTER, MECHANIC, buttons, fsm_context, make_callback, make_message, on_screens, shown

C1 = "11111111-1111-1111-1111-111111111111"


async def test_start_asks_for_phone():
    state = fsm_context()
    await on_screens(state)
    callback = make_callback("wiz:paper_consent")

    await start_paper_consent(callback, state, api=AsyncMock(), user=MASTER)

    assert await state.get_state() == PaperConsentStates.waiting_for_phone.state
    assert shown(callback)[0] == "Введите телефон клиента:"


async def test_start_refused_for_mechanic():
    callback = make_callback("wiz:paper_consent")

    await start_paper_consent(callback, fsm_context(), api=AsyncMock(), user=MECHANIC)

    callback.answer.assert_awaited_once_with("Недостаточно прав")


async def test_phone_then_name_registers_and_opens_client_card():
    state = fsm_context()
    await on_screens(state)
    await state.set_state(PaperConsentStates.waiting_for_phone)
    await state.update_data(wiz_name="paper_consent", wiz_steps=[])
    api = AsyncMock()
    api.register_paper_consent.return_value = {"client_id": C1}
    api.get_client.return_value = {"id": C1, "full_name": "Иван Иванов", "phone_display": "+7 999 000-00-00"}
    api.list_client_vehicles.return_value = []

    message = make_message("79990000000")
    await receive_paper_phone(message, state, api=api, user=MASTER)
    assert shown(message)[0] == "Введите ФИО клиента:"

    message = make_message("Иван Иванов")
    await receive_paper_full_name(message, state, api=api, user=MASTER)

    api.register_paper_consent.assert_awaited_once_with(full_name="Иван Иванов", phone="79990000000")
    text, markup = shown(message)
    assert text == "Клиент зарегистрирован (бумажное согласие): Иван Иванов\n\n👤 Иван Иванов\n+7 999 000-00-00"
    assert ("➕ Добавить автомобиль", "act:add_vehicle") in buttons(markup)
    assert (await state.get_data())["nav_stack"][-1] == ["client", {"client_id": C1}]


async def test_invalid_phone_is_asked_again():
    state = fsm_context()
    await on_screens(state)
    await state.set_state(PaperConsentStates.waiting_for_phone)
    await state.update_data(wiz_name="paper_consent", wiz_steps=[])
    message = make_message("12345")

    await receive_paper_phone(message, state, api=AsyncMock(), user=MASTER)

    assert await state.get_state() == PaperConsentStates.waiting_for_phone.state
    assert shown(message)[0] == f"{PHONE_FORMAT_ERROR}\n\nВведите телефон клиента:"


async def test_taken_phone_returns_to_phone_step():
    state = fsm_context()
    await on_screens(state)
    await state.set_state(PaperConsentStates.waiting_for_full_name)
    await state.update_data(wiz_name="paper_consent", wiz_steps=[], phone="79990000000")
    api = AsyncMock()
    api.register_paper_consent.side_effect = ApiConflict("Клиент с таким телефоном уже есть")
    message = make_message("Иван Иванов")

    await receive_paper_full_name(message, state, api=api, user=MASTER)

    assert await state.get_state() == PaperConsentStates.waiting_for_phone.state
    assert shown(message)[0] == "Клиент с таким телефоном уже есть\n\nВведите телефон клиента:"
