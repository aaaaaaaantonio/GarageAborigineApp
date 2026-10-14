from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery

from bot import actions, nav
from bot.api_client import ApiClient, ApiError

router = Router()

PDF_PREPARING = "Готовлю заказ-наряд…"


@router.callback_query(F.data == actions.PDF)
async def pdf_callback(callback: CallbackQuery, state: FSMContext, api: ApiClient, **kwargs) -> None:
    """Send the work order as a separate document; the live card stays as it is."""
    args = await nav.top_args(callback, state, "visit")
    if args is None:
        return
    # Generation can outlast Telegram's callback timeout: stop the spinner first.
    await callback.answer(PDF_PREPARING)
    visit_id = args["visit_id"]
    try:
        result = await api.generate_document(visit_id)
        content = await api.get_document_file(result["document_id"])
    except ApiError as e:
        # The press is answered already, so the error middleware can't report it.
        await callback.message.answer(e.message)
        return
    await callback.message.answer_document(BufferedInputFile(content, filename=f"zakaz-naryad-{visit_id}.pdf"))
