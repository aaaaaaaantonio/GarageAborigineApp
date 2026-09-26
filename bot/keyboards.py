from aiogram.types import ReplyKeyboardMarkup
from aiogram.utils.keyboard import ReplyKeyboardBuilder

from app.core.enums import UserRole

NEW_VISIT = "Новый заезд"
SEARCH = "Поиск"
PAPER_CONSENT = "Регистрация клиента (бумага)"
ADD_STAFF = "Добавить сотрудника"
MY_WORK_ITEMS = "Мои работы"

# A visit's assigned master must have role MASTER (backend rule), and an ADMIN
# has no UI to choose one, so "Новый заезд" is offered to masters only.
MASTER_ONLY_BUTTONS = [NEW_VISIT]
SHARED_STAFF_BUTTONS = [SEARCH, PAPER_CONSENT]
ADMIN_ONLY_BUTTONS = [ADD_STAFF]
MECHANIC_BUTTONS = [MY_WORK_ITEMS]
ALL_MENU_BUTTONS = MASTER_ONLY_BUTTONS + SHARED_STAFF_BUTTONS + ADMIN_ONLY_BUTTONS + MECHANIC_BUTTONS


def main_menu(role: UserRole) -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    if role == UserRole.MECHANIC:
        buttons = MECHANIC_BUTTONS
    elif role == UserRole.ADMIN:
        buttons = SHARED_STAFF_BUTTONS + ADMIN_ONLY_BUTTONS
    else:
        buttons = MASTER_ONLY_BUTTONS + SHARED_STAFF_BUTTONS
    for text in buttons:
        builder.button(text=text)
    builder.adjust(1)
    return builder.as_markup(resize_keyboard=True)
