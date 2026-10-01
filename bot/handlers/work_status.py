from aiogram import F, Router
from aiogram.types import CallbackQuery

from bot.api_client import ApiClient
from bot.callback_ids import decode_id
from bot.handlers.visits import refresh_visit_card
from bot.work_item_status import FROM_MY_WORK_ITEMS, FROM_VISIT_CARD

router = Router()


@router.callback_query(F.data.startswith(f"{FROM_VISIT_CARD}:") | F.data.startswith(f"{FROM_MY_WORK_ITEMS}:"))
async def change_work_status_callback(callback: CallbackQuery, api: ApiClient, **kwargs) -> None:
    origin, visit_b64, item_b64, new_status = callback.data.split(":")
    visit_id = decode_id(visit_b64)
    item = await api.update_work_item_status(visit_id, decode_id(item_b64), new_status)
    if origin == FROM_VISIT_CARD:
        await refresh_visit_card(callback.message, api, visit_id)
    else:
        await callback.message.answer(f"Статус обновлён: {item['name']} — {item['status']}")
    await callback.answer()
