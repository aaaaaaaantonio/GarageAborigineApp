from unittest.mock import AsyncMock

import httpx
import respx
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from bot.api_client import ApiClient
from bot.callback_ids import encode_id
from bot.handlers.visits import send_visit_card
from bot.handlers.work_items import choose_new_mechanic_callback, start_reassign_mechanic
from bot.states import ReassignMechanicStates

VISIT_ID = "11111111-1111-1111-1111-111111111111"
ITEM_ID = "22222222-2222-2222-2222-222222222222"
MECH_ID = "33333333-3333-3333-3333-333333333333"
ADMIN = {"id": "44444444-4444-4444-4444-444444444444", "role": "admin"}
MECHANIC = {"id": MECH_ID, "role": "mechanic"}


def _fsm_context() -> FSMContext:
    return FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=1, user_id=1))


def _texts(markup) -> list[tuple[str, str]]:
    return [(b.text, b.callback_data) for row in markup.inline_keyboard for b in row]


async def test_visit_card_shows_mechanic_and_reassign_button():
    message = AsyncMock()
    visit = {"id": VISIT_ID, "status": "in_progress", "total_amount": "0.00"}
    item = {
        "id": ITEM_ID,
        "name": "Замена масла",
        "status": "in_progress",
        "approved_by_client": True,
        "assigned_mechanic_name": "Иванов",
    }

    await send_visit_card(message, visit, [item])

    text = message.answer.await_args.args[0]
    assert "1. Замена масла — В работе · Иванов" in text
    buttons = _texts(message.answer.await_args.kwargs["reply_markup"])
    assert ("👤 Замена масла", f"reassign:{encode_id(VISIT_ID)}:{encode_id(ITEM_ID)}") in buttons


async def test_visit_card_marks_unassigned_item():
    message = AsyncMock()
    visit = {"id": VISIT_ID, "status": "in_progress", "total_amount": "0.00"}
    item = {"id": ITEM_ID, "name": "Замена масла", "status": "not_ready", "approved_by_client": True}

    await send_visit_card(message, visit, [item])

    assert "1. Замена масла — Не начата · без исполнителя" in message.answer.await_args.args[0]


async def test_start_reassign_lists_mechanics_and_remembers_item():
    callback = AsyncMock()
    callback.data = f"reassign:{encode_id(VISIT_ID)}:{encode_id(ITEM_ID)}"
    state = _fsm_context()
    api = AsyncMock()
    api.list_mechanics.return_value = [{"id": MECH_ID, "full_name": "Петров"}]

    await start_reassign_mechanic(callback, state, api=api, user=ADMIN)

    assert await state.get_data() == {"visit_id": VISIT_ID, "item_id": ITEM_ID}
    assert await state.get_state() == ReassignMechanicStates.choosing_mechanic.state
    buttons = _texts(callback.message.answer.await_args.kwargs["reply_markup"])
    assert buttons == [
        ("Петров", f"reassign_to:{encode_id(MECH_ID)}"),
        ("Без исполнителя", "reassign_to:none"),
    ]
    callback.answer.assert_awaited_once()


async def test_start_reassign_refuses_mechanic():
    callback = AsyncMock()
    callback.data = f"reassign:{encode_id(VISIT_ID)}:{encode_id(ITEM_ID)}"
    state = _fsm_context()
    api = AsyncMock()

    await start_reassign_mechanic(callback, state, api=api, user=MECHANIC)

    callback.answer.assert_awaited_once_with("Недостаточно прав")
    api.list_mechanics.assert_not_awaited()
    assert await state.get_state() is None


async def test_choose_new_mechanic_patches_and_refreshes_card():
    callback = AsyncMock()
    callback.data = f"reassign_to:{encode_id(MECH_ID)}"
    state = _fsm_context()
    await state.update_data(visit_id=VISIT_ID, item_id=ITEM_ID)
    await state.set_state(ReassignMechanicStates.choosing_mechanic)
    api = AsyncMock()
    api.get_visit.return_value = {"id": VISIT_ID, "status": "in_progress", "total_amount": "0.00"}
    api.list_work_items.return_value = []

    await choose_new_mechanic_callback(callback, state, api=api)

    api.assign_work_item_mechanic.assert_awaited_once_with(VISIT_ID, ITEM_ID, MECH_ID)
    api.get_visit.assert_awaited_once_with(VISIT_ID)
    assert await state.get_state() is None
    callback.answer.assert_awaited_once()


async def test_choose_none_unassigns():
    callback = AsyncMock()
    callback.data = "reassign_to:none"
    state = _fsm_context()
    await state.update_data(visit_id=VISIT_ID, item_id=ITEM_ID)
    await state.set_state(ReassignMechanicStates.choosing_mechanic)
    api = AsyncMock()
    api.get_visit.return_value = {"id": VISIT_ID, "status": "in_progress", "total_amount": "0.00"}
    api.list_work_items.return_value = []

    await choose_new_mechanic_callback(callback, state, api=api)

    api.assign_work_item_mechanic.assert_awaited_once_with(VISIT_ID, ITEM_ID, None)


@respx.mock
async def test_api_client_assign_work_item_mechanic_patches_endpoint():
    route = respx.patch(f"http://localhost:8000/visits/{VISIT_ID}/work-items/{ITEM_ID}/mechanic").mock(
        return_value=httpx.Response(200, json={"id": ITEM_ID})
    )

    await ApiClient().assign_work_item_mechanic(VISIT_ID, ITEM_ID, None)

    assert route.calls.last.request.content == b'{"assigned_mechanic_id":null}'
