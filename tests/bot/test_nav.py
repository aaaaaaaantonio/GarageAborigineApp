from unittest.mock import AsyncMock

from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.state import State, StatesGroup
from aiogram.methods import EditMessageText
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot import nav
from bot.api_client import ApiNotFound
from bot.callback_ids import encode_id
from tests.bot.helpers import MASTER, buttons, fsm_context, make_callback, make_message, on_screens, shown

if nav.MENU not in nav.SCREENS:
    @nav.screen(nav.MENU)
    async def _placeholder_menu(api, user, args):
        return "menu", InlineKeyboardMarkup(inline_keyboard=[])


A = "11111111-1111-1111-1111-111111111111"
B = "22222222-2222-2222-2222-222222222222"


@nav.screen("t_item", params=("item_id",))
async def _render_item(api, user, args):
    return f"item {args['item_id']}", InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="x", callback_data="x")]])


@nav.screen("t_broken")
async def _render_broken(api, user, args):
    raise ApiNotFound("Не найдено")


class _Wiz(StatesGroup):
    step = State()


def _bad_request(text: str) -> TelegramBadRequest:
    return TelegramBadRequest(method=EditMessageText(text="x"), message=text)


async def _stack(state):
    return (await state.get_data())["nav_stack"]


async def test_go_pushes_screen_and_edits_pressed_message():
    state = fsm_context()
    await on_screens(state)
    callback = make_callback(f"go:t_item:{encode_id(A)}")

    await nav.go_callback(callback, state, api=AsyncMock(), user=MASTER)

    assert await _stack(state) == [["menu", {}], ["t_item", {"item_id": A}]]
    text, markup = shown(callback)
    assert text == f"item {A}"
    assert buttons(markup)[-2:] == [("‹ Назад", "back"), ("🏠 Меню", "home")]
    callback.answer.assert_awaited_once_with()


async def test_go_data_encodes_ids():
    assert nav.go_data("t_item", A) == f"go:t_item:{encode_id(A)}"
    assert nav.go_data("active_visits") == "go:active_visits"


async def test_back_pops_to_previous_screen():
    state = fsm_context()
    await on_screens(state, ("t_item", {"item_id": A}), ("t_item", {"item_id": B}))
    callback = make_callback("back")

    await nav.back_callback(callback, state, api=AsyncMock(), user=MASTER)

    assert await _stack(state) == [["menu", {}], ["t_item", {"item_id": A}]]
    assert shown(callback)[0] == f"item {A}"


async def test_back_without_stack_goes_to_menu():
    state = fsm_context()  # e.g. storage lost: no nav data at all

    await nav.back_callback(make_callback("back"), state, api=AsyncMock(), user=MASTER)

    assert await _stack(state) == [["menu", {}]]


async def test_home_resets_stack_to_menu():
    state = fsm_context()
    await on_screens(state, ("t_item", {"item_id": A}), ("t_item", {"item_id": B}))

    await nav.home_callback(make_callback("home"), state, api=AsyncMock(), user=MASTER)

    assert await _stack(state) == [["menu", {}]]


async def test_render_error_alerts_and_keeps_stack():
    state = fsm_context()
    await on_screens(state, ("t_item", {"item_id": A}))
    callback = make_callback("go:t_broken")

    await nav.go_callback(callback, state, api=AsyncMock(), user=MASTER)

    callback.answer.assert_awaited_once_with("Не найдено", show_alert=True)
    callback.message.edit_text.assert_not_awaited()
    assert await _stack(state) == [["menu", {}], ["t_item", {"item_id": A}]]


async def test_back_into_broken_screen_shows_menu_with_error():
    state = fsm_context()
    await on_screens(state, ("t_broken", {}), ("t_item", {"item_id": A}))
    callback = make_callback("back")

    await nav.back_callback(callback, state, api=AsyncMock(), user=MASTER)

    assert await _stack(state) == [["menu", {}]]
    assert shown(callback)[0].startswith("Не найдено\n\n")


async def test_text_message_sends_new_message_and_strips_previous_live_one():
    state = fsm_context()
    await on_screens(state, msg_id=5)
    message = make_message("query", message_id=9)

    await nav.push(message, state, AsyncMock(), MASTER, "t_item", {"item_id": A})

    assert shown(message)[0] == f"item {A}"
    message.bot.edit_message_reply_markup.assert_awaited_once_with(chat_id=1, message_id=5, reply_markup=None)
    assert (await state.get_data())["nav_msg_id"] == 109


async def test_not_modified_is_ignored():
    state = fsm_context()
    await on_screens(state, ("t_item", {"item_id": A}))
    callback = make_callback("x")
    callback.message.edit_text.side_effect = _bad_request("Bad Request: message is not modified")

    await nav.refresh(callback, state, AsyncMock(), MASTER)

    callback.message.answer.assert_not_awaited()
    callback.answer.assert_awaited_once_with()


async def test_failed_edit_sends_new_message():
    state = fsm_context()
    await on_screens(state, ("t_item", {"item_id": A}))
    callback = make_callback("x")
    callback.message.edit_text.side_effect = _bad_request("Bad Request: message to edit not found")

    await nav.refresh(callback, state, AsyncMock(), MASTER)

    callback.message.answer.assert_awaited_once()
    assert (await state.get_data())["nav_msg_id"] == 105


async def test_failed_strip_of_old_buttons_is_ignored():
    state = fsm_context()
    await on_screens(state, msg_id=5)
    message = make_message("q", message_id=9)
    message.bot.edit_message_reply_markup.side_effect = _bad_request("Bad Request: message can't be edited")

    await nav.push(message, state, AsyncMock(), MASTER, "t_item", {"item_id": A})

    assert (await state.get_data())["nav_msg_id"] == 109


async def test_notice_goes_above_screen_text():
    state = fsm_context()
    await on_screens(state, ("t_item", {"item_id": A}))
    callback = make_callback("x")

    await nav.refresh(callback, state, AsyncMock(), MASTER, notice="Готово.")

    assert shown(callback)[0] == f"Готово.\n\nitem {A}"


async def test_replace_top_keeps_depth():
    state = fsm_context()
    await on_screens(state, ("t_item", {"item_id": A}))

    await nav.replace_top(make_callback("x"), state, AsyncMock(), MASTER, {"item_id": B})

    assert await _stack(state) == [["menu", {}], ["t_item", {"item_id": B}]]


async def test_top_args_on_live_top_screen():
    state = fsm_context()
    await on_screens(state, ("t_item", {"item_id": A}), msg_id=5)

    assert await nav.top_args(make_callback("act:x", message_id=5), state, "t_item") == {"item_id": A}


async def test_top_args_wrong_screen_is_stale():
    state = fsm_context()
    await on_screens(state, ("t_item", {"item_id": A}), msg_id=5)
    callback = make_callback("act:x", message_id=5)

    assert await nav.top_args(callback, state, "visit") is None
    callback.answer.assert_awaited_once_with("Кнопка устарела — начните действие заново.")


async def test_top_args_on_old_message_is_stale():
    state = fsm_context()
    await on_screens(state, ("t_item", {"item_id": A}), msg_id=5)
    callback = make_callback("act:x", message_id=4)

    assert await nav.top_args(callback, state, "t_item") is None
    callback.answer.assert_awaited_once_with("Кнопка устарела — начните действие заново.")


async def test_clear_wizard_keeps_stack_and_live_message():
    state = fsm_context()
    await on_screens(state, ("t_item", {"item_id": A}), msg_id=5)
    await state.set_state(_Wiz.step)
    await state.update_data(visit_id="v1")

    await nav.clear_wizard(state)

    assert await state.get_state() is None
    assert await state.get_data() == {"nav_stack": [["menu", {}], ["t_item", {"item_id": A}]], "nav_msg_id": 5}


async def test_go_to_unknown_screen_is_stale():
    state = fsm_context()
    callback = make_callback("go:nope")

    await nav.go_callback(callback, state, api=AsyncMock(), user=MASTER)

    callback.answer.assert_awaited_once_with("Кнопка устарела — начните действие заново.")


async def test_go_drops_an_unfinished_wizard():
    state = fsm_context()
    await on_screens(state)
    await state.set_state(_Wiz.step)
    await state.update_data(visit_id="v1")

    await nav.go_callback(make_callback(f"go:t_item:{encode_id(A)}"), state, api=AsyncMock(), user=MASTER)

    assert await state.get_state() is None
    assert "visit_id" not in await state.get_data()
