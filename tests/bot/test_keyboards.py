from app.core.enums import UserRole
from bot.keyboards import main_menu


def test_mechanic_menu_has_only_my_work_items_button():
    markup = main_menu(UserRole.MECHANIC)
    texts = [button.text for row in markup.keyboard for button in row]
    assert texts == ["Мои работы"]


def test_master_menu_has_full_staff_buttons_but_not_admin_only():
    markup = main_menu(UserRole.MASTER)
    texts = [button.text for row in markup.keyboard for button in row]
    assert "Новый заезд" in texts
    assert "Поиск" in texts
    assert "Добавить сотрудника" not in texts


def test_admin_menu_includes_add_staff_button():
    markup = main_menu(UserRole.ADMIN)
    texts = [button.text for row in markup.keyboard for button in row]
    assert "Добавить сотрудника" in texts


def test_admin_menu_hides_new_visit_button():
    markup = main_menu(UserRole.ADMIN)
    texts = [button.text for row in markup.keyboard for button in row]
    assert "Новый заезд" not in texts
    assert "Поиск" in texts
    assert "Регистрация клиента (бумага)" in texts
