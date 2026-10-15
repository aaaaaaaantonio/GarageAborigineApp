from unittest.mock import AsyncMock

from bot.handlers.mechanic import render_mech_visit
from tests.bot.helpers import MECHANIC

VISIT = "11111111-1111-1111-1111-111111111111"
PART = {"name": "Фильтр", "article_number": None, "quantity": 1, "availability_status": "in_stock", "unit_price": None, "amount": None}


def _view(**over):
    base = {
        "id": VISIT, "status": "in_progress", "created_at": "2026-10-10T09:00:00+00:00", "mileage_at_intake": 120000,
        "plate_number": "А123ВС77", "make_model": "Toyota Camry", "master_name": "Орлов",
        "client_name": None, "client_phone": None, "client_telegram_username": None, "vin": None,
        "discount": None, "total_amount": None, "my_pay_total": None,
        "works": [
            {"id": "w1", "name": "Масло", "category": "maintenance", "status": "in_progress", "mechanic_name": "Сидоров",
             "is_mine": True, "norm_hours": 2, "hourly_rate": None, "amount": None, "my_pay": None, "parts": [PART]},
            {"id": "w2", "name": "Мойка", "category": "other", "status": "not_ready", "mechanic_name": None,
             "is_mine": False, "norm_hours": 0.5, "hourly_rate": None, "amount": None, "my_pay": None, "parts": []},
        ],
    }
    return base | over


async def test_card_without_prices():
    api = AsyncMock()
    api.get_mechanic_view.return_value = _view()

    text, _ = await render_mech_visit(api, MECHANIC, {"visit_id": VISIT})

    api.get_mechanic_view.assert_awaited_once_with(VISIT)
    assert text.splitlines()[:2] == ["🚗 А123ВС77 · Toyota Camry", "Пробег: 120 000 км · Мастер: Орлов"]
    assert "Масло · моя" in text and "без исполнителя" in text and "🔩 Фильтр × 1" in text
    assert "₽" not in text and "Клиент" not in text


async def test_card_with_prices_client_and_no_scheme():
    api = AsyncMock()
    view = _view(client_name="Петров", client_phone="+7 900 123-45-67", client_telegram_username="petrov_ivan", vin="X" * 17,
                 discount=0, total_amount=3450, my_pay_total=None)
    view["works"][0] |= {"hourly_rate": 1000, "amount": 2000, "my_pay": None,
                         "parts": [PART | {"unit_price": 450, "amount": 450}]}
    api.get_mechanic_view.return_value = view

    text, _ = await render_mech_visit(api, MECHANIC, {"visit_id": VISIT})

    assert "Клиент: Петров" in text and "Телефон: +7 900 123-45-67" in text and f"VIN: {'X' * 17}" in text
    assert "Telegram: @petrov_ivan" in text
    assert "2 000 ₽" in text and "🔩 Фильтр × 1 · 450 ₽" in text
    assert "Итого по заезду: 3 450 ₽" in text
    assert "Ваш заработок по заезду: схема оплаты не задана" in text


async def test_card_with_own_pay():
    api = AsyncMock()
    view = _view(discount=0, total_amount=3450, my_pay_total=1000)
    view["works"][0] |= {"hourly_rate": 1000, "amount": 2000, "my_pay": 1000}
    api.get_mechanic_view.return_value = view

    text, _ = await render_mech_visit(api, MECHANIC, {"visit_id": VISIT})

    assert "Ваш заработок: 1 000 ₽" in text and "Ваш заработок по заезду: 1 000 ₽" in text


async def test_card_shows_kopecks_like_the_web():
    api = AsyncMock()
    view = _view(discount=0, total_amount=1000.5, my_pay_total=1543.13)
    view["works"][0] |= {"hourly_rate": 1000, "amount": 1000.5, "my_pay": 1543.13}
    api.get_mechanic_view.return_value = view

    text, _ = await render_mech_visit(api, MECHANIC, {"visit_id": VISIT})

    assert "Итого по заезду: 1 000,50 ₽" in text and "Ваш заработок: 1 543,13 ₽" in text


async def test_long_card_stays_under_the_telegram_limit():
    api = AsyncMock()
    works = [
        {"id": f"w{i}", "name": f"Работа номер {i} " + "х" * 40, "category": "other", "status": "not_ready",
         "mechanic_name": "Сидоров", "is_mine": True, "norm_hours": 1, "hourly_rate": None, "amount": None,
         "my_pay": None, "parts": [PART | {"name": "Деталь " + "д" * 30} for _ in range(5)]}
        for i in range(60)
    ]
    api.get_mechanic_view.return_value = _view(works=works)

    text, _ = await render_mech_visit(api, MECHANIC, {"visit_id": VISIT})

    assert len(text) <= 4096
    assert "показаны не все работы — откройте карточку в веб-приложении" in text
    assert "Работа номер 0" in text and "Работа номер 59" not in text
