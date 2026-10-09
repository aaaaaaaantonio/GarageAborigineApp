"""Wizards: multi-step input on FSM states, with step-back and cancel.

Each step registers a prompt `(state, api, user) -> (text, markup | None)`.
`wiz_steps` in FSM data lists the steps behind the current one, so
"‹ Назад" re-shows the previous prompt even in branching wizards, keeping
what was typed. "✖ Отмена" drops the wizard and redraws the screen it was
started from (the top of the screen stack — wizards never push screens).
"""
from typing import Awaitable, Callable

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from bot import nav
from bot.api_client import ApiClient
from bot.texts import STALE_BUTTON

router = Router()

WIZ_NAME = "wiz_name"
WIZ_STEPS = "wiz_steps"
WIZ_BACK = "wiz_back"
WIZ_CANCEL = "wiz_cancel"

Prompt = Callable[[FSMContext, ApiClient, dict], Awaitable[tuple[str, InlineKeyboardMarkup | None]]]
PROMPTS: dict[str, Prompt] = {}


def step(*states: State):
    """Register the prompt shown on entering any of `states`."""

    def decorator(prompt: Prompt) -> Prompt:
        for s in states:
            PROMPTS[s.state] = prompt
        return prompt

    return decorator


async def _show(event: nav.Event, state: FSMContext, api: ApiClient, user: dict, error: str | None = None) -> None:
    text, markup = await PROMPTS[await state.get_state()](state, api, user)
    if error:
        text = f"{error}\n\n{text}"
    controls = [
        InlineKeyboardButton(text="‹ Назад", callback_data=WIZ_BACK),
        InlineKeyboardButton(text="✖ Отмена", callback_data=WIZ_CANCEL),
    ]
    rows = markup.inline_keyboard if markup else []
    await nav.present(event, state, text, InlineKeyboardMarkup(inline_keyboard=[*rows, controls]))
    if isinstance(event, CallbackQuery):
        await event.answer()


async def start(event: nav.Event, state: FSMContext, api: ApiClient, user: dict, name: str, first: State, **data) -> None:
    await nav.clear_wizard(state)
    await state.update_data(**{WIZ_NAME: name, WIZ_STEPS: []}, **data)
    await state.set_state(first)
    await _show(event, state, api, user)


async def goto(event: nav.Event, state: FSMContext, api: ApiClient, user: dict, target: State, *, commit: bool = False) -> None:
    """Move to `target`. After a side effect (an entity was created) pass commit=True:
    the history is dropped, so "‹ Назад" can't lead back into repeating it."""
    current = await state.get_state()
    steps = [] if commit else list((await state.get_data()).get(WIZ_STEPS, []))
    if not commit and current is not None and current != target.state:
        steps.append(current)
    await state.update_data(**{WIZ_STEPS: steps})
    await state.set_state(target)
    await _show(event, state, api, user)


async def reprompt(event: nav.Event, state: FSMContext, api: ApiClient, user: dict, error: str) -> None:
    await _show(event, state, api, user, error=error)


async def retry(event: nav.Event, state: FSMContext, api: ApiClient, user: dict, target: State, error: str) -> None:
    """Return to an earlier step `target` with `error` (e.g. the API said the VIN is taken).
    History is cut back to what it was when `target` was first shown."""
    steps = list((await state.get_data()).get(WIZ_STEPS, []))
    if target.state in steps:
        steps = steps[: steps.index(target.state)]
    await state.update_data(**{WIZ_STEPS: steps})
    await state.set_state(target)
    await _show(event, state, api, user, error=error)


async def name(state: FSMContext) -> str | None:
    return (await state.get_data()).get(WIZ_NAME)


async def finish(state: FSMContext) -> None:
    await nav.clear_wizard(state)


@router.callback_query(F.data == WIZ_CANCEL)
async def cancel_callback(callback: CallbackQuery, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    if await state.get_state() is None:
        await callback.answer(STALE_BUTTON)
        return
    await nav.clear_wizard(state)
    await nav.refresh(callback, state, api, user)


@router.callback_query(F.data == WIZ_BACK)
async def back_callback(callback: CallbackQuery, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    if await state.get_state() is None:
        await callback.answer(STALE_BUTTON)
        return
    steps = list((await state.get_data()).get(WIZ_STEPS, []))
    if not steps:
        await cancel_callback(callback, state, api, user)
        return
    previous = steps.pop()
    await state.update_data(**{WIZ_STEPS: steps})
    await state.set_state(previous)
    await _show(callback, state, api, user)
