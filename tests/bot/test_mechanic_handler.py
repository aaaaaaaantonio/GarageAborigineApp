from unittest.mock import AsyncMock

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from bot.handlers.mechanic import change_work_status_callback, show_my_work_items


def _fsm_context() -> FSMContext:
    return FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=1, user_id=1))


async def test_show_my_work_items_handles_empty_list():
    message = AsyncMock()
    api = AsyncMock()
    api.list_my_work_items.return_value = []

    await show_my_work_items(message, _fsm_context(), api=api)

    message.answer.assert_awaited_once_with("У вас нет назначенных работ.")


async def test_show_my_work_items_sends_status_button_per_item():
    message = AsyncMock()
    api = AsyncMock()
    api.list_my_work_items.return_value = [
        {"id": "wi1", "visit_id": "visit1", "status": "not_ready", "free_text_name": "Замена масла", "catalog_item_id": None}
    ]

    await show_my_work_items(message, _fsm_context(), api=api)

    message.answer.assert_awaited_once()
    args, kwargs = message.answer.await_args
    assert "Замена масла" in args[0]
    assert kwargs["reply_markup"] is not None


async def test_show_my_work_items_omits_button_when_no_next_status():
    message = AsyncMock()
    api = AsyncMock()
    api.list_my_work_items.return_value = [
        {"id": "wi1", "visit_id": "visit1", "status": "ready", "free_text_name": "Замена масла", "catalog_item_id": None}
    ]

    await show_my_work_items(message, _fsm_context(), api=api)

    _, kwargs = message.answer.await_args
    assert kwargs["reply_markup"] is None


async def test_change_work_status_callback_updates_status():
    callback = AsyncMock()
    callback.data = "work_status:wi1:in_progress"
    api = AsyncMock()
    api.update_work_item_status.return_value = {"id": "wi1", "status": "in_progress"}

    await change_work_status_callback(callback, api=api)

    api.update_work_item_status.assert_awaited_once_with("wi1", "wi1", "in_progress")
    callback.message.answer.assert_awaited_once()
    callback.answer.assert_awaited_once()


async def test_show_my_work_items_callback_data_fits_telegram_limit():
    message = AsyncMock()
    api = AsyncMock()
    api.list_my_work_items.return_value = [
        {
            "id": "22222222-2222-2222-2222-222222222222",
            "visit_id": "11111111-1111-1111-1111-111111111111",
            "status": "not_ready",
            "free_text_name": "Замена масла",
            "catalog_item_id": None,
        }
    ]

    await show_my_work_items(message, _fsm_context(), api=api)

    _, kwargs = message.answer.await_args
    markup = kwargs["reply_markup"]
    assert all(len(b.callback_data.encode()) <= 64 for row in markup.inline_keyboard for b in row)


async def test_show_my_work_items_numbers_catalog_items_without_free_text_name():
    message = AsyncMock()
    api = AsyncMock()
    api.list_my_work_items.return_value = [
        {
            "id": "22222222-2222-2222-2222-222222222222",
            "visit_id": "11111111-1111-1111-1111-111111111111",
            "status": "not_ready",
            "free_text_name": None,
            "catalog_item_id": "33333333-3333-3333-3333-333333333333",
        }
    ]

    await show_my_work_items(message, _fsm_context(), api=api)

    args, _ = message.answer.await_args
    assert args[0].startswith("работа №1 —")
