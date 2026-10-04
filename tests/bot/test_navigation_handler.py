from unittest.mock import AsyncMock

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from bot.callback_ids import encode_id
from bot.handlers.navigation import open_visit_callback, show_active_visits

ME = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
OTHER = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
V1 = "11111111-1111-1111-1111-111111111111"
V2 = "22222222-2222-2222-2222-222222222222"


def _fsm_context() -> FSMContext:
    return FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=1, user_id=1))


def _visit(visit_id, master_id, status="in_progress", plate="А123ВС77", client="Иванов Пётр"):
    return {
        "id": visit_id, "status": status, "plate_number": plate, "client_name": client,
        "assigned_master_id": master_id, "created_at": "2026-10-02T07:00:00+00:00",
        "make_model": "Toyota Camry", "master_name": "Мастер", "total_amount": 0,
    }


def _buttons(message):
    markup = message.answer.await_args.kwargs["reply_markup"]
    return [(b.text, b.callback_data) for row in markup.inline_keyboard for b in row]


async def test_active_visits_marks_own_with_star_and_links_to_card():
    message = AsyncMock()
    api = AsyncMock()
    api.list_visits.return_value = {
        "items": [_visit(V1, ME), _visit(V2, OTHER, status="diagnostics", plate="В001ОР50", client="Петрова")],
        "has_more": False,
    }

    await show_active_visits(message, _fsm_context(), api=api, user={"id": ME, "role": "master"})

    api.list_visits.assert_awaited_once_with(active=True)
    assert message.answer.await_args.args[0] == "Заезды в работе (2)"
    assert _buttons(message) == [
        ("⭐ А123ВС77 · Иванов Пётр · Ремонт", f"visit_open:{encode_id(V1)}"),
        ("В001ОР50 · Петрова · Диагностика", f"visit_open:{encode_id(V2)}"),
    ]


async def test_active_visits_admin_sees_no_stars():
    message = AsyncMock()
    api = AsyncMock()
    api.list_visits.return_value = {"items": [_visit(V1, OTHER)], "has_more": False}

    await show_active_visits(message, _fsm_context(), api=api, user={"id": ME, "role": "admin"})

    assert not _buttons(message)[0][0].startswith("⭐")


async def test_active_visits_empty():
    message = AsyncMock()
    api = AsyncMock()
    api.list_visits.return_value = {"items": [], "has_more": False}

    await show_active_visits(message, _fsm_context(), api=api, user={"id": ME, "role": "master"})

    message.answer.assert_awaited_once_with("Незакрытых заездов нет.")


async def test_active_visits_warns_when_truncated():
    message = AsyncMock()
    api = AsyncMock()
    api.list_visits.return_value = {"items": [_visit(V1, ME)], "has_more": True}

    await show_active_visits(message, _fsm_context(), api=api, user={"id": ME, "role": "master"})

    assert message.answer.await_args.args[0] == "Заезды в работе (1)\nПоказаны последние 30."


async def test_active_visits_clears_wizard_state():
    message = AsyncMock()
    api = AsyncMock()
    api.list_visits.return_value = {"items": [], "has_more": False}
    state = _fsm_context()
    await state.update_data(visit_id="stale")

    await show_active_visits(message, state, api=api, user={"id": ME, "role": "master"})

    assert await state.get_data() == {}


async def test_open_visit_sends_card():
    callback = AsyncMock()
    callback.data = f"visit_open:{encode_id(V1)}"
    api = AsyncMock()
    api.get_visit.return_value = _visit(V1, ME)
    api.list_work_items.return_value = []

    await open_visit_callback(callback, api=api)

    api.get_visit.assert_awaited_once_with(V1)
    api.list_work_items.assert_awaited_once_with(V1)
    assert callback.message.answer.await_args.args[0].startswith("А123ВС77 · Toyota Camry · Иванов Пётр")
    callback.answer.assert_awaited_once()
