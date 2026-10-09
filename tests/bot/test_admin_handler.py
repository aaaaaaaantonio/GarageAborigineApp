from unittest.mock import AsyncMock

from bot.handlers.admin import choose_staff_role, receive_staff_full_name, receive_telegram_id, start_new_staff
from bot.states import NewStaffStates
from tests.bot.helpers import ADMIN, MASTER, buttons, fsm_context, make_callback, make_message, on_screens, shown


async def test_start_offers_roles_in_russian():
    state = fsm_context()
    await on_screens(state)
    callback = make_callback("wiz:new_staff")

    await start_new_staff(callback, state, api=AsyncMock(), user=ADMIN)

    text, markup = shown(callback)
    assert text == "Выберите роль:"
    assert buttons(markup)[:3] == [
        ("Администратор", "staff_role:admin"), ("Мастер", "staff_role:master"), ("Механик", "staff_role:mechanic"),
    ]


async def test_start_refused_for_master():
    state = fsm_context()
    callback = make_callback("wiz:new_staff")

    await start_new_staff(callback, state, api=AsyncMock(), user=MASTER)

    assert await state.get_state() is None
    callback.answer.assert_awaited_once_with("Недостаточно прав")


async def _at(state, step, **data):
    await on_screens(state)
    await state.set_state(step)
    await state.update_data(wiz_name="new_staff", wiz_steps=[], **data)


async def test_role_then_name_then_id_creates_user_and_shows_menu():
    state = fsm_context()
    await _at(state, NewStaffStates.choosing_role)
    api = AsyncMock()
    api.create_staff_user.return_value = {"full_name": "Сидоров"}

    callback = make_callback("staff_role:mechanic")
    await choose_staff_role(callback, state, api=api, user=ADMIN)
    assert shown(callback)[0] == "Введите ФИО сотрудника:"

    message = make_message("Сидоров")
    await receive_staff_full_name(message, state, api=api, user=ADMIN)
    assert shown(message)[0] == "Введите Telegram ID сотрудника (или «-», если пока неизвестен):"

    message = make_message("12345")
    await receive_telegram_id(message, state, api=api, user=ADMIN)

    api.create_staff_user.assert_awaited_once_with(role="mechanic", full_name="Сидоров", telegram_id=12345)
    assert shown(message)[0] == "Сотрудник создан: Сидоров\n\nГлавное меню"
    assert await state.get_state() is None


async def test_dash_means_no_telegram_id():
    state = fsm_context()
    await _at(state, NewStaffStates.waiting_for_telegram_id, role="master", full_name="Петров")
    api = AsyncMock()
    api.create_staff_user.return_value = {"full_name": "Петров"}

    await receive_telegram_id(make_message("-"), state, api=api, user=ADMIN)

    assert api.create_staff_user.await_args.kwargs["telegram_id"] is None


async def test_non_numeric_id_reprompts():
    state = fsm_context()
    await _at(state, NewStaffStates.waiting_for_telegram_id, role="master", full_name="Петров")
    api = AsyncMock()
    message = make_message("abc")

    await receive_telegram_id(message, state, api=api, user=ADMIN)

    api.create_staff_user.assert_not_awaited()
    assert shown(message)[0].startswith("Telegram ID должен быть числом или «-».\n\n")
