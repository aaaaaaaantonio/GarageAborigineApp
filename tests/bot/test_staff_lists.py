from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

from bot.callback_ids import encode_id
from bot.handlers.staff_lists import ARCHIVE_PAGE, render_archive, render_board
from tests.bot.helpers import ADMIN, MASTER, buttons

V1 = "11111111-1111-1111-1111-111111111111"
W1 = "22222222-2222-2222-2222-222222222222"
W2 = "33333333-3333-3333-3333-333333333333"
M1 = "44444444-4444-4444-4444-444444444444"


def _closed(visit_id=V1, status="issued", amount=12500.0):
    return {"id": visit_id, "status": status, "plate_number": "А123ВС77", "client_name": "Иванов", "total_amount": amount,
            "assigned_master_id": M1, "status_changed_at": "2026-10-01T10:00:00+00:00"}


def _go(markup, screen):
    return [b for b in buttons(markup) if b[1].startswith(f"go:{screen}:")]


def _opts(markup):
    return [b for b in buttons(markup) if b[1].startswith("opt:")]


# --- archive ---

async def test_archive_defaults_to_last_month_with_totals():
    api = AsyncMock()
    api.list_visits.return_value = {"items": [_closed(), _closed(W1, "cancelled", 0)], "has_more": False,
                                    "total_count": 2, "issued_amount": 12500.0}

    text, markup = await render_archive(api, MASTER, {})

    kwargs = api.list_visits.await_args.kwargs
    assert kwargs["closed"] is True and kwargs["sort"] == "date" and kwargs["offset"] == 0
    since = datetime.fromisoformat(kwargs["since"])
    assert abs(datetime.now(timezone.utc) - timedelta(days=30) - since) < timedelta(minutes=1)
    assert text == "🗄 Архив заездов · Месяц\nЗаездов: 2 · Выручка: 12 500 ₽"
    assert _go(markup, "visit") == [
        ("01.10 · А123ВС77 · ✅ Выдан · 12 500 ₽", f"go:visit:{encode_id(V1)}"),
        ("01.10 · А123ВС77 · ❌ Отменён · 0 ₽", f"go:visit:{encode_id(W1)}"),
    ]
    assert _opts(markup) == [
        ("Период: Месяц ▾", "opt:open:p"), ("Итог: Все ▾", "opt:open:o"), ("Сортировка: По дате ▾", "opt:open:s"),
    ]
    _, opened = await render_archive(api, MASTER, {"open": "p"})
    assert ("✓ Месяц", "opt:p:month") in _opts(opened) and ("Квартал", "opt:p:quarter") in _opts(opened)


async def test_archive_period_outcome_and_paging():
    api = AsyncMock()
    api.list_visits.return_value = {"items": [_closed()], "has_more": True, "total_count": 45, "issued_amount": 1.0}

    text, markup = await render_archive(api, MASTER, {"p": "all", "o": "cancelled", "s": "amount", "page": "1"})

    kwargs = api.list_visits.await_args.kwargs
    assert "since" not in kwargs or kwargs["since"] is None
    assert kwargs["status"] == ["cancelled"] and kwargs["sort"] == "amount" and kwargs["offset"] == ARCHIVE_PAGE
    assert "стр. 2" in text
    assert ("‹ Пред.", "opt:page:0") in _opts(markup) and ("Далее ›", "opt:page:2") in _opts(markup)


async def test_archive_empty_and_admin_master_picker():
    api = AsyncMock()
    api.list_visits.return_value = {"items": [], "has_more": False, "total_count": 0, "issued_amount": 0}
    api.list_masters.return_value = [{"id": M1, "full_name": "Кузнецов"}]

    text, markup = await render_archive(api, ADMIN, {"m": encode_id(M1)})
    _, master_markup = await render_archive(api, MASTER, {})

    assert text.endswith("За этот период закрытых заездов нет.")
    assert api.list_visits.await_args_list[0].kwargs["master_id"] == M1
    assert ("Мастер: Кузнецов ▾", "opt:open:m") in _opts(markup)
    assert not [b for b in _opts(master_markup) if b[1].startswith("opt:m:")]


# --- board ---

def _work(work_id, name, status="in_progress", mechanic="Морозов", plate="А123ВС77", approved=True):
    return {"id": work_id, "visit_id": V1, "name": name, "status": status, "assigned_mechanic_name": mechanic,
            "plate_number": plate, "make_model": "Kia Rio", "approved_by_client": approved}


async def test_board_groups_in_text_and_links_works():
    api = AsyncMock()
    api.list_work_board.return_value = {"items": [
        _work(W1, "Колодки", status="not_ready", mechanic=None, approved=False),
        _work(W2, "Генератор", status="waiting_parts"),
    ], "has_more": False}
    api.list_mechanics.return_value = [{"id": M1, "full_name": "Морозов"}]

    text, markup = await render_board(api, MASTER, {})

    api.list_work_board.assert_awaited_once_with(group="mechanic")
    assert text == (
        "📋 Доска работ (2)\n\n"
        "Без исполнителя\n  ⏳ Колодки · А123ВС77 · не согласовано\n\n"
        "Морозов\n  📦 Генератор · А123ВС77"
    )
    assert _go(markup, "work") == [
        ("⏳ Колодки · А123ВС77", f"go:work:{encode_id(V1)}:{encode_id(W1)}"),
        ("📦 Генератор · А123ВС77", f"go:work:{encode_id(V1)}:{encode_id(W2)}"),
    ]


async def test_board_filters_go_to_the_api():
    api = AsyncMock()
    api.list_work_board.return_value = {"items": [], "has_more": False}
    api.list_mechanics.return_value = [{"id": M1, "full_name": "Морозов"}]

    text, markup = await render_board(api, MASTER, {"mech": encode_id(M1), "st": "ready", "cat": "chassis", "un": "1", "g": "car"})
    await render_board(api, MASTER, {"mech": "none"})

    api.list_work_board.assert_any_await(mechanic_id=M1, status=["ready"], category=["chassis"], unapproved=True, group="car")
    api.list_work_board.assert_awaited_with(unassigned=True, group="mechanic")
    assert text.endswith("Работ с этим фильтром нет.")
    assert [b[0] for b in _opts(markup)] == [
        "Механик: Морозов ▾", "Статус: Готово ▾", "Категория: Ходовая ▾",
        "Согласование: Не согласованные ▾", "Группировка: По машине ▾",
    ]
