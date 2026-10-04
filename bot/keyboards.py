from aiogram.types import ReplyKeyboardMarkup
from aiogram.utils.keyboard import ReplyKeyboardBuilder

from app.core.enums import UserRole

NEW_VISIT = "Новый заезд"
ACTIVE_VISITS = "Заезды в работе"
SEARCH = "Поиск"
PAPER_CONSENT = "Регистрация клиента (бумага)"
ADD_STAFF = "Добавить сотрудника"
MY_WORK_ITEMS = "Мои работы"

MASTER_BUTTONS = [NEW_VISIT, ACTIVE_VISITS, SEARCH, PAPER_CONSENT]
ADMIN_BUTTONS = MASTER_BUTTONS + [ADD_STAFF]
MECHANIC_BUTTONS = [MY_WORK_ITEMS, SEARCH]
ALL_MENU_BUTTONS = ADMIN_BUTTONS + [MY_WORK_ITEMS]


def main_menu(role: UserRole) -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    if role == UserRole.MECHANIC:
        buttons = MECHANIC_BUTTONS
    elif role == UserRole.ADMIN:
        buttons = ADMIN_BUTTONS
    else:
        buttons = MASTER_BUTTONS
    for text in buttons:
        builder.button(text=text)
    builder.adjust(1)
    return builder.as_markup(resize_keyboard=True)
