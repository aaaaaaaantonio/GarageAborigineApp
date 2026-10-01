from aiogram import Router
from aiogram.types import CallbackQuery

from bot.texts import STALE_BUTTON

router = Router()


@router.callback_query()
async def stale_callback(callback: CallbackQuery, **kwargs) -> None:
    """Any callback no other handler accepted — typically a wizard button
    pressed after its FSM step is over. Answer it so the spinner stops."""
    await callback.answer(STALE_BUTTON)
