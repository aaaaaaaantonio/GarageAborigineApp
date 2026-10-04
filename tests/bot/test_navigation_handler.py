from unittest.mock import AsyncMock

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from bot.callback_ids import encode_id
from bot.handlers.navigation import (
    client_open_callback,
    open_visit_callback,
    show_active_visits,
    vehicle_open_callback,
    visits_by_client_callback,
    visits_by_vehicle_callback,
    work_history_callback,
)

ME = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
OTHER = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
V1 = "11111111-1111-1111-1111-111111111111"
V2 = "22222222-2222-2222-2222-222222222222"


def _fsm_context() -> FSMContext:
    return FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=1, user_id=1))


def _visit(visit_id, master_id, status="in_progress", plate="А123ВС77", client="Иванов Пётр"):
    return {
        "id": visit_id, "status": status, "plate_number": plate, "client_name": client,
        "assigned_master_id": master_id, "created_at": "2026-10-02T07:00:00+00:00",
        "make_model": "Toyota Camry", "master_name": "Мастер", "total_amount": 0,
    }


def _buttons(message):
    markup = message.answer.await_args.kwargs["reply_markup"]
    return [(b.text, b.callback_data) for row in markup.inline_keyboard for b in row]


async def test_active_visits_marks_own_with_star_and_links_to_card():
    message = AsyncMock()
    api = AsyncMock()
    api.list_visits.return_value = {
        "items": [_visit(V1, ME), _visit(V2, OTHER, status="diagnostics", plate="В001ОР50", client="Петрова")],
        "has_more": False,
    }

    await show_active_visits(message, _fsm_context(), api=api, user={"id": ME, "role": "master"})

    api.list_visits.assert_awaited_once_with(active=True)
    assert message.answer.await_args.args[0] == "Заезды в работе (2)"
    assert _buttons(message) == [
        ("⭐ А123ВС77 · Иванов Пётр · Ремонт", f"visit_open:{encode_id(V1)}"),
        ("В001ОР50 · Петрова · Диагностика", f"visit_open:{encode_id(V2)}"),
    ]


async def test_active_visits_admin_sees_no_stars():
    message = AsyncMock()
    api = AsyncMock()
    api.list_visits.return_value = {"items": [_visit(V1, OTHER)], "has_more": False}

    await show_active_visits(message, _fsm_context(), api=api, user={"id": ME, "role": "admin"})

    assert not _buttons(message)[0][0].startswith("⭐")


async def test_active_visits_empty():
    message = AsyncMock()
    api = AsyncMock()
    api.list_visits.return_value = {"items": [], "has_more": False}

    await show_active_visits(message, _fsm_context(), api=api, user={"id": ME, "role": "master"})

    message.answer.assert_awaited_once_with("Незакрытых заездов нет.")


async def test_active_visits_warns_when_truncated():
    message = AsyncMock()
    api = AsyncMock()
    api.list_visits.return_value = {"items": [_visit(V1, ME)], "has_more": True}

    await show_active_visits(message, _fsm_context(), api=api, user={"id": ME, "role": "master"})

    assert message.answer.await_args.args[0] == "Заезды в работе (1)\nПоказаны последние 30."


async def test_active_visits_clears_wizard_state():
    message = AsyncMock()
    api = AsyncMock()
    api.list_visits.return_value = {"items": [], "has_more": False}
    state = _fsm_context()
    await state.update_data(visit_id="stale")

    await show_active_visits(message, state, api=api, user={"id": ME, "role": "master"})

    assert await state.get_data() == {}


async def test_open_visit_sends_card():
    callback = AsyncMock()
    callback.data = f"visit_open:{encode_id(V1)}"
    api = AsyncMock()
    api.get_visit.return_value = _visit(V1, ME)
    api.list_work_items.return_value = []

    await open_visit_callback(callback, api=api)

    api.get_visit.assert_awaited_once_with(V1)
    api.list_work_items.assert_awaited_once_with(V1)
    assert callback.message.answer.await_args.args[0].startswith("А123ВС77 · Toyota Camry · Иванов Пётр")
    callback.answer.assert_awaited_once()


C1 = "33333333-3333-3333-3333-333333333333"
VH = "44444444-4444-4444-4444-444444444444"
CLIENT = {"id": C1, "full_name": "Иванов Пётр", "phone_display": "+7 999 123-45-67", "client_type": "individual"}
VEHICLE = {"id": VH, "vin": "JTNB0000000000001", "plate_number": "А123ВС77", "make": "Toyota",
           "model": "Camry", "mileage_current": 84500}


def _callback(data):
    callback = AsyncMock()
    callback.data = data
    return callback


def _cb_buttons(callback):
    markup = callback.message.answer.await_args.kwargs["reply_markup"]
    return [(b.text, b.callback_data) for row in markup.inline_keyboard for b in row]


async def test_client_card_lists_vehicles_and_visits_button():
    callback = _callback(f"client_open:{encode_id(C1)}")
    api = AsyncMock()
    api.get_client.return_value = CLIENT
    api.list_client_vehicles.return_value = [VEHICLE]

    await client_open_callback(callback, api=api)

    assert callback.message.answer.await_args.args[0] == "👤 Иванов Пётр\n+7 999 123-45-67"
    assert _cb_buttons(callback) == [
        ("🚗 Toyota Camry (А123ВС77)", f"vehicle_open:{encode_id(VH)}"),
        ("📋 Заезды клиента", f"visits_by_client:{encode_id(C1)}"),
    ]


async def test_vehicle_card_for_master_has_owner_visits_new_visit_and_history():
    callback = _callback(f"vehicle_open:{encode_id(VH)}")
    api = AsyncMock()
    api.get_vehicle.return_value = VEHICLE
    api.get_vehicle_owner.return_value = CLIENT

    await vehicle_open_callback(callback, api=api, user={"id": ME, "role": "master"})

    assert callback.message.answer.await_args.args[0] == (
        "🚗 Toyota Camry · А123ВС77\nVIN: JTNB0000000000001 · Пробег: 84 500 км"
    )
    assert _cb_buttons(callback) == [
        ("👤 Владелец: Иванов Пётр", f"client_open:{encode_id(C1)}"),
        ("📋 Заезды по машине", f"visits_by_vehicle:{encode_id(VH)}"),
        ("➕ Новый заезд", f"new_visit_for:{encode_id(VH)}"),
        ("🔧 История работ", f"work_history:{encode_id(VH)}"),
    ]


async def test_vehicle_card_without_owner_hides_owner_and_new_visit():
    callback = _callback(f"vehicle_open:{encode_id(VH)}")
    api = AsyncMock()
    api.get_vehicle.return_value = VEHICLE
    api.get_vehicle_owner.return_value = None

    await vehicle_open_callback(callback, api=api, user={"id": ME, "role": "admin"})

    assert [t for t, _ in _cb_buttons(callback)] == ["📋 Заезды по машине", "🔧 История работ"]


async def test_vehicle_card_for_mechanic_has_only_history_and_never_asks_owner():
    callback = _callback(f"vehicle_open:{encode_id(VH)}")
    api = AsyncMock()
    api.get_vehicle.return_value = VEHICLE

    await vehicle_open_callback(callback, api=api, user={"id": ME, "role": "mechanic"})

    api.get_vehicle_owner.assert_not_awaited()
    assert [t for t, _ in _cb_buttons(callback)] == ["🔧 История работ"]


async def test_visits_by_client_and_vehicle_show_dated_history():
    api = AsyncMock()
    api.list_visits.return_value = {"items": [_visit(V1, OTHER, status="issued")], "has_more": True}
    by_client = _callback(f"visits_by_client:{encode_id(C1)}")
    by_vehicle = _callback(f"visits_by_vehicle:{encode_id(VH)}")

    await visits_by_client_callback(by_client, api=api, user={"id": ME, "role": "master"})
    await visits_by_vehicle_callback(by_vehicle, api=api, user={"id": ME, "role": "master"})

    assert api.list_visits.await_args_list[0].kwargs == {"client_id": C1}
    assert api.list_visits.await_args_list[1].kwargs == {"vehicle_id": VH}
    assert by_client.message.answer.await_args.args[0] == "Заезды (1)\nПоказаны последние 30."
    assert _cb_buttons(by_client)[0][0] == "02.10 · А123ВС77 · Выдан"


async def test_visits_history_empty():
    api = AsyncMock()
    api.list_visits.return_value = {"items": [], "has_more": False}
    callback = _callback(f"visits_by_client:{encode_id(C1)}")

    await visits_by_client_callback(callback, api=api, user={"id": ME, "role": "master"})

    callback.message.answer.assert_awaited_once_with("Заездов ещё не было.")


async def test_work_history_groups_by_visit():
    api = AsyncMock()
    api.get_vehicle.return_value = VEHICLE
    api.get_vehicle_work_history.return_value = {
        "items": [
            {"visit_id": V1, "visit_at": "2026-09-12T07:00:00+00:00", "mileage": 84500,
             "name": "Замена масла ДВС", "status": "ready"},
            {"visit_id": V1, "visit_at": "2026-09-12T07:00:00+00:00", "mileage": 84500,
             "name": "Замена фильтра салона", "status": "in_progress"},
            {"visit_id": V2, "visit_at": "2026-04-03T07:00:00+00:00", "mileage": 76200,
             "name": "Диагностика подвески", "status": "ready"},
        ],
        "has_more": False,
    }
    callback = _callback(f"work_history:{encode_id(VH)}")

    await work_history_callback(callback, api=api)

    callback.message.answer.assert_awaited_once_with(
        "🔧 История работ · А123ВС77\n"
        "12.09.2026 · 84 500 км\n"
        "  • Замена масла ДВС — Готово\n"
        "  • Замена фильтра салона — В работе\n"
        "03.04.2026 · 76 200 км\n"
        "  • Диагностика подвески — Готово"
    )


async def test_work_history_empty_and_truncated():
    api = AsyncMock()
    api.get_vehicle.return_value = VEHICLE
    api.get_vehicle_work_history.return_value = {"items": [], "has_more": False}
    empty = _callback(f"work_history:{encode_id(VH)}")

    await work_history_callback(empty, api=api)

    empty.message.answer.assert_awaited_once_with("Работ по машине ещё не было.")

    api.get_vehicle_work_history.return_value = {
        "items": [{"visit_id": V1, "visit_at": "2026-09-12T07:00:00+00:00", "mileage": 1,
                   "name": "Работа", "status": "ready"}],
        "has_more": True,
    }
    truncated = _callback(f"work_history:{encode_id(VH)}")

    await work_history_callback(truncated, api=api)

    assert truncated.message.answer.await_args.args[0].endswith("Показаны последние 30 работ.")
