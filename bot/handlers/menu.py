"""The menu screen (bottom of the screen stack) and a temporary handler for
texts of the removed reply keyboard."""
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, ReplyKeyboardRemove
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot import actions, nav
from bot.api_client import ApiClient

router = Router()

_MASTER_ITEMS = [
    ("🆕 Новый заезд", actions.NEW_VISIT),
    ("🔧 Заезды в работе", nav.go_data("active_visits")),
    ("🔍 Поиск", nav.go_data("search")),
    ("📝 Регистрация клиента (бумага)", actions.PAPER_CONSENT),
]
_ADMIN_ITEMS = _MASTER_ITEMS + [("👥 Добавить сотрудника", actions.NEW_STAFF)]
_MECHANIC_ITEMS = [("🧰 Мои работы", nav.go_data("my_works")), ("🔍 Поиск", nav.go_data("search"))]


@nav.screen(nav.MENU)
async def render_menu(api: ApiClient, user: dict, args: dict) -> nav.Rendered:
    items = {"admin": _ADMIN_ITEMS, "mechanic": _MECHANIC_ITEMS}.get(user["role"], _MASTER_ITEMS)
    builder = InlineKeyboardBuilder()
    for text, data in items:
        builder.button(text=text, callback_data=data)
    builder.adjust(1)
    return "Главное меню", builder.as_markup()


# Users who still have the old reply keyboard send its button texts as plain
# messages; without this they would turn into search queries.
# TODO(2026-10-25): delete with the rollout grace period over.
LEGACY_MENU_TEXTS = {
    "Новый заезд", "Заезды в работе", "Поиск", "Регистрация клиента (бумага)", "Добавить сотрудника", "Мои работы",
}
KEYBOARD_REMOVED = "Меню теперь в кнопках под сообщением."


@router.message(F.text.in_(LEGACY_MENU_TEXTS))
async def legacy_menu_text(message: Message, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    await nav.clear_wizard(state)
    await message.answer(KEYBOARD_REMOVED, reply_markup=ReplyKeyboardRemove())
    await nav.home(message, state, api, user)
