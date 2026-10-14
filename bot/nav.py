"""Screen stack: one live message that screens redraw in place.

A screen is a render function `(api, user, args) -> (text, markup)` registered
with @screen. FSM data holds the stack (`nav_stack`: [[name, args], ...], the
menu always at the bottom) and the live message id (`nav_msg_id`), so with
RedisStorage both survive restarts. A callback redraws the message it came
from; a text message gets a new message, and the previous live message loses
its buttons so no stale ones stay in the chat.
"""
import logging
from dataclasses import dataclass
from typing import Awaitable, Callable

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.api_client import ApiClient, ApiError
from bot.callback_ids import decode_id, encode_id
from bot.texts import STALE_BUTTON

logger = logging.getLogger(__name__)

router = Router()

NAV_STACK = "nav_stack"
NAV_MSG = "nav_msg_id"
MENU = "menu"
BACK = "back"
HOME = "home"
OPT = "opt"  # opt:<key>:<value> sets one arg of the top screen (filters, sorting, pages)

Event = Message | CallbackQuery
Rendered = tuple[str, InlineKeyboardMarkup]
Render = Callable[[ApiClient, dict, dict], Awaitable[Rendered]]


@dataclass(frozen=True)
class Screen:
    render: Render
    params: tuple[str, ...]


SCREENS: dict[str, Screen] = {}


def screen(name: str, params: tuple[str, ...] = ()):
    """Register a render function; `params` name the UUIDs a `go:` button carries, in order."""

    def decorator(render: Render) -> Render:
        SCREENS[name] = Screen(render, params)
        return render

    return decorator


def go_data(name: str, *ids: str) -> str:
    return ":".join(["go", name, *(encode_id(i) for i in ids)])


def _base_stack() -> list:
    return [[MENU, {}]]


async def _get_stack(state: FSMContext) -> list:
    return (await state.get_data()).get(NAV_STACK) or _base_stack()


async def top_name(state: FSMContext) -> str:
    return (await _get_stack(state))[-1][0]


async def clear_wizard(state: FSMContext) -> None:
    """Drop wizard state and data; keep the screen stack and the live message."""
    data = await state.get_data()
    await state.set_state(None)
    await state.set_data({key: data[key] for key in (NAV_STACK, NAV_MSG) if key in data})


async def present(event: Event, state: FSMContext, text: str, markup: InlineKeyboardMarkup | None) -> None:
    """Show `text` as the live message: edit the pressed message, or send a new one for a text message."""
    if isinstance(event, CallbackQuery):
        message, bot = event.message, event.bot
        if not isinstance(message, Message):
            # Deleted or otherwise inaccessible: nothing to edit, start a new live message.
            live_id = (await bot.send_message(message.chat.id, text, reply_markup=markup)).message_id
        else:
            try:
                await message.edit_text(text, reply_markup=markup)
                live_id = message.message_id
            except TelegramBadRequest as e:
                if "message is not modified" in e.message:
                    live_id = message.message_id
                else:
                    live_id = (await message.answer(text, reply_markup=markup)).message_id
    else:
        message, bot = event, event.bot
        live_id = (await message.answer(text, reply_markup=markup)).message_id
    previous = (await state.get_data()).get(NAV_MSG)
    if previous is not None and previous != live_id:
        try:
            await bot.edit_message_reply_markup(chat_id=message.chat.id, message_id=previous, reply_markup=None)
        except TelegramAPIError:
            logger.debug("Could not remove buttons from message %s", previous)
    await state.update_data(**{NAV_MSG: live_id})


async def _render(api: ApiClient, user: dict, stack: list, notice: str | None) -> Rendered:
    name, args = stack[-1]
    text, markup = await SCREENS[name].render(api, user, args)
    if len(stack) > 1:
        nav_row = [
            InlineKeyboardButton(text="‹ Назад", callback_data=BACK),
            InlineKeyboardButton(text="🏠 Меню", callback_data=HOME),
        ]
        markup = InlineKeyboardMarkup(inline_keyboard=[*markup.inline_keyboard, nav_row])
    if notice:
        text = f"{notice}\n\n{text}"
    return text, markup


async def _commit(event: Event, state: FSMContext, stack: list, rendered: Rendered) -> None:
    await present(event, state, *rendered)
    await state.update_data(**{NAV_STACK: stack})
    if isinstance(event, CallbackQuery):
        await event.answer()


async def _show(event: Event, state: FSMContext, api: ApiClient, user: dict, stack: list, notice: str | None = None) -> bool:
    """Render the top of `stack`; the stack is saved only if rendering succeeded."""
    try:
        rendered = await _render(api, user, stack, notice)
    except ApiError as e:
        if isinstance(event, CallbackQuery):
            await event.answer(e.message, show_alert=True)
        else:
            await event.answer(e.message)
        return False
    await _commit(event, state, stack, rendered)
    return True


async def push(event: Event, state: FSMContext, api: ApiClient, user: dict, name: str, args: dict, notice: str | None = None) -> bool:
    return await _show(event, state, api, user, [*await _get_stack(state), [name, args]], notice)


async def refresh(event: Event, state: FSMContext, api: ApiClient, user: dict, notice: str | None = None) -> bool:
    return await _show(event, state, api, user, await _get_stack(state), notice)


async def replace_top(event: Event, state: FSMContext, api: ApiClient, user: dict, args: dict) -> bool:
    stack = await _get_stack(state)
    return await _show(event, state, api, user, [*stack[:-1], [stack[-1][0], args]])


async def home(event: Event, state: FSMContext, api: ApiClient, user: dict, notice: str | None = None) -> bool:
    return await _show(event, state, api, user, _base_stack(), notice)


async def pop(event: Event, state: FSMContext, api: ApiClient, user: dict, notice: str | None = None) -> None:
    """Back one screen; if that screen can't be shown any more, fall back to the menu with the error on top."""
    stack = (await _get_stack(state))[:-1] or _base_stack()
    try:
        rendered = await _render(api, user, stack, notice)
    except ApiError as e:
        stack = _base_stack()
        rendered = await _render(api, user, stack, e.message)
    await _commit(event, state, stack, rendered)


async def top_args(callback: CallbackQuery, state: FSMContext, name: str) -> dict | None:
    """Args of the top screen for an `act:` button.

    The button carries no ids, so it is honoured only on the live message while
    `name` is on top; otherwise it would act on whatever screen is there now.
    """
    data = await state.get_data()
    stack = data.get(NAV_STACK) or _base_stack()
    if stack[-1][0] != name or data.get(NAV_MSG) != callback.message.message_id:
        await callback.answer(STALE_BUTTON)
        return None
    return stack[-1][1]


@router.callback_query(F.data.startswith("go:"))
async def go_callback(callback: CallbackQuery, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    _, name, *encoded = callback.data.split(":")
    spec = SCREENS.get(name)
    if spec is None or len(encoded) != len(spec.params):
        await callback.answer(STALE_BUTTON)
        return
    await clear_wizard(state)
    await push(callback, state, api, user, name, dict(zip(spec.params, map(decode_id, encoded))))


@router.callback_query(F.data == BACK)
async def back_callback(callback: CallbackQuery, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    await clear_wizard(state)
    await pop(callback, state, api, user)


@router.callback_query(F.data == HOME)
async def home_callback(callback: CallbackQuery, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    await clear_wizard(state)
    await home(callback, state, api, user)


def option_button(label: str, key: str, value: str, current: str) -> InlineKeyboardButton:
    """One choice of a filter row; the current one is ticked."""
    text = f"✓ {label}" if value == current else label
    return InlineKeyboardButton(text=text, callback_data=f"{OPT}:{key}:{value}")


OPEN = "open"  # arg naming the dropdown that is unfolded; "-" or absent = all folded


def dropdown(
    title: str, key: str, options: list[tuple[str, str]], current: str, opened: str, per_row: int = 2
) -> list[list[InlineKeyboardButton]]:
    """Telegram has no select: one button shows the choice and unfolds the options in place."""
    if opened != key:
        label = dict(options).get(current, options[0][1])
        return [[InlineKeyboardButton(text=f"{title}: {label} ▾", callback_data=f"{OPT}:{OPEN}:{key}")]]
    choices = [option_button(label, key, value, current) for value, label in options]
    return [
        [InlineKeyboardButton(text=f"{title} ▴", callback_data=f"{OPT}:{OPEN}:-")],
        *[choices[i : i + per_row] for i in range(0, len(choices), per_row)],
    ]


def _offered(message) -> set[str]:
    markup = getattr(message, "reply_markup", None)
    if not isinstance(markup, InlineKeyboardMarkup):
        return set()
    return {b.callback_data for row in markup.inline_keyboard for b in row if b.callback_data}


@router.callback_query(F.data.startswith(f"{OPT}:"))
async def option_callback(callback: CallbackQuery, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    _, key, value = callback.data.split(":", 2)
    data = await state.get_data()
    stack = data.get(NAV_STACK) or _base_stack()
    # Callback data is client-supplied: honour only a button the live message really shows,
    # so a forged opt: can't overwrite screen ids or feed renders values they never offered.
    if data.get(NAV_MSG) != callback.message.message_id or callback.data not in _offered(callback.message):
        await callback.answer(STALE_BUTTON)
        return
    args = {**stack[-1][1], key: value}
    if key != OPEN:
        args.pop(OPEN, None)  # a choice folds its dropdown
        if key != "page":
            args.pop("page", None)  # a new filter starts from the first page
    await replace_top(callback, state, api, user, args)
