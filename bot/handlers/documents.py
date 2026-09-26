from aiogram import F, Router
from aiogram.types import BufferedInputFile, CallbackQuery

from bot.api_client import ApiClient

router = Router()


@router.callback_query(F.data.startswith("gen_doc:"))
async def generate_document_callback(callback: CallbackQuery, api: ApiClient, **kwargs) -> None:
    _, visit_id = callback.data.split(":")
    result = await api.generate_document(visit_id)
    content = await api.get_document_file(result["document_id"])
    await callback.message.answer_document(BufferedInputFile(content, filename=f"zakaz-naryad-{visit_id}.pdf"))
    await callback.answer()
