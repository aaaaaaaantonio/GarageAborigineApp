from unittest.mock import AsyncMock

from bot.handlers.mechanic import change_work_status_callback, show_my_work_items


async def test_show_my_work_items_handles_empty_list():
    message = AsyncMock()
    api = AsyncMock()
    api.list_my_work_items.return_value = []

    await show_my_work_items(message, api=api)

    message.answer.assert_awaited_once_with("У вас нет назначенных работ.")


async def test_show_my_work_items_sends_status_button_per_item():
    message = AsyncMock()
    api = AsyncMock()
    api.list_my_work_items.return_value = [
        {"id": "wi1", "visit_id": "visit1", "status": "not_ready", "free_text_name": "Замена масла", "catalog_item_id": None}
    ]

    await show_my_work_items(message, api=api)

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

    await show_my_work_items(message, api=api)

    _, kwargs = message.answer.await_args
    assert kwargs["reply_markup"] is None


async def test_change_work_status_callback_updates_status():
    callback = AsyncMock()
    callback.data = "work_status:visit1:wi1:in_progress"
    api = AsyncMock()
    api.update_work_item_status.return_value = {"id": "wi1", "status": "in_progress"}

    await change_work_status_callback(callback, api=api)

    api.update_work_item_status.assert_awaited_once_with("visit1", "wi1", "in_progress")
    callback.message.answer.assert_awaited_once()
    callback.answer.assert_awaited_once()
