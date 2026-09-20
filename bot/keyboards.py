from aiogram.types import ReplyKeyboardMarkup
from aiogram.utils.keyboard import ReplyKeyboardBuilder

from app.core.enums import UserRole

STAFF_BUTTONS = ["Новый заезд", "Поиск", "Регистрация клиента (бумага)"]
ADMIN_ONLY_BUTTONS = ["Добавить сотрудника"]
MECHANIC_BUTTONS = ["Мои работы"]


def main_menu(role: UserRole) -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    if role == UserRole.MECHANIC:
        buttons = MECHANIC_BUTTONS
    else:
        buttons = list(STAFF_BUTTONS)
        if role == UserRole.ADMIN:
            buttons += ADMIN_ONLY_BUTTONS
    for text in buttons:
        builder.button(text=text)
    builder.adjust(1)
    return builder.as_markup(resize_keyboard=True)
