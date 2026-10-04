"""Search: a prompt screen, and free text (outside wizards) as the query.

The query lives in the results screen's args, so paging needs no extra state.
"""
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot import actions, nav
from bot.api_client import ApiClient

router = Router()

SEARCH_RESULTS_LIMIT = 10


def _is_mechanic(user: dict) -> bool:
    return user["role"] == "mechanic"


@nav.screen("search")
async def render_search(api: ApiClient, user: dict, args: dict) -> nav.Rendered:
    text = "Введите VIN или гос.номер:" if _is_mechanic(user) else "Введите телефон, VIN, гос.номер или имя клиента:"
    return text, InlineKeyboardBuilder().as_markup()


@nav.screen("search_results")
async def render_search_results(api: ApiClient, user: dict, args: dict) -> nav.Rendered:
    # For mechanics the API returns vehicles only (no client personal data).
    results = await api.search(args["query"])
    builder = InlineKeyboardBuilder()
    if not results:
        if _is_mechanic(user):
            return "Ничего не найдено. Механик может искать машину по VIN или госномеру.", builder.as_markup()
        return "Ничего не найдено.", builder.as_markup()
    pages = -(-len(results) // SEARCH_RESULTS_LIMIT)
    page = min(max(args["page"], 0), pages - 1)  # results may have shrunk since the button was drawn
    for r in results[page * SEARCH_RESULTS_LIMIT : (page + 1) * SEARCH_RESULTS_LIMIT]:
        if r["entity"] == "client":
            client = await api.get_client(r["id"])
            builder.button(text=f"👤 {client['full_name']} — {client['phone_display']}", callback_data=nav.go_data("client", r["id"]))
        elif r["entity"] == "vehicle":
            vehicle = await api.get_vehicle(r["id"])
            builder.button(
                text=f"🚗 {vehicle['make']} {vehicle['model']} ({vehicle['plate_number']})",
                callback_data=nav.go_data("vehicle", r["id"]),
            )
    builder.adjust(1)
    if pages == 1:
        return f"Найдено: {len(results)}", builder.as_markup()
    arrows = []
    if page > 0:
        arrows.append(InlineKeyboardButton(text="‹ Пред.", callback_data=f"{actions.SEARCH_PAGE}:{page - 1}"))
    if page < pages - 1:
        arrows.append(InlineKeyboardButton(text="Далее ›", callback_data=f"{actions.SEARCH_PAGE}:{page + 1}"))
    builder.row(*arrows)
    return f"Найдено: {len(results)} · стр. {page + 1}/{pages}\nМожно уточнить запрос.", builder.as_markup()


@router.message(F.text)
async def receive_search_query(message: Message, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    await nav.push(message, state, api, user, "search_results", {"query": message.text, "page": 0})


@router.callback_query(F.data.startswith(f"{actions.SEARCH_PAGE}:"))
async def search_page_callback(callback: CallbackQuery, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    args = await nav.top_args(callback, state, "search_results")
    if args is None:
        return
    await nav.replace_top(callback, state, api, user, {**args, "page": int(callback.data.rsplit(":", 1)[1])})
