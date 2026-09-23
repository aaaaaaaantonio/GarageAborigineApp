from aiogram import Router
from aiogram.types import CallbackQuery

from bot.api_client import ApiClient

router = Router()


@router.callback_query(lambda c: c.data.startswith("gen_doc:"))
async def generate_document_callback(callback: CallbackQuery, api: ApiClient, **kwargs) -> None:
    _, visit_id = callback.data.split(":")
    result = await api.generate_document(visit_id)
    await callback.message.answer(f"Документ готов: {result['document_url']}")
    await callback.answer()
