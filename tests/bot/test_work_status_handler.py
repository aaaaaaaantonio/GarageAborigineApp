from unittest.mock import AsyncMock

from bot.callback_ids import encode_id
from bot.handlers.work_status import change_work_status_callback

VISIT_ID = "11111111-1111-1111-1111-111111111111"
ITEM_ID = "22222222-2222-2222-2222-222222222222"


async def test_card_origin_updates_status_with_real_visit_id_and_refreshes_card():
    callback = AsyncMock()
    callback.data = f"wsc:{encode_id(VISIT_ID)}:{encode_id(ITEM_ID)}:ready"
    api = AsyncMock()
    api.update_work_item_status.return_value = {"id": ITEM_ID, "name": "Замена масла", "status": "ready"}
    api.get_visit.return_value = {"id": VISIT_ID, "status": "in_progress", "total_amount": "0.00"}
    api.list_work_items.return_value = []

    await change_work_status_callback(callback, api=api)

    api.update_work_item_status.assert_awaited_once_with(VISIT_ID, ITEM_ID, "ready")
    api.get_visit.assert_awaited_once_with(VISIT_ID)
    api.list_work_items.assert_awaited_once_with(VISIT_ID)
    callback.answer.assert_awaited_once()


async def test_mechanic_origin_updates_status_and_confirms_without_loading_visit():
    callback = AsyncMock()
    callback.data = f"wsm:{encode_id(VISIT_ID)}:{encode_id(ITEM_ID)}:in_progress"
    api = AsyncMock()
    api.update_work_item_status.return_value = {"id": ITEM_ID, "name": "Замена масла", "status": "in_progress"}

    await change_work_status_callback(callback, api=api)

    api.update_work_item_status.assert_awaited_once_with(VISIT_ID, ITEM_ID, "in_progress")
    api.get_visit.assert_not_awaited()
    assert "Замена масла" in callback.message.answer.await_args.args[0]
    callback.answer.assert_awaited_once()
