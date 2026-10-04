from app.core.enums import UserRole
from bot.keyboards import main_menu


def _texts(role):
    return [button.text for row in main_menu(role).keyboard for button in row]


def test_mechanic_menu_has_my_work_items_and_search():
    assert _texts(UserRole.MECHANIC) == ["Мои работы", "Поиск"]


def test_master_menu():
    assert _texts(UserRole.MASTER) == ["Новый заезд", "Заезды в работе", "Поиск", "Регистрация клиента (бумага)"]


def test_admin_menu_has_everything_master_has_plus_add_staff():
    assert _texts(UserRole.ADMIN) == [
        "Новый заезд", "Заезды в работе", "Поиск", "Регистрация клиента (бумага)", "Добавить сотрудника",
    ]
