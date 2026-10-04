from unittest.mock import AsyncMock

from bot.handlers.consent import receive_paper_full_name, receive_paper_phone, start_paper_consent
from bot.states import PaperConsentStates
from tests.bot.helpers import MASTER, MECHANIC, fsm_context, make_callback, make_message, on_screens, shown


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


async def test_phone_then_name_registers_and_shows_menu():
    state = fsm_context()
    await on_screens(state)
    await state.set_state(PaperConsentStates.waiting_for_phone)
    await state.update_data(wiz_name="paper_consent", wiz_steps=[])
    api = AsyncMock()

    message = make_message("79990000000")
    await receive_paper_phone(message, state, api=api, user=MASTER)
    assert shown(message)[0] == "Введите ФИО клиента:"

    message = make_message("Иван Иванов")
    await receive_paper_full_name(message, state, api=api, user=MASTER)

    api.register_paper_consent.assert_awaited_once_with(full_name="Иван Иванов", phone="79990000000")
    assert shown(message)[0] == "Клиент зарегистрирован (бумажное согласие): Иван Иванов\n\nГлавное меню"
