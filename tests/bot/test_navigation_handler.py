from unittest.mock import AsyncMock

from bot.callback_ids import encode_id
from bot.handlers.navigation import (
    render_active_visits,
    render_client,
    render_client_visits,
    render_vehicle,
    render_vehicle_visits,
    render_work_history,
)
from tests.bot.helpers import ADMIN, MASTER, MECHANIC, buttons

ME = MASTER["id"]
OTHER = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
V1 = "11111111-1111-1111-1111-111111111111"
V2 = "22222222-2222-2222-2222-222222222222"
C1 = "33333333-3333-3333-3333-333333333333"
CAR = "44444444-4444-4444-4444-444444444444"


def _visit(visit_id, master_id, status="in_progress", plate="А123ВС77", client="Иванов Пётр"):
    return {
        "id": visit_id, "status": status, "plate_number": plate, "client_name": client,
        "assigned_master_id": master_id, "created_at": "2026-10-02T07:00:00+00:00",
    }


async def test_active_visits_marks_own_with_star_and_opens_card():
    api = AsyncMock()
    api.list_visits.return_value = {
        "items": [_visit(V1, ME), _visit(V2, OTHER, status="diagnostics", plate="В001ОР50", client="Петрова")],
        "has_more": False,
    }

    text, markup = await render_active_visits(api, MASTER, {})

    api.list_visits.assert_awaited_once_with(active=True)
    assert text == "Заезды в работе (2)"
    assert buttons(markup) == [
        ("⭐ А123ВС77 · Иванов Пётр · Ремонт", f"go:visit:{encode_id(V1)}"),
        ("В001ОР50 · Петрова · Диагностика", f"go:visit:{encode_id(V2)}"),
    ]


async def test_active_visits_admin_sees_no_stars():
    api = AsyncMock()
    api.list_visits.return_value = {"items": [_visit(V1, OTHER)], "has_more": False}

    _, markup = await render_active_visits(api, ADMIN, {})

    assert not buttons(markup)[0][0].startswith("⭐")


async def test_active_visits_empty():
    api = AsyncMock()
    api.list_visits.return_value = {"items": [], "has_more": False}

    text, markup = await render_active_visits(api, MASTER, {})

    assert text == "Незакрытых заездов нет."
    assert buttons(markup) == []


async def test_active_visits_warns_when_truncated():
    api = AsyncMock()
    api.list_visits.return_value = {"items": [_visit(V1, ME)], "has_more": True}

    text, _ = await render_active_visits(api, MASTER, {})

    assert text == "Заезды в работе (1)\nПоказаны последние 30."


async def test_client_card_lists_vehicles_and_visits_button():
    api = AsyncMock()
    api.get_client.return_value = {"id": C1, "full_name": "Иван Иванов", "phone_display": "+7 999 123-45-67"}
    api.list_client_vehicles.return_value = [{"id": CAR, "make": "Toyota", "model": "Camry", "plate_number": "А123ВС77"}]

    text, markup = await render_client(api, MASTER, {"client_id": C1})

    assert text == "👤 Иван Иванов\n+7 999 123-45-67"
    assert buttons(markup) == [
        ("🚗 Toyota Camry (А123ВС77)", f"go:vehicle:{encode_id(CAR)}"),
        ("📋 Заезды клиента", f"go:client_visits:{encode_id(C1)}"),
    ]


def _car():
    return {"id": CAR, "make": "Toyota", "model": "Camry", "plate_number": "А123ВС77", "vin": "X" * 17, "mileage_current": 120500}


async def test_vehicle_card_for_master_has_owner_visits_new_visit_and_history():
    api = AsyncMock()
    api.get_vehicle.return_value = _car()
    api.get_vehicle_owner.return_value = {"id": C1, "full_name": "Иван Иванов"}

    text, markup = await render_vehicle(api, MASTER, {"vehicle_id": CAR})

    assert text == f"🚗 Toyota Camry · А123ВС77\nVIN: {'X' * 17} · Пробег: 120 500 км"
    assert buttons(markup) == [
        ("👤 Владелец: Иван Иванов", f"go:client:{encode_id(C1)}"),
        ("📋 Заезды по машине", f"go:vehicle_visits:{encode_id(CAR)}"),
        ("➕ Новый заезд", "act:new_visit_for"),
        ("🔧 История работ", f"go:work_history:{encode_id(CAR)}"),
    ]


async def test_vehicle_card_without_owner_hides_owner_and_new_visit():
    api = AsyncMock()
    api.get_vehicle.return_value = _car()
    api.get_vehicle_owner.return_value = None

    _, markup = await render_vehicle(api, MASTER, {"vehicle_id": CAR})

    assert [t for t, _ in buttons(markup)] == ["📋 Заезды по машине", "🔧 История работ"]


async def test_vehicle_card_for_mechanic_has_only_history_and_never_asks_owner():
    api = AsyncMock()
    api.get_vehicle.return_value = _car()

    _, markup = await render_vehicle(api, MECHANIC, {"vehicle_id": CAR})

    assert [t for t, _ in buttons(markup)] == ["🔧 История работ"]
    api.get_vehicle_owner.assert_not_awaited()


async def test_client_and_vehicle_visits_are_dated_lists():
    api = AsyncMock()
    api.list_visits.return_value = {"items": [_visit(V1, ME, status="issued")], "has_more": False}

    text, markup = await render_client_visits(api, MASTER, {"client_id": C1})
    api.list_visits.assert_awaited_with(client_id=C1)
    assert text == "Заезды (1)"
    assert buttons(markup) == [("⭐ 02.10 · А123ВС77 · Выдан", f"go:visit:{encode_id(V1)}")]

    await render_vehicle_visits(api, MASTER, {"vehicle_id": CAR})
    api.list_visits.assert_awaited_with(vehicle_id=CAR)


async def test_visits_history_empty():
    api = AsyncMock()
    api.list_visits.return_value = {"items": [], "has_more": False}

    text, _ = await render_client_visits(api, MASTER, {"client_id": C1})

    assert text == "Заездов ещё не было."


async def test_work_history_groups_by_visit():
    api = AsyncMock()
    api.get_vehicle.return_value = _car()
    api.get_vehicle_work_history.return_value = {
        "items": [
            {"visit_id": V1, "visit_at": "2026-10-02T07:00:00+00:00", "mileage": 120000, "name": "Замена масла", "status": "ready"},
            {"visit_id": V1, "visit_at": "2026-10-02T07:00:00+00:00", "mileage": 120000, "name": "Фильтр", "status": "in_progress"},
        ],
        "has_more": False,
    }

    text, markup = await render_work_history(api, MECHANIC, {"vehicle_id": CAR})

    assert text == "🔧 История работ · А123ВС77\n02.10.2026 · 120 000 км\n  • Замена масла — Готово\n  • Фильтр — В работе"
    assert buttons(markup) == []


async def test_work_history_empty_and_truncated():
    api = AsyncMock()
    api.get_vehicle.return_value = _car()
    api.get_vehicle_work_history.return_value = {"items": [], "has_more": False}
    assert (await render_work_history(api, MASTER, {"vehicle_id": CAR}))[0] == "Работ по машине ещё не было."

    api.get_vehicle_work_history.return_value = {
        "items": [{"visit_id": V1, "visit_at": "2026-10-02T07:00:00+00:00", "mileage": 1, "name": "X", "status": "ready"}],
        "has_more": True,
    }
    assert (await render_work_history(api, MASTER, {"vehicle_id": CAR}))[0].endswith("Показаны последние 30 работ.")
