from unittest.mock import AsyncMock

from aiogram.types import BufferedInputFile

from bot.handlers.documents import generate_document_callback


async def test_generate_document_callback_sends_pdf_file():
    callback = AsyncMock()
    callback.data = "gen_doc:visit1"
    api = AsyncMock()
    api.generate_document.return_value = {"document_id": "visit1", "document_url": "/storage/visits/visit1.pdf"}
    api.get_document_file.return_value = b"%PDF-1.7"

    await generate_document_callback(callback, api=api)

    api.generate_document.assert_awaited_once_with("visit1")
    api.get_document_file.assert_awaited_once_with("visit1")
    callback.message.answer_document.assert_awaited_once()
    sent = callback.message.answer_document.await_args.args[0]
    assert isinstance(sent, BufferedInputFile)
    assert sent.data == b"%PDF-1.7"
    assert sent.filename.endswith(".pdf")
    callback.message.answer.assert_not_awaited()
    callback.answer.assert_awaited_once()
