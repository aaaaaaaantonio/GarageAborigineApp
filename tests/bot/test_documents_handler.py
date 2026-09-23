from unittest.mock import AsyncMock

from bot.handlers.documents import generate_document_callback


async def test_generate_document_callback_sends_url():
    callback = AsyncMock()
    callback.data = "gen_doc:visit1"
    api = AsyncMock()
    api.generate_document.return_value = {"document_url": "/storage/visits/visit1.pdf"}

    await generate_document_callback(callback, api=api)

    api.generate_document.assert_awaited_once_with("visit1")
    callback.message.answer.assert_awaited_once()
    callback.answer.assert_awaited_once()
