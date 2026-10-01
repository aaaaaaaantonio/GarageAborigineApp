from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.api_client import ApiClient

router = Router()


async def start_search(message: Message, state: FSMContext, **kwargs) -> None:
    """Menu entry point (registered in bot/handlers/menu.py)."""
    await state.clear()
    await message.answer("Введите телефон, VIN, гос.номер или имя клиента:")


@router.message(F.text)
async def receive_search_query(message: Message, api: ApiClient, **kwargs) -> None:
    results = await api.search(message.text)
    if not results:
        await message.answer("Ничего не найдено.")
        return
    lines = []
    for r in results:
        if r["entity"] == "client":
            client = await api.get_client(r["id"])
            lines.append(f"{client['full_name']} — {client['phone_display']}")
        elif r["entity"] == "vehicle":
            vehicle = await api.get_vehicle(r["id"])
            lines.append(f"{vehicle['make']} {vehicle['model']} ({vehicle['plate_number']})")
    await message.answer("\n".join(lines) or "Ничего не найдено.")
