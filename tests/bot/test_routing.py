"""Dispatcher-level routing tests: feed real Updates through the routers
wired exactly as bot/main.py wires them (middlewares excluded; `api` and
`user` are injected as workflow data)."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import SendMessage
from aiogram.types import CallbackQuery, Chat, Message, MessageEntity, Update, User

from bot.main import build_dispatcher
from bot.states import AddWorkItemStates, NewClientStates, NewVisitStates

CHAT_ID = USER_ID = 1001


class RecordingBot(Bot):
    def __init__(self):
        super().__init__(token="42:TEST")
        self.sent: list = []

    async def __call__(self, method, request_timeout=None):
        self.sent.append(method)
        if isinstance(method, SendMessage):
            return Message(
                message_id=100 + len(self.sent),
                date=datetime.now(timezone.utc),
                chat=Chat(id=CHAT_ID, type="private"),
                text=method.text,
            )
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
            entities=[MessageEntity(type="bot_command", offset=0, length=len(text))] if text.startswith("/") else None,
        ),
    )


def _callback(data: str, message_id: int = 5) -> Update:
    return Update(
        update_id=2,
        callback_query=CallbackQuery(
            id="cb1",
            chat_instance="ci",
            from_user=User(id=USER_ID, is_bot=False, first_name="T"),
            data=data,
            message=Message(
                message_id=message_id,
                date=datetime.now(timezone.utc),
                chat=Chat(id=CHAT_ID, type="private"),
                text="old",
            ),
        ),
    )


# Routers are module-level singletons and can be attached to one Dispatcher only.
_DP = build_dispatcher(MemoryStorage())


@pytest.fixture
def env():
    bot = RecordingBot()
    dp = _DP
    dp.fsm.storage = MemoryStorage()
    state = dp.fsm.get_context(bot=bot, chat_id=CHAT_ID, user_id=USER_ID)
    api = AsyncMock()
    api.list_visits.return_value = {"items": [], "has_more": False}
    user = {"id": "m1", "role": "master"}
    return bot, dp, state, api, user


def _texts(bot: RecordingBot) -> list[str]:
    return [getattr(m, "text", None) for m in bot.sent]


async def test_wizard_callback_outside_its_state_is_answered_as_stale(env):
    bot, dp, state, api, user = env

    await dp.feed_update(bot, _callback("vehicle_pick:v1"), api=api, user=user)

    assert await state.get_state() is None
    answers = [m for m in bot.sent if type(m).__name__ == "AnswerCallbackQuery"]
    assert answers and answers[0].text == "Кнопка устарела — начните действие заново."


@pytest.mark.parametrize(
    "data",
    ["client_pick:c1", "vehicle_pick:v1", "catalog_pick:none", "category_pick:body", "staff_role:master", "mileage_confirm", "master_pick:AAAAAAAAAAAAAAAAAAAAAA", "client_add", "vehicle_add"],
)
async def test_state_bound_wizard_callbacks_do_not_fire_without_state(env, data):
    bot, dp, state, api, user = env

    await dp.feed_update(bot, _callback(data), api=api, user=user)

    assert await state.get_state() is None
    assert await state.get_data() == {}
    api.create_visit.assert_not_awaited()


async def test_mileage_confirm_callback_routes_in_confirming_state(env):
    bot, dp, state, api, user = env
    await state.set_state(NewVisitStates.confirming_mileage)
    await state.update_data(client_id="c1", vehicle_id="v1", mileage=900, wiz_name="new_visit", wiz_steps=[])
    api.create_visit.return_value = {"id": "11111111-1111-1111-1111-111111111111", "status": "received"}
    api.get_visit.return_value = {"id": "11111111-1111-1111-1111-111111111111", "status": "received", "total_amount": 0}
    api.list_work_items.return_value = []

    await dp.feed_update(bot, _callback("mileage_confirm"), api=api, user=user)

    api.create_visit.assert_awaited_once_with(
        client_id="c1", vehicle_id="v1", assigned_master_id="m1", mileage_at_intake=900,
        mileage_manually_confirmed=True,
    )
    assert await state.get_state() is None


async def test_search_page_button_routes_to_search_not_stale_fallback(env):
    bot, dp, state, api, user = env
    await state.update_data(nav_stack=[["menu", {}], ["search_results", {"query": "Toyota", "page": 0}]], nav_msg_id=5)
    api.search.return_value = [
        {"entity": "vehicle", "id": f"{n:08d}-0000-0000-0000-000000000000", "matched_field": "make"} for n in range(12)
    ]
    api.get_vehicle.return_value = {"make": "Toyota", "model": "Camry", "plate_number": "А1"}

    await dp.feed_update(bot, _callback("act:spage:1"), api=api, user=user)

    api.search.assert_awaited_once_with("Toyota")
    edits = [m for m in bot.sent if type(m).__name__ == "EditMessageText"]
    assert edits and edits[0].text.startswith("Найдено: 12 · стр. 2/2")


async def test_old_reply_keyboard_text_beats_wizard_and_opens_menu(env):
    bot, dp, state, api, user = env
    await state.set_state(NewVisitStates.waiting_for_mileage)
    await state.update_data(client_id="c1", vehicle_id="v1")

    await dp.feed_update(bot, _message("Поиск"), api=api, user=user)

    assert await state.get_state() is None
    assert "Главное меню" in _texts(bot)
    api.search.assert_not_awaited()


async def test_menu_command_beats_wizard(env):
    bot, dp, state, api, user = env
    await state.set_state(AddWorkItemStates.waiting_for_hours_and_rate)

    await dp.feed_update(bot, _message("/menu"), api=api, user=user)

    assert await state.get_state() is None
    assert "Главное меню" in _texts(bot)


async def test_full_flow_menu_to_work_and_back(env):
    from bot.callback_ids import encode_id

    bot, dp, state, api, user = env
    visit_id, item_id = "11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222"
    api.list_visits.return_value = {"items": [], "has_more": False}
    api.get_visit.return_value = {"id": visit_id, "status": "in_progress", "total_amount": 0, "plate_number": "А1"}
    api.list_work_items.return_value = [
        {"id": item_id, "name": "Масло", "status": "in_progress", "approved_by_client": True, "assigned_mechanic_name": None},
    ]

    await dp.feed_update(bot, _message("/start"), api=api, user=user)
    live = (await state.get_data())["nav_msg_id"]
    for data in ("go:active_visits", f"go:visit:{encode_id(visit_id)}", f"go:work:{encode_id(visit_id)}:{encode_id(item_id)}"):
        await dp.feed_update(bot, _callback(data, message_id=live), api=api, user=user)
    assert [s[0] for s in (await state.get_data())["nav_stack"]] == ["menu", "active_visits", "visit", "work"]

    await dp.feed_update(bot, _callback("act:wstatus:ready", message_id=live), api=api, user=user)
    api.update_work_item_status.assert_awaited_once_with(visit_id, item_id, "ready")

    await dp.feed_update(bot, _callback("back", message_id=live), api=api, user=user)
    assert [s[0] for s in (await state.get_data())["nav_stack"]] == ["menu", "active_visits", "visit"]


async def test_wizard_back_and_cancel_route_through_dispatcher(env):
    bot, dp, state, api, user = env
    await state.update_data(nav_stack=[["menu", {}]], nav_msg_id=5)

    await dp.feed_update(bot, _callback("wiz:new_visit"), api=api, user=user)
    assert await state.get_state() == NewVisitStates.waiting_for_client_query.state

    await dp.feed_update(bot, _callback("wiz_cancel"), api=api, user=user)
    assert await state.get_state() is None
    assert (await state.get_data())["nav_stack"] == [["menu", {}]]


async def test_old_format_buttons_are_stale(env):
    bot, dp, state, api, user = env

    for data in ("visit_open:AAAAAAAAAAAAAAAAAAAAAA", "wsc:a:b:ready", "add_work:x", "search_page:1"):
        await dp.feed_update(bot, _callback(data), api=api, user=user)

    answers = [m.text for m in bot.sent if type(m).__name__ == "AnswerCallbackQuery"]
    assert answers == ["Кнопка устарела — начните действие заново."] * 4


async def test_text_at_a_button_step_stays_in_the_wizard(env):
    bot, dp, state, api, user = env
    await state.set_state(AddWorkItemStates.choosing_mechanic)
    await state.update_data(
        nav_stack=[["menu", {}]], nav_msg_id=5, wiz_name="add_work", wiz_steps=[],
        mechanic_choices=[["AAAAAAAAAAAAAAAAAAAAAA", "Петров"]],
    )

    await dp.feed_update(bot, _message("Петров"), api=api, user=user)

    api.search.assert_not_awaited()
    assert await state.get_state() == AddWorkItemStates.choosing_mechanic.state
    assert "Выберите вариант кнопкой.\n\nКому назначить работу?" in _texts(bot)


async def test_double_tap_on_final_wizard_button_creates_one_work_item(env):
    import asyncio

    bot, dp, state, api, user = env
    visit_id = "11111111-1111-1111-1111-111111111111"
    await state.set_state(AddWorkItemStates.choosing_mechanic)
    await state.update_data(
        nav_stack=[["menu", {}], ["visit", {"visit_id": visit_id}]], nav_msg_id=5, wiz_name="add_work", wiz_steps=[],
        visit_id=visit_id, catalog_item_id=None, free_text_name="X", category="other", norm_hours=1.0, hourly_rate=100.0,
    )

    async def slow_add(*args, **kwargs):
        await asyncio.sleep(0.05)
        return {}

    api.add_work_item.side_effect = slow_add
    api.get_visit.return_value = {"id": visit_id, "status": "in_progress", "total_amount": 0}
    api.list_work_items.return_value = []

    await asyncio.gather(*(dp.feed_update(bot, _callback("assign_mech:none"), api=api, user=user) for _ in range(2)))

    assert api.add_work_item.await_count == 1
