from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
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
async def receive_search_query(message: Message, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    # For mechanics the API returns vehicles only (no client personal data).
    results = await api.search(message.text)
    if not results:
        if _is_mechanic(user):
            await message.answer("Ничего не найдено. Механик может искать машину по VIN или госномеру.")
        else:
            await message.answer("Ничего не найдено.")
        return
    # Page buttons re-run the search, so the query has to outlive this message.
    await state.update_data(search_query=message.text)
    text, markup = await _results_page(api, results, page=0)
    await message.answer(text, reply_markup=markup)


@router.callback_query(F.data.startswith("search_page:"))
async def search_page_callback(callback: CallbackQuery, state: FSMContext, api: ApiClient, **kwargs) -> None:
    query = (await state.get_data()).get("search_query")
    if query is None:
        await callback.answer("Поиск устарел — введите запрос заново.", show_alert=True)
        return
    results = await api.search(query)
    page = int(callback.data.split(":", 1)[1])
    text, markup = await _results_page(api, results, page)
    await callback.message.edit_text(text, reply_markup=markup)
    await callback.answer()


async def _results_page(api: ApiClient, results: list[dict], page: int) -> tuple[str, InlineKeyboardMarkup]:
    pages = max(1, -(-len(results) // SEARCH_RESULTS_LIMIT))
    page = min(max(page, 0), pages - 1)  # results may have shrunk since the button was drawn
    builder = InlineKeyboardBuilder()
    for r in results[page * SEARCH_RESULTS_LIMIT : (page + 1) * SEARCH_RESULTS_LIMIT]:
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
    if pages == 1:
        return f"Найдено: {len(results)}", builder.as_markup()

    arrows = []
    if page > 0:
        arrows.append(InlineKeyboardButton(text="‹ Назад", callback_data=f"search_page:{page - 1}"))
    if page < pages - 1:
        arrows.append(InlineKeyboardButton(text="Далее ›", callback_data=f"search_page:{page + 1}"))
    builder.row(*arrows)
    return f"Найдено: {len(results)} · стр. {page + 1}/{pages}\nМожно уточнить запрос.", builder.as_markup()
