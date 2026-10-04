from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.api_client import ApiClient
from bot.callback_ids import encode_id

router = Router()

SEARCH_RESULTS_LIMIT = 10


def _is_mechanic(user: dict) -> bool:
    return user["role"] == "mechanic"


async def start_search(message: Message, state: FSMContext, user: dict, **kwargs) -> None:
    """Menu entry point (registered in bot/handlers/menu.py)."""
    await state.clear()
    if _is_mechanic(user):
        await message.answer("Введите VIN или гос.номер:")
    else:
        await message.answer("Введите телефон, VIN, гос.номер или имя клиента:")


@router.message(F.text)
async def receive_search_query(message: Message, api: ApiClient, user: dict, **kwargs) -> None:
    # For mechanics the API returns vehicles only (no client personal data).
    results = await api.search(message.text)
    if not results:
        if _is_mechanic(user):
            await message.answer("Ничего не найдено. Механик может искать машину по VIN или госномеру.")
        else:
            await message.answer("Ничего не найдено.")
        return
    builder = InlineKeyboardBuilder()
    for r in results[:SEARCH_RESULTS_LIMIT]:
        if r["entity"] == "client":
            client = await api.get_client(r["id"])
            builder.button(
                text=f"👤 {client['full_name']} — {client['phone_display']}",
                callback_data=f"client_open:{encode_id(r['id'])}",
            )
        elif r["entity"] == "vehicle":
            vehicle = await api.get_vehicle(r["id"])
            builder.button(
                text=f"🚗 {vehicle['make']} {vehicle['model']} ({vehicle['plate_number']})",
                callback_data=f"vehicle_open:{encode_id(r['id'])}",
            )
    builder.adjust(1)
    text = f"Найдено: {len(results)}"
    if len(results) > SEARCH_RESULTS_LIMIT:
        text += f"\nПоказаны первые {SEARCH_RESULTS_LIMIT} — уточните запрос."
    await message.answer(text, reply_markup=builder.as_markup())
