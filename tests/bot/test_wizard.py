from unittest.mock import AsyncMock

from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot import nav, wizard
from tests.bot.helpers import MASTER, buttons, fsm_context, make_callback, make_message, on_screens, shown


class _Demo(StatesGroup):
    first = State()
    second = State()
    third = State()


@wizard.step(_Demo.first)
async def _first(state, api, user):
    return "first?", None


@wizard.step(_Demo.second)
async def _second(state, api, user):
    builder = InlineKeyboardBuilder()
    builder.button(text="pick", callback_data="pick")
    return "second?", builder.as_markup()


@wizard.step(_Demo.third)
async def _third(state, api, user):
    return "third?", None


@nav.screen("w_source")
async def _source(api, user, args):
    return "source", InlineKeyboardMarkup(inline_keyboard=[])


async def _started(state):
    await on_screens(state, ("w_source", {}))
    await wizard.start(make_callback("x"), state, AsyncMock(), MASTER, "demo", _Demo.first, visit_id="v1")


async def test_start_shows_first_prompt_with_controls_and_keeps_stack():
    state = fsm_context()
    await on_screens(state, ("w_source", {}))
    await state.update_data(stale="old wizard")
    callback = make_callback("x")

    await wizard.start(callback, state, AsyncMock(), MASTER, "demo", _Demo.first, visit_id="v1")

    text, markup = shown(callback)
    assert text == "first?"
    assert buttons(markup) == [("‹ Назад", "wiz_back"), ("✖ Отмена", "wiz_cancel")]
    assert await state.get_state() == _Demo.first.state
    data = await state.get_data()
    assert data["visit_id"] == "v1" and data["wiz_name"] == "demo" and data["wiz_steps"] == []
    assert "stale" not in data
    assert data["nav_stack"] == [["menu", {}], ["w_source", {}]]
    assert await wizard.name(state) == "demo"


async def test_step_choices_come_before_controls():
    state = fsm_context()
    await _started(state)
    message = make_message("answer")

    await wizard.goto(message, state, AsyncMock(), MASTER, _Demo.second)

    assert buttons(shown(message)[1]) == [("pick", "pick"), ("‹ Назад", "wiz_back"), ("✖ Отмена", "wiz_cancel")]


async def test_back_returns_to_previous_step_and_keeps_data():
    state = fsm_context()
    await _started(state)
    await wizard.goto(make_message("a"), state, AsyncMock(), MASTER, _Demo.second)
    await wizard.goto(make_message("b"), state, AsyncMock(), MASTER, _Demo.third)
    callback = make_callback("wiz_back")

    await wizard.back_callback(callback, state, api=AsyncMock(), user=MASTER)

    assert await state.get_state() == _Demo.second.state
    assert shown(callback)[0] == "second?"
    assert (await state.get_data())["visit_id"] == "v1"


async def test_back_on_first_step_cancels_to_source_screen():
    state = fsm_context()
    await _started(state)
    callback = make_callback("wiz_back")

    await wizard.back_callback(callback, state, api=AsyncMock(), user=MASTER)

    assert await state.get_state() is None
    assert shown(callback)[0] == "source"


async def test_cancel_drops_wizard_data_and_redraws_source():
    state = fsm_context()
    await _started(state)
    await wizard.goto(make_message("a"), state, AsyncMock(), MASTER, _Demo.second)
    callback = make_callback("wiz_cancel")

    await wizard.cancel_callback(callback, state, api=AsyncMock(), user=MASTER)

    assert await state.get_state() is None
    assert "visit_id" not in await state.get_data()
    assert shown(callback)[0] == "source"


async def test_commit_drops_history_so_back_cancels():
    state = fsm_context()
    await _started(state)
    await wizard.goto(make_message("a"), state, AsyncMock(), MASTER, _Demo.second, commit=True)
    callback = make_callback("wiz_back")

    await wizard.back_callback(callback, state, api=AsyncMock(), user=MASTER)

    assert await state.get_state() is None


async def test_goto_same_step_does_not_grow_history():
    state = fsm_context()
    await _started(state)
    await wizard.goto(make_message("a"), state, AsyncMock(), MASTER, _Demo.second)
    await wizard.goto(make_message("b"), state, AsyncMock(), MASTER, _Demo.second)

    assert (await state.get_data())["wiz_steps"] == [_Demo.first.state]


async def test_reprompt_puts_error_above_prompt_in_new_message():
    state = fsm_context()
    await _started(state)
    message = make_message("bad")

    await wizard.reprompt(message, state, AsyncMock(), MASTER, "Введите число.")

    assert shown(message)[0] == "Введите число.\n\nfirst?"


async def test_finish_keeps_stack():
    state = fsm_context()
    await _started(state)

    await wizard.finish(state)

    assert await state.get_state() is None
    assert set(await state.get_data()) == {"nav_stack", "nav_msg_id"}


async def test_back_without_wizard_is_stale():
    state = fsm_context()
    callback = make_callback("wiz_back")

    await wizard.back_callback(callback, state, api=AsyncMock(), user=MASTER)

    callback.answer.assert_awaited_once_with("Кнопка устарела — начните действие заново.")
