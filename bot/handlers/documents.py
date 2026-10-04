from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery

from bot import actions, nav
from bot.api_client import ApiClient

router = Router()


@router.callback_query(F.data == actions.PDF)
async def pdf_callback(callback: CallbackQuery, state: FSMContext, api: ApiClient, **kwargs) -> None:
    """Send the work order as a separate document; the live card stays as it is."""
    args = await nav.top_args(callback, state, "visit")
    if args is None:
        return
    visit_id = args["visit_id"]
    result = await api.generate_document(visit_id)
    content = await api.get_document_file(result["document_id"])
    await callback.message.answer_document(BufferedInputFile(content, filename=f"zakaz-naryad-{visit_id}.pdf"))
    await callback.answer()
