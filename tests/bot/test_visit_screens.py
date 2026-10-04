from unittest.mock import AsyncMock

import pytest

from bot.api_client import ApiNotFound
from bot.callback_ids import encode_id
from bot.handlers.documents import pdf_callback
from bot.handlers.mechanic import render_my_works
from bot.handlers.visits import receive_cancel_reason, render_visit, render_visit_status, visit_header, visit_status_callback
from bot.handlers.work_items import (
    approve_callback,
    reassign_callback,
    render_reassign,
    render_work,
    work_status_callback,
)
from bot.states import VisitCancelStates
from tests.bot.helpers import MASTER, MECHANIC, buttons, fsm_context, make_callback, make_message, on_screens, shown

VISIT = "11111111-1111-1111-1111-111111111111"
ITEM = "22222222-2222-2222-2222-222222222222"
ITEM2 = "55555555-5555-5555-5555-555555555555"
MECH = "33333333-3333-3333-3333-333333333333"


def _visit(status="in_progress"):
    return {
        "id": VISIT, "status": status, "total_amount": 12400.0, "plate_number": "А123ВС77",
        "make_model": "Toyota Camry", "client_name": "Иванов Пётр", "master_name": "Петров",
    }


def _item(item_id=ITEM, name="Замена масла", status="in_progress", approved=True, mechanic="Сидоров"):
    return {"id": item_id, "visit_id": VISIT, "name": name, "status": status,
            "approved_by_client": approved, "assigned_mechanic_name": mechanic}


def _api(visit=None, items=None):
    api = AsyncMock()
    api.get_visit.return_value = visit or _visit()
    api.list_work_items.return_value = items if items is not None else [_item()]
    return api


# --- visit card ---

async def test_visit_card_is_compact_one_button_per_work_item():
    api = _api(items=[_item(), _item(ITEM2, "Диагностика", "not_ready", mechanic=None)])

    text, markup = await render_visit(api, MASTER, {"visit_id": VISIT})

    assert text.splitlines() == [
        "А123ВС77 · Toyota Camry · Иванов Пётр",
        "Статус: Ремонт · Мастер: Петров",
        "Сумма: 12 400",
        "Работы:",
        "1. Замена масла — В работе · Сидоров",
        "2. Диагностика — Не начата · без исполнителя",
    ]
    assert buttons(markup) == [
        ("🔧 1. Замена масла · Сидоров", f"go:work:{encode_id(VISIT)}:{encode_id(ITEM)}"),
        ("⏳ 2. Диагностика · без исполнителя", f"go:work:{encode_id(VISIT)}:{encode_id(ITEM2)}"),
        ("➕ Добавить работу", "act:add_work"),
        ("🔄 Статус заезда", f"go:visit_status:{encode_id(VISIT)}"),
        ("📄 PDF", "act:pdf"),
    ]


async def test_closed_visit_has_no_status_button():
    _, markup = await render_visit(_api(visit=_visit("issued"), items=[]), MASTER, {"visit_id": VISIT})

    assert "🔄 Статус заезда" not in [t for t, _ in buttons(markup)]


def test_visit_header_formats_total_and_falls_back_to_generic_title():
    assert visit_header({"status": "received", "total_amount": 12400.5}) == ["Заезд", "Статус: Принят", "Сумма: 12 400.50"]


# --- visit status ---

async def test_visit_status_screen_lists_allowed_next_statuses():
    text, markup = await render_visit_status(_api(visit=_visit("in_progress")), MASTER, {"visit_id": VISIT})

    assert text == "Статус сейчас: Ремонт\nСменить на:"
    assert buttons(markup) == [
        ("Ждём запчасти", "act:vstatus:waiting_parts"),
        ("Готов", "act:vstatus:ready"),
        ("Отменён", "act:vstatus:cancelled"),
    ]


async def test_choosing_status_changes_it_and_returns_to_card():
    state = fsm_context()
    await on_screens(state, ("visit", {"visit_id": VISIT}), ("visit_status", {"visit_id": VISIT}))
    api = _api()
    callback = make_callback("act:vstatus:ready")

    await visit_status_callback(callback, state, api=api, user=MASTER)

    api.change_visit_status.assert_awaited_once_with(VISIT, "ready")
    assert (await state.get_data())["nav_stack"] == [["menu", {}], ["visit", {"visit_id": VISIT}]]
    assert shown(callback)[0].startswith("А123ВС77")


async def test_choosing_cancelled_asks_for_reason():
    state = fsm_context()
    await on_screens(state, ("visit", {"visit_id": VISIT}), ("visit_status", {"visit_id": VISIT}))
    api = _api()
    callback = make_callback("act:vstatus:cancelled")

    await visit_status_callback(callback, state, api=api, user=MASTER)

    api.change_visit_status.assert_not_awaited()
    assert await state.get_state() == VisitCancelStates.waiting_for_reason.state
    assert (await state.get_data())["visit_id"] == VISIT
    assert shown(callback)[0] == "Укажите причину отмены заезда:"


async def test_cancel_reason_cancels_and_returns_to_card():
    state = fsm_context()
    await on_screens(state, ("visit", {"visit_id": VISIT}), ("visit_status", {"visit_id": VISIT}))
    await state.set_state(VisitCancelStates.waiting_for_reason)
    await state.update_data(visit_id=VISIT, wiz_steps=[])
    api = _api()
    message = make_message("клиент передумал")

    await receive_cancel_reason(message, state, api=api, user=MASTER)

    api.change_visit_status.assert_awaited_once_with(VISIT, "cancelled", reason="клиент передумал")
    assert await state.get_state() is None
    assert (await state.get_data())["nav_stack"][-1] == ["visit", {"visit_id": VISIT}]


async def test_cancel_reason_must_be_text():
    state = fsm_context()
    await on_screens(state, ("visit_status", {"visit_id": VISIT}))
    await state.set_state(VisitCancelStates.waiting_for_reason)
    await state.update_data(visit_id=VISIT)
    api = _api()
    message = make_message(None)

    await receive_cancel_reason(message, state, api=api, user=MASTER)

    api.change_visit_status.assert_not_awaited()
    assert shown(message)[0] == "Пожалуйста, отправьте ответ текстом.\n\nУкажите причину отмены заезда:"


async def test_status_button_from_another_screen_is_stale():
    state = fsm_context()
    await on_screens(state, ("visit", {"visit_id": VISIT}))
    api = _api()
    callback = make_callback("act:vstatus:ready")

    await visit_status_callback(callback, state, api=api, user=MASTER)

    api.change_visit_status.assert_not_awaited()
    callback.answer.assert_awaited_once_with("Кнопка устарела — начните действие заново.")


# --- work screen ---

async def test_work_screen_for_master():
    api = _api(items=[_item(approved=False)])

    text, markup = await render_work(api, MASTER, {"visit_id": VISIT, "item_id": ITEM})

    assert text == "А123ВС77 · Toyota Camry\n🔧 Замена масла\nСтатус: В работе\nИсполнитель: Сидоров\nСогласовано клиентом: нет"
    assert buttons(markup) == [
        ("✅ Согласовано клиентом", "act:approve"),
        ("→ Ждёт запчасти", "act:wstatus:waiting_parts"),
        ("→ Готово", "act:wstatus:ready"),
        ("🔩 Добавить запчасть", "act:add_part"),
        ("👤 Сменить исполнителя", f"go:reassign:{encode_id(VISIT)}:{encode_id(ITEM)}"),
    ]


async def test_work_screen_for_mechanic_has_only_status_buttons_and_no_visit_call():
    api = AsyncMock()
    api.list_my_work_items.return_value = [
        {"id": ITEM, "visit_id": VISIT, "name": "Замена масла", "status": "not_ready",
         "plate_number": "А123ВС77", "make_model": "Toyota Camry"},
    ]

    text, markup = await render_work(api, MECHANIC, {"visit_id": VISIT, "item_id": ITEM})

    api.get_visit.assert_not_awaited()
    assert text == "А123ВС77 · Toyota Camry\n⏳ Замена масла\nСтатус: Не начата"
    assert buttons(markup) == [("→ В работе", "act:wstatus:in_progress")]


async def test_work_screen_reassigned_away_from_mechanic_raises_not_found():
    api = AsyncMock()
    api.list_my_work_items.return_value = []

    with pytest.raises(ApiNotFound):
        await render_work(api, MECHANIC, {"visit_id": VISIT, "item_id": ITEM})


async def test_work_status_action_updates_and_redraws_in_place():
    state = fsm_context()
    await on_screens(state, ("work", {"visit_id": VISIT, "item_id": ITEM}))
    api = _api()
    callback = make_callback("act:wstatus:ready")

    await work_status_callback(callback, state, api=api, user=MASTER)

    api.update_work_item_status.assert_awaited_once_with(VISIT, ITEM, "ready")
    assert (await state.get_data())["nav_stack"][-1][0] == "work"
    callback.message.edit_text.assert_awaited_once()


async def test_work_status_action_on_old_message_is_stale():
    state = fsm_context()
    await on_screens(state, ("work", {"visit_id": VISIT, "item_id": ITEM}), msg_id=7)
    api = _api()
    callback = make_callback("act:wstatus:ready", message_id=5)

    await work_status_callback(callback, state, api=api, user=MASTER)

    api.update_work_item_status.assert_not_awaited()


async def test_approve_action():
    state = fsm_context()
    await on_screens(state, ("work", {"visit_id": VISIT, "item_id": ITEM}))
    api = _api()

    await approve_callback(make_callback("act:approve"), state, api=api, user=MASTER)

    api.approve_work_item.assert_awaited_once_with(VISIT, ITEM)


async def test_reassign_screen_and_choice_returns_to_work():
    api = _api()
    api.list_mechanics.return_value = [{"id": MECH, "full_name": "Петров"}]

    text, markup = await render_reassign(api, MASTER, {"visit_id": VISIT, "item_id": ITEM})
    assert text == "Кому передать работу?"
    assert buttons(markup) == [("Петров", f"act:reassign:{encode_id(MECH)}"), ("Без исполнителя", "act:reassign:none")]

    state = fsm_context()
    args = {"visit_id": VISIT, "item_id": ITEM}
    await on_screens(state, ("work", args), ("reassign", args))
    await reassign_callback(make_callback(f"act:reassign:{encode_id(MECH)}"), state, api=api, user=MASTER)
    api.assign_work_item_mechanic.assert_awaited_once_with(VISIT, ITEM, MECH)
    assert (await state.get_data())["nav_stack"][-1] == ["work", args]

    await on_screens(state, ("work", args), ("reassign", args))
    await reassign_callback(make_callback("act:reassign:none"), state, api=api, user=MASTER)
    api.assign_work_item_mechanic.assert_awaited_with(VISIT, ITEM, None)


# --- my works ---

async def test_my_works_lists_items_with_car():
    api = AsyncMock()
    api.list_my_work_items.return_value = [
        {"id": ITEM, "visit_id": VISIT, "name": "Замена масла", "status": "in_progress", "plate_number": "А123ВС77"},
    ]

    text, markup = await render_my_works(api, MECHANIC, {})

    assert text == "Мои работы (1)"
    assert buttons(markup) == [("🔧 Замена масла · А123ВС77", f"go:work:{encode_id(VISIT)}:{encode_id(ITEM)}")]


async def test_my_works_empty():
    api = AsyncMock()
    api.list_my_work_items.return_value = []

    text, markup = await render_my_works(api, MECHANIC, {})

    assert text == "У вас нет назначенных работ."
    assert buttons(markup) == []


# --- pdf ---

async def test_pdf_action_sends_document_without_redrawing():
    state = fsm_context()
    await on_screens(state, ("visit", {"visit_id": VISIT}))
    api = AsyncMock()
    api.generate_document.return_value = {"document_id": "d1"}
    api.get_document_file.return_value = b"%PDF"
    callback = make_callback("act:pdf")

    await pdf_callback(callback, state, api=api, user=MASTER)

    api.generate_document.assert_awaited_once_with(VISIT)
    document = callback.message.answer_document.await_args.args[0]
    assert document.filename == f"zakaz-naryad-{VISIT}.pdf"
    callback.message.edit_text.assert_not_awaited()
    callback.answer.assert_awaited_once_with()
