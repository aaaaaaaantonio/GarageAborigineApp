"""Dispatcher-level routing tests: feed real Updates through the routers
wired exactly as bot/main.py wires them (middlewares excluded; `api` and
`user` are injected as workflow data)."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Chat, Message, Update, User

from bot.keyboards import ALL_MENU_BUTTONS
from bot.main import setup_routers
from bot.states import AddWorkItemStates, NewClientStates, NewVisitStates

CHAT_ID = USER_ID = 1001


class RecordingBot(Bot):
    def __init__(self):
        super().__init__(token="42:TEST")
        self.sent: list = []

    async def __call__(self, method, request_timeout=None):
        self.sent.append(method)
        return True


def _message(text: str) -> Update:
    return Update(
        update_id=1,
        message=Message(
            message_id=1,
            date=datetime.now(timezone.utc),
            chat=Chat(id=CHAT_ID, type="private"),
            from_user=User(id=USER_ID, is_bot=False, first_name="T"),
            text=text,
        ),
    )


def _callback(data: str) -> Update:
    return Update(
        update_id=2,
        callback_query=CallbackQuery(
            id="cb1",
            chat_instance="ci",
            from_user=User(id=USER_ID, is_bot=False, first_name="T"),
            data=data,
            message=Message(
                message_id=5,
                date=datetime.now(timezone.utc),
                chat=Chat(id=CHAT_ID, type="private"),
                text="old",
            ),
        ),
    )


# Routers are module-level singletons and can be attached to one Dispatcher only.
_DP = Dispatcher(storage=MemoryStorage())
setup_routers(_DP)


@pytest.fixture
def env():
    bot = RecordingBot()
    dp = _DP
    dp.fsm.storage = MemoryStorage()
    state = dp.fsm.get_context(bot=bot, chat_id=CHAT_ID, user_id=USER_ID)
    api = AsyncMock()
    user = {"id": "m1", "role": "master"}
    return bot, dp, state, api, user


def _texts(bot: RecordingBot) -> list[str]:
    return [getattr(m, "text", None) for m in bot.sent]


async def test_menu_button_wins_over_wizard_state_and_resets_it(env):
    bot, dp, state, api, user = env
    await state.set_state(NewClientStates.waiting_for_full_name)
    await state.update_data(phone="79990000000", return_flow="new_visit")

    await dp.feed_update(bot, _message("Новый заезд"), api=api, user=user)

    api.create_client.assert_not_awaited()
    assert await state.get_state() == NewVisitStates.waiting_for_client_query.state
    assert await state.get_data() == {}


async def test_menu_button_wins_over_mileage_state(env):
    bot, dp, state, api, user = env
    await state.set_state(NewVisitStates.waiting_for_mileage)
    await state.update_data(client_id="c1", vehicle_id="v1")
    api.search.return_value = []

    await dp.feed_update(bot, _message("Поиск"), api=api, user=user)

    assert await state.get_state() is None
    assert "Введите число (пробег в км)." not in _texts(bot)


@pytest.mark.parametrize("text", ALL_MENU_BUTTONS)
async def test_every_menu_button_clears_active_wizard(env, text):
    bot, dp, state, api, user = env
    api.list_my_work_items.return_value = []
    await state.set_state(AddWorkItemStates.waiting_for_hours_and_rate)
    await state.update_data(visit_id="stale")

    await dp.feed_update(bot, _message(text), api=api, user=user)

    api.add_work_item.assert_not_awaited()
    assert (await state.get_data()).get("visit_id") is None
    assert await state.get_state() != AddWorkItemStates.waiting_for_hours_and_rate.state


async def test_wizard_callback_outside_its_state_is_answered_as_stale(env):
    bot, dp, state, api, user = env

    await dp.feed_update(bot, _callback("vehicle_pick:v1"), api=api, user=user)

    assert await state.get_state() is None
    answers = [m for m in bot.sent if type(m).__name__ == "AnswerCallbackQuery"]
    assert answers and answers[0].text == "Кнопка устарела — начните действие заново."


@pytest.mark.parametrize(
    "data",
    ["client_pick:c1", "vehicle_pick:v1", "catalog_pick:none", "category_pick:body", "staff_role:master", "mileage_confirm"],
)
async def test_state_bound_wizard_callbacks_do_not_fire_without_state(env, data):
    bot, dp, state, api, user = env

    await dp.feed_update(bot, _callback(data), api=api, user=user)

    assert await state.get_state() is None
    assert await state.get_data() == {}
    api.create_visit.assert_not_awaited()
