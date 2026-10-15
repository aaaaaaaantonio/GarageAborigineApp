from unittest.mock import AsyncMock

import pytest

from bot import nav
from bot.api_client import ApiForbidden
from bot.callback_ids import encode_id
from bot.handlers.admin_settings import (
    choose_scheme, pay_label, receive_value, render_pay, render_settings, start_pay, toggle_setting,
)
from bot.states import PayStates
from tests.bot.helpers import ADMIN, MASTER, MECHANIC, buttons, fsm_context, make_callback, make_message, on_screens, shown

M1 = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"
OFF = {"mechanic_sees_prices": False, "mechanic_sees_client_name": False,
       "mechanic_sees_client_phone": False, "mechanic_sees_vin": True}
PAY = [{"user_id": M1, "full_name": "Морозов", "pay_scheme": "percent", "pay_value": 40.0}]


def _api():
    api = AsyncMock()
    api.get_settings.return_value = OFF
    api.list_mechanic_pay.return_value = PAY
    return api


async def test_settings_screen_shows_switch_states():
    _, markup = await render_settings(_api(), ADMIN, {})

    assert buttons(markup) == [
        ("⬜ Цены и заработок", "act:set:prices"), ("⬜ Имя клиента", "act:set:name"),
        ("⬜ Телефон клиента", "act:set:phone"), ("✅ VIN / номер кузова", "act:set:vin"),
        ("💰 Оплата механиков", nav.go_data("pay")),
    ]


async def test_settings_are_admin_only():
    for user in (MASTER, MECHANIC):
        with pytest.raises(ApiForbidden):
            await render_settings(_api(), user, {})


async def test_toggle_flips_the_setting_and_redraws():
    state = fsm_context()
    await on_screens(state, ("settings", {}))
    api = _api()

    await toggle_setting(make_callback("act:set:vin"), state, api=api, user=ADMIN)

    api.update_settings.assert_awaited_once_with(mechanic_sees_vin=False)


def test_pay_labels():
    assert pay_label({"pay_scheme": "percent", "pay_value": 40.0}) == "40% от работы"
    assert pay_label({"pay_scheme": "percent", "pay_value": 12.5}) == "12,5% от работы"
    assert pay_label({"pay_scheme": "per_hour", "pay_value": 700.0}) == "700 ₽ за н/ч"
    assert pay_label({"pay_scheme": "full", "pay_value": None}) == "вся стоимость"
    assert pay_label({"pay_scheme": None, "pay_value": None}) == "схема не задана"


async def test_pay_screen_lists_mechanics():
    text, markup = await render_pay(_api(), ADMIN, {})

    assert text.startswith("💰 Оплата механиков")
    assert buttons(markup) == [("Морозов · 40% от работы", f"act:pay:{encode_id(M1)}")]


async def _pay_wizard(state, api):
    await on_screens(state, ("settings", {}), ("pay", {}))
    callback = make_callback(f"act:pay:{encode_id(M1)}")
    await start_pay(callback, state, api=api, user=ADMIN)
    return callback


async def test_percent_with_a_comma_saves_and_returns_to_the_list():
    state, api = fsm_context(), _api()
    callback = await _pay_wizard(state, api)
    assert shown(callback)[0] == "Схема оплаты: Морозов"

    await choose_scheme(make_callback("pay_scheme:percent"), state, api=api, user=ADMIN)
    assert await state.get_state() == PayStates.waiting_for_value.state
    message = make_message("12,5")
    await receive_value(message, state, api=api, user=ADMIN)

    api.set_mechanic_pay.assert_awaited_once_with(M1, "percent", 12.5)
    assert await state.get_state() is None
    assert shown(message)[0].startswith("Сохранено\n\n💰 Оплата механиков")


async def test_full_saves_without_asking_a_number():
    state, api = fsm_context(), _api()
    await _pay_wizard(state, api)

    await choose_scheme(make_callback("pay_scheme:full"), state, api=api, user=ADMIN)

    api.set_mechanic_pay.assert_awaited_once_with(M1, "full", None)


async def test_wrong_number_reprompts():
    state, api = fsm_context(), _api()
    await _pay_wizard(state, api)
    await choose_scheme(make_callback("pay_scheme:percent"), state, api=api, user=ADMIN)

    for text in ("abc", "150", "0"):
        message = make_message(text)
        await receive_value(message, state, api=api, user=ADMIN)
        assert shown(message)[0].startswith("Процент — число больше 0 и не больше 100")
    api.set_mechanic_pay.assert_not_awaited()


async def test_pay_refused_for_master():
    state = fsm_context()
    await on_screens(state, ("pay", {}))
    callback = make_callback(f"act:pay:{encode_id(M1)}")

    await start_pay(callback, state, api=_api(), user=MASTER)

    callback.answer.assert_awaited_once_with("Недостаточно прав")


async def test_infinite_rate_reprompts():
    state, api = fsm_context(), _api()
    await _pay_wizard(state, api)
    await choose_scheme(make_callback("pay_scheme:per_hour"), state, api=api, user=ADMIN)

    for text in ("inf", "nan", "-inf"):
        message = make_message(text)
        await receive_value(message, state, api=api, user=ADMIN)
        assert shown(message)[0].startswith("Ставка — число больше нуля")
    api.set_mechanic_pay.assert_not_awaited()
