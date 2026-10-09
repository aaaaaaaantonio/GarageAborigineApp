from unittest.mock import AsyncMock

from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardRemove

from bot.handlers.menu import KEYBOARD_REMOVED, legacy_menu_text, render_menu
from bot.handlers.start import WELCOME, cmd_cancel, cmd_menu, cmd_start
from bot.main import BOT_COMMANDS
from tests.bot.helpers import ADMIN, MASTER, MECHANIC, buttons, fsm_context, make_message, on_screens, shown


class _Wiz(StatesGroup):
    step = State()


async def test_master_menu():
    text, markup = await render_menu(AsyncMock(), MASTER, {})
    assert text == "Главное меню"
    assert buttons(markup) == [
        ("🆕 Новый заезд", "wiz:new_visit"),
        ("🔧 Заезды в работе", "go:active_visits"),
        ("🔍 Поиск", "go:search"),
        ("📝 Регистрация клиента (бумага)", "wiz:paper_consent"),
    ]


async def test_admin_menu_adds_staff():
    _, markup = await render_menu(AsyncMock(), ADMIN, {})
    assert buttons(markup)[-1] == ("👥 Добавить сотрудника", "wiz:new_staff")
    assert len(buttons(markup)) == 5


async def test_mechanic_menu():
    _, markup = await render_menu(AsyncMock(), MECHANIC, {})
    assert buttons(markup) == [("🧰 Мои работы", "go:my_works"), ("🔍 Поиск", "go:search")]


async def test_start_removes_reply_keyboard_clears_wizard_and_shows_menu():
    state = fsm_context()
    await on_screens(state, ("visit", {"visit_id": "v"}))
    await state.set_state(_Wiz.step)
    message = make_message("/start")

    await cmd_start(message, state, api=AsyncMock(), user=MASTER)

    first = message.answer.await_args_list[0]
    assert first.args[0] == WELCOME
    assert isinstance(first.kwargs["reply_markup"], ReplyKeyboardRemove)
    assert shown(message)[0] == "Главное меню"
    assert await state.get_state() is None
    assert (await state.get_data())["nav_stack"] == [["menu", {}]]


async def test_menu_command_shows_menu():
    state = fsm_context()
    await state.set_state(_Wiz.step)
    message = make_message("/menu")

    await cmd_menu(message, state, api=AsyncMock(), user=MASTER)

    assert shown(message)[0] == "Главное меню"
    assert await state.get_state() is None


async def test_cancel_clears_wizard_and_redraws_current_screen():
    state = fsm_context()
    await on_screens(state)
    await state.set_state(_Wiz.step)
    await state.update_data(visit_id="v1")
    message = make_message("/cancel")

    await cmd_cancel(message, state, api=AsyncMock(), user=MASTER)

    assert await state.get_state() is None
    assert "visit_id" not in await state.get_data()
    assert shown(message)[0] == "Действие отменено.\n\nГлавное меню"


async def test_legacy_reply_keyboard_text_removes_keyboard_and_shows_menu():
    state = fsm_context()
    message = make_message("Новый заезд")

    await legacy_menu_text(message, state, api=AsyncMock(), user=MASTER)

    first = message.answer.await_args_list[0]
    assert first.args[0] == KEYBOARD_REMOVED
    assert isinstance(first.kwargs["reply_markup"], ReplyKeyboardRemove)
    assert shown(message)[0] == "Главное меню"


def test_menu_command_is_registered_in_telegram():
    assert ("menu", "Главное меню") in [(c.command, c.description) for c in BOT_COMMANDS]
