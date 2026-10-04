import uuid
from unittest.mock import AsyncMock

from app.core.enums import UserRole, VisitStatus
from app.modules.clients.schemas import ClientCreate
from app.modules.clients.service import ClientService
from app.modules.notifications.logging_sender import NotificationOutbox
from app.modules.notifications.telegram_sender import TelegramNotificationSender
from app.modules.users.models import User
from app.modules.vehicles.schemas import VehicleCreate
from app.modules.vehicles.service import VehicleService
from app.modules.visits.models import Visit
from sqlalchemy import select


async def _make_visit_with_master(session, telegram_id):
    admin = User(role=UserRole.ADMIN, full_name="Админ", branch_id=uuid.uuid4())
    master = User(role=UserRole.MASTER, full_name="Мастер", telegram_id=telegram_id, branch_id=uuid.uuid4())
    session.add_all([admin, master])
    await session.flush()
    client = await ClientService(session).create_client(
        ClientCreate(full_name="Иван", phone="79991234567"), admin
    )
    vehicle = await VehicleService(session).create_vehicle(
        VehicleCreate(vin="X" * 17, plate_number="А123", make="Toyota", model="Camry"), admin
    )
    visit = Visit(
        client_id=client.id,
        vehicle_id=vehicle.id,
        assigned_master_id=master.id,
        mileage_at_intake=1000,
        status=VisitStatus.RECEIVED,
    )
    session.add(visit)
    await session.flush()
    return visit


async def test_send_status_changed_writes_outbox_and_calls_telegram(session):
    visit = await _make_visit_with_master(session, telegram_id=777)
    bot = AsyncMock()
    sender = TelegramNotificationSender(session, bot)

    await sender.send_status_changed(visit, VisitStatus.RECEIVED, VisitStatus.READY)

    rows = list((await session.execute(select(NotificationOutbox))).scalars())
    assert any(r.kind == "status_changed" for r in rows)
    bot.send_message.assert_awaited_once()
    assert bot.send_message.await_args.kwargs["chat_id"] == 777


async def test_send_status_changed_skips_telegram_when_no_telegram_id(session):
    visit = await _make_visit_with_master(session, telegram_id=None)
    bot = AsyncMock()
    sender = TelegramNotificationSender(session, bot)

    await sender.send_status_changed(visit, VisitStatus.RECEIVED, VisitStatus.READY)

    rows = list((await session.execute(select(NotificationOutbox))).scalars())
    assert any(r.kind == "status_changed" for r in rows)
    bot.send_message.assert_not_awaited()


async def test_send_status_changed_swallows_telegram_failure(session, caplog):
    visit = await _make_visit_with_master(session, telegram_id=778)
    bot = AsyncMock()
    bot.send_message.side_effect = RuntimeError("chat not found")
    sender = TelegramNotificationSender(session, bot)

    await sender.send_status_changed(visit, VisitStatus.RECEIVED, VisitStatus.READY)

    rows = list((await session.execute(select(NotificationOutbox))).scalars())
    assert any(r.kind == "status_changed" for r in rows)
    assert "chat not found" in caplog.text


async def _work_item_for(session, visit, name="Замена масла"):
    from app.core.enums import WorkCategory, WorkItemStatus
    from app.modules.visits.models import VisitWorkItem

    item = VisitWorkItem(
        visit_id=visit.id,
        free_text_name=name,
        category=WorkCategory.MAINTENANCE,
        norm_hours=1.0,
        hourly_rate=1500,
        status=WorkItemStatus.NOT_READY,
    )
    session.add(item)
    await session.flush()
    return item


async def _mechanic(session, telegram_id):
    mechanic = User(role=UserRole.MECHANIC, full_name="Механик", telegram_id=telegram_id, branch_id=uuid.uuid4())
    session.add(mechanic)
    await session.flush()
    return mechanic


async def test_send_work_assigned_messages_mechanic_with_name_and_plate(session):
    visit = await _make_visit_with_master(session, telegram_id=None)
    item = await _work_item_for(session, visit)
    mechanic = await _mechanic(session, telegram_id=901)
    bot = AsyncMock()

    await TelegramNotificationSender(session, bot).send_work_assigned(item, mechanic.id)

    rows = list((await session.execute(select(NotificationOutbox))).scalars())
    assert any(r.kind == "work_assigned" for r in rows)
    kwargs = bot.send_message.await_args.kwargs
    assert kwargs["chat_id"] == 901
    assert kwargs["text"] == "Вам назначена работа «Замена масла» · А123"


async def test_send_work_unassigned_messages_old_mechanic(session):
    visit = await _make_visit_with_master(session, telegram_id=None)
    item = await _work_item_for(session, visit)
    mechanic = await _mechanic(session, telegram_id=902)
    bot = AsyncMock()

    await TelegramNotificationSender(session, bot).send_work_unassigned(item, mechanic.id)

    rows = list((await session.execute(select(NotificationOutbox))).scalars())
    assert any(r.kind == "work_unassigned" for r in rows)
    kwargs = bot.send_message.await_args.kwargs
    assert kwargs["chat_id"] == 902
    assert kwargs["text"] == "Работа «Замена масла» · А123 снята с вас"


async def test_send_work_assigned_skips_mechanic_without_telegram_id(session):
    visit = await _make_visit_with_master(session, telegram_id=None)
    item = await _work_item_for(session, visit)
    mechanic = await _mechanic(session, telegram_id=None)
    bot = AsyncMock()

    await TelegramNotificationSender(session, bot).send_work_assigned(item, mechanic.id)

    bot.send_message.assert_not_awaited()
