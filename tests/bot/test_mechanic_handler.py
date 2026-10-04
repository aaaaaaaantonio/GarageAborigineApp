from unittest.mock import AsyncMock

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from bot.callback_ids import encode_id
from bot.handlers.mechanic import show_my_work_items

VISIT_ID = "11111111-1111-1111-1111-111111111111"
ITEM_ID = "22222222-2222-2222-2222-222222222222"


def _fsm_context() -> FSMContext:
    return FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=1, user_id=1))


def _item(status: str, name: str = "Замена масла") -> dict:
    return {"id": ITEM_ID, "visit_id": VISIT_ID, "status": status, "name": name,
            "free_text_name": None, "catalog_item_id": None}


async def test_show_my_work_items_handles_empty_list():
    message = AsyncMock()
    api = AsyncMock()
    api.list_my_work_items.return_value = []

    await show_my_work_items(message, _fsm_context(), api=api)

    message.answer.assert_awaited_once_with("У вас нет назначенных работ.")


async def test_show_my_work_items_uses_resolved_name_and_real_visit_id():
    message = AsyncMock()
    api = AsyncMock()
    api.list_my_work_items.return_value = [_item("not_ready", name="Диагностика ходовой")]

    await show_my_work_items(message, _fsm_context(), api=api)

    args, kwargs = message.answer.await_args
    assert args[0].startswith("Диагностика ходовой —")
    buttons = [b for row in kwargs["reply_markup"].inline_keyboard for b in row]
    assert [b.callback_data for b in buttons] == [f"wsm:{encode_id(VISIT_ID)}:{encode_id(ITEM_ID)}:in_progress"]


async def test_show_my_work_items_offers_waiting_parts_and_ready_from_in_progress():
    message = AsyncMock()
    api = AsyncMock()
    api.list_my_work_items.return_value = [_item("in_progress")]

    await show_my_work_items(message, _fsm_context(), api=api)

    _, kwargs = message.answer.await_args
    data = [b.callback_data for row in kwargs["reply_markup"].inline_keyboard for b in row]
    assert [d.rsplit(":", 1)[1] for d in data] == ["waiting_parts", "ready"]
    assert all(len(d.encode()) <= 64 for d in data)


async def test_show_my_work_items_omits_button_when_no_next_status():
    message = AsyncMock()
    api = AsyncMock()
    api.list_my_work_items.return_value = [_item("ready")]

    await show_my_work_items(message, _fsm_context(), api=api)

    _, kwargs = message.answer.await_args
    assert kwargs["reply_markup"] is None


async def test_show_my_work_items_shows_russian_status():
    message = AsyncMock()
    api = AsyncMock()
    api.list_my_work_items.return_value = [_item("waiting_parts")]

    await show_my_work_items(message, _fsm_context(), api=api)

    assert "Ждёт запчасти" in message.answer.await_args.args[0]
