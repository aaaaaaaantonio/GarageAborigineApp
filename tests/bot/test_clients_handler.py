from unittest.mock import AsyncMock

from bot import wizard
from bot.handlers.clients import receive_full_name, receive_phone, start_new_client
from bot.states import NewClientStates, NewVisitStates
from tests.bot.helpers import MASTER, MECHANIC, fsm_context, make_callback, make_message, on_screens, shown

C1 = "11111111-1111-1111-1111-111111111111"


async def test_new_client_command_asks_for_phone():
    state = fsm_context()
    message = make_message("/new_client")

    await start_new_client(message, state, api=AsyncMock(), user=MASTER)

    assert await state.get_state() == NewClientStates.waiting_for_phone.state
    assert shown(message)[0] == "Введите телефон клиента:"


async def test_new_client_refused_for_mechanic():
    state = fsm_context()
    message = make_message("/new_client")

    await start_new_client(message, state, api=AsyncMock(), user=MECHANIC)

    assert await state.get_state() is None
    message.answer.assert_awaited_once_with("Недостаточно прав.")


async def test_standalone_client_is_created_and_menu_shown():
    state = fsm_context()
    await on_screens(state)
    await state.set_state(NewClientStates.waiting_for_full_name)
    await state.update_data(wiz_name="new_client", wiz_steps=[], phone="79990000000")
    api = AsyncMock()
    api.create_client.return_value = {"id": C1, "full_name": "Иван Иванов"}
    message = make_message("Иван Иванов")

    await receive_full_name(message, state, api=api, user=MASTER)

    api.create_client.assert_awaited_once_with(full_name="Иван Иванов", phone="79990000000")
    assert await state.get_state() is None
    assert shown(message)[0] == "Клиент создан: Иван Иванов\n\nГлавное меню"


async def test_client_in_new_visit_continues_and_back_cannot_recreate_it():
    state = fsm_context()
    await on_screens(state)
    await state.set_state(NewClientStates.waiting_for_full_name)
    await state.update_data(wiz_name="new_visit", wiz_steps=["NewVisitStates:waiting_for_client_query"], phone="7999")
    api = AsyncMock()
    api.create_client.return_value = {"id": C1, "full_name": "Иван Иванов"}
    message = make_message("Иван Иванов")

    await receive_full_name(message, state, api=api, user=MASTER)

    assert (await state.get_data())["client_id"] == C1
    assert await state.get_state() == NewVisitStates.waiting_for_vehicle_query.state
    assert shown(message)[0] == "Клиент создан: Иван Иванов\nВведите VIN или гос.номер авто:"

    await wizard.back_callback(make_callback("wiz_back"), state, api=api, user=MASTER)

    assert await state.get_state() is None  # history dropped: back = cancel
    api.create_client.assert_awaited_once()


async def test_phone_must_be_text():
    state = fsm_context()
    await state.set_state(NewClientStates.waiting_for_phone)
    await state.update_data(wiz_name="new_client", wiz_steps=[])
    message = make_message(None)

    await receive_phone(message, state, api=AsyncMock(), user=MASTER)

    assert shown(message)[0] == "Пожалуйста, отправьте ответ текстом.\n\nВведите телефон клиента:"
