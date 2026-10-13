import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.core.enums import ApprovedVia, UserRole, VisitStatus, WorkCategory, WorkItemStatus
from app.core.exceptions import InvalidAssignedMechanic, NotAssignedMechanic, VisitNotFound, WorkItemNotFound
from app.modules.clients.schemas import ClientCreate
from app.modules.clients.service import ClientService
from app.modules.users.audit import AuditLog
from app.modules.users.models import User
from app.modules.vehicles.schemas import VehicleCreate
from app.modules.vehicles.service import VehicleService
from app.modules.visits.models import Visit
from app.modules.visits.schemas import VisitCreate
from app.modules.visits.service import VisitService
from app.modules.visits.work_items_schemas import WorkItemCreate
from app.modules.visits.work_items_service import WorkItemService


async def _setup_visit_with_mechanic(session):
    admin = User(role=UserRole.ADMIN, full_name="Админ", branch_id=uuid.uuid4())
    master = User(role=UserRole.MASTER, full_name="Мастер", branch_id=uuid.uuid4())
    mechanic_a = User(role=UserRole.MECHANIC, full_name="Механик А", branch_id=uuid.uuid4())
    mechanic_b = User(role=UserRole.MECHANIC, full_name="Механик Б", branch_id=uuid.uuid4())
    session.add_all([admin, master, mechanic_a, mechanic_b])
    await session.flush()

    client = await ClientService(session).create_client(
        ClientCreate(full_name="Иван", phone="79991234567"), admin
    )
    vehicle = await VehicleService(session).create_vehicle(
        VehicleCreate(vin="X" * 17, plate_number="А123", make="Toyota", model="Camry"), admin
    )
    visit = await VisitService(session).create_visit(
        VisitCreate(client_id=client.id, vehicle_id=vehicle.id, assigned_master_id=master.id, mileage_at_intake=1000),
        admin,
    )
    item = await WorkItemService(session).add_item(
        visit.id,
        WorkItemCreate(
            free_text_name="Замена масла",
            category=WorkCategory.MAINTENANCE,
            norm_hours=1.0,
            hourly_rate=1500,
            assigned_mechanic_id=mechanic_a.id,
        ),
        admin,
    )
    return admin, mechanic_a, mechanic_b, item


async def test_assigned_mechanic_can_update_status(session):
    admin, mechanic_a, mechanic_b, item = await _setup_visit_with_mechanic(session)
    updated = await WorkItemService(session).update_status(item.id, WorkItemStatus.IN_PROGRESS, mechanic_a)
    assert updated.status == WorkItemStatus.IN_PROGRESS


async def test_other_mechanic_cannot_update_status(session):
    admin, mechanic_a, mechanic_b, item = await _setup_visit_with_mechanic(session)
    with pytest.raises(NotAssignedMechanic):
        await WorkItemService(session).update_status(item.id, WorkItemStatus.IN_PROGRESS, mechanic_b)


async def test_approve_sets_flags(session):
    admin, mechanic_a, mechanic_b, item = await _setup_visit_with_mechanic(session)
    approved = await WorkItemService(session).approve(item.id, admin)
    assert approved.approved_by_client is True
    assert approved.approved_at is not None


async def test_add_item_unknown_visit_raises_not_found(session):
    admin = User(role=UserRole.ADMIN, full_name="Админ", branch_id=uuid.uuid4())
    session.add(admin)
    await session.flush()
    with pytest.raises(VisitNotFound):
        await WorkItemService(session).add_item(
            uuid.uuid4(),
            WorkItemCreate(free_text_name="Замена масла", category=WorkCategory.MAINTENANCE, norm_hours=1.0, hourly_rate=1500),
            admin,
        )


async def test_update_status_unknown_item_raises_not_found(session):
    admin, mechanic_a, mechanic_b, item = await _setup_visit_with_mechanic(session)
    with pytest.raises(WorkItemNotFound):
        await WorkItemService(session).update_status(uuid.uuid4(), WorkItemStatus.IN_PROGRESS, mechanic_a)


async def test_approve_unknown_item_raises_not_found(session):
    admin, mechanic_a, mechanic_b, item = await _setup_visit_with_mechanic(session)
    with pytest.raises(WorkItemNotFound):
        await WorkItemService(session).approve(uuid.uuid4(), admin)


async def test_list_mine_returns_only_own_assigned_items(session):
    admin, mechanic_a, mechanic_b, item_a = await _setup_visit_with_mechanic(session)

    mine = await WorkItemService(session).list_mine(mechanic_a)
    assert [i.id for i in mine] == [item_a.id]

    other = await WorkItemService(session).list_mine(mechanic_b)
    assert other == []


@pytest.mark.parametrize("closed", [VisitStatus.ISSUED, VisitStatus.CANCELLED, "deleted"])
async def test_list_mine_skips_items_of_closed_visits(session, closed):
    admin, mechanic_a, mechanic_b, item = await _setup_visit_with_mechanic(session)
    visit = await session.get(Visit, item.visit_id)
    if closed == "deleted":
        visit.deleted_at = datetime.now(timezone.utc)
    else:
        visit.status = closed
    await session.flush()

    assert await WorkItemService(session).list_mine(mechanic_a) == []


async def test_list_mine_keeps_ready_items_of_open_visits(session):
    admin, mechanic_a, mechanic_b, item = await _setup_visit_with_mechanic(session)
    await WorkItemService(session).update_status(item.id, WorkItemStatus.READY, mechanic_a)

    mine = await WorkItemService(session).list_mine(mechanic_a)
    assert [i.id for i in mine] == [item.id]


async def _close(session, item, status, work_status=WorkItemStatus.READY):
    item.status = work_status
    visit = await session.get(Visit, item.visit_id)
    visit.status = status
    await session.flush()
    return visit


@pytest.mark.parametrize("closed", [VisitStatus.ISSUED, VisitStatus.CANCELLED])
async def test_list_done_returns_ready_items_of_closed_visits(session, closed):
    admin, mechanic_a, mechanic_b, item = await _setup_visit_with_mechanic(session)
    visit = await _close(session, item, closed)

    done = await WorkItemService(session).list_done(mechanic_a)
    assert [i.id for i in done] == [item.id]
    assert done[0].name == "Замена масла"
    assert done[0].plate_number == "А123"
    assert done[0].visit_status == closed
    assert done[0].visit_date == visit.created_at
    assert await WorkItemService(session).list_done(mechanic_b) == []


async def test_list_done_skips_open_visits_unfinished_and_deleted(session):
    admin, mechanic_a, mechanic_b, item = await _setup_visit_with_mechanic(session)
    item.status = WorkItemStatus.READY  # готова, но машина ещё в сервисе
    await session.flush()
    assert await WorkItemService(session).list_done(mechanic_a) == []

    await _close(session, item, VisitStatus.CANCELLED, WorkItemStatus.NOT_READY)
    assert await WorkItemService(session).list_done(mechanic_a) == []

    visit = await _close(session, item, VisitStatus.ISSUED)
    visit.deleted_at = datetime.now(timezone.utc)
    await session.flush()
    assert await WorkItemService(session).list_done(mechanic_a) == []


async def test_list_done_newest_visit_first(session):
    admin, mechanic_a, mechanic_b, old = await _setup_visit_with_mechanic(session)
    old_visit = await _close(session, old, VisitStatus.ISSUED)
    new_visit = await VisitService(session).create_visit(
        VisitCreate(client_id=old_visit.client_id, vehicle_id=old_visit.vehicle_id,
                    assigned_master_id=old_visit.assigned_master_id, mileage_at_intake=2000),
        admin,
    )
    new = await WorkItemService(session).add_item(
        new_visit.id,
        WorkItemCreate(free_text_name="Развал", category=WorkCategory.CHASSIS, norm_hours=1.0,
                       hourly_rate=1500, assigned_mechanic_id=mechanic_a.id),
        admin,
    )
    await _close(session, new, VisitStatus.ISSUED)
    old_visit.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    await session.flush()

    done = await WorkItemService(session).list_done(mechanic_a)
    assert [i.id for i in done] == [new.id, old.id]


async def test_list_for_visit_returns_items_for_that_visit(session):
    admin, mechanic_a, mechanic_b, item = await _setup_visit_with_mechanic(session)

    items = await WorkItemService(session).list_for_visit(item.visit_id)

    assert [i.id for i in items] == [item.id]


async def test_list_for_visit_unknown_visit_raises_not_found(session):
    with pytest.raises(VisitNotFound):
        await WorkItemService(session).list_for_visit(uuid.uuid4())


async def _add_catalog_item(session, admin, name="Замена масла"):
    from app.modules.catalog.schemas import WorkCatalogCreate
    from app.modules.catalog.service import CatalogService

    return await CatalogService(session).create_item(
        WorkCatalogCreate(name=name, category=WorkCategory.MAINTENANCE, default_norm_hours=1.0), admin
    )


async def test_list_for_visit_resolves_name_from_catalog_or_free_text(session):
    admin, mechanic_a, mechanic_b, free_item = await _setup_visit_with_mechanic(session)
    catalog_item = await _add_catalog_item(session, admin, name="Диагностика ходовой")
    catalog_work = await WorkItemService(session).add_item(
        free_item.visit_id,
        WorkItemCreate(
            catalog_item_id=catalog_item.id, category=WorkCategory.CHASSIS, norm_hours=1.0, hourly_rate=1000
        ),
        admin,
    )

    items = await WorkItemService(session).list_for_visit(free_item.visit_id)

    names = {i.id: i.name for i in items}
    assert names[free_item.id] == "Замена масла"
    assert names[catalog_work.id] == "Диагностика ходовой"


async def test_list_for_visit_orders_by_created_at(session):
    from datetime import datetime, timedelta, timezone

    admin, mechanic_a, mechanic_b, first = await _setup_visit_with_mechanic(session)
    second = await WorkItemService(session).add_item(
        first.visit_id,
        WorkItemCreate(free_text_name="Вторая", category=WorkCategory.OTHER, norm_hours=1.0, hourly_rate=1000),
        admin,
    )
    now = datetime.now(timezone.utc)
    first.created_at = now + timedelta(minutes=1)
    second.created_at = now
    await session.flush()

    items = await WorkItemService(session).list_for_visit(first.visit_id)

    assert [i.id for i in items] == [second.id, first.id]


async def test_list_mine_resolves_name(session):
    admin, mechanic_a, mechanic_b, item = await _setup_visit_with_mechanic(session)

    mine = await WorkItemService(session).list_mine(mechanic_a)

    assert mine[0].name == "Замена масла"


async def test_update_status_result_serializes_with_name_and_visit_id(session):
    from app.modules.visits.work_items_schemas import WorkItemOut

    admin, mechanic_a, mechanic_b, item = await _setup_visit_with_mechanic(session)

    updated = await WorkItemService(session).update_status(item.id, WorkItemStatus.IN_PROGRESS, admin)

    out = WorkItemOut.model_validate(updated)
    assert out.name == "Замена масла"
    assert out.visit_id == item.visit_id


async def _new_work_item(mechanic_id):
    return WorkItemCreate(
        free_text_name="Диагностика",
        category=WorkCategory.MAINTENANCE,
        norm_hours=1.0,
        hourly_rate=1500,
        assigned_mechanic_id=mechanic_id,
    )


@pytest.mark.parametrize("who", ["master", "unknown", "deleted_mechanic"])
async def test_add_item_rejects_invalid_assigned_mechanic(session, who):
    admin, mechanic_a, mechanic_b, item = await _setup_visit_with_mechanic(session)
    if who == "master":
        assignee = User(role=UserRole.MASTER, full_name="Мастер 2", branch_id=uuid.uuid4())
        session.add(assignee)
        await session.flush()
        assignee_id = assignee.id
    elif who == "unknown":
        assignee_id = uuid.uuid4()
    else:
        mechanic_b.deleted_at = datetime.now(timezone.utc)
        await session.flush()
        assignee_id = mechanic_b.id

    with pytest.raises(InvalidAssignedMechanic):
        await WorkItemService(session).add_item(item.visit_id, await _new_work_item(assignee_id), admin)


async def test_add_item_without_mechanic_is_allowed(session):
    admin, mechanic_a, mechanic_b, item = await _setup_visit_with_mechanic(session)
    created = await WorkItemService(session).add_item(item.visit_id, await _new_work_item(None), admin)
    assert created.assigned_mechanic_id is None


async def _audit_rows(session, entity_id, action):
    result = await session.execute(
        select(AuditLog).where(AuditLog.entity_id == entity_id, AuditLog.action == action)
    )
    return list(result.scalars())


async def test_update_status_is_audited(session):
    admin, mechanic_a, mechanic_b, item = await _setup_visit_with_mechanic(session)
    await WorkItemService(session).update_status(item.id, WorkItemStatus.IN_PROGRESS, mechanic_a)

    rows = await _audit_rows(session, item.id, "status_change")
    assert len(rows) == 1
    assert rows[0].user_id == mechanic_a.id
    assert rows[0].entity_type == "visit_work_item"
    assert rows[0].old_value == {"status": WorkItemStatus.NOT_READY.value}
    assert rows[0].new_value == {"status": WorkItemStatus.IN_PROGRESS.value}


async def test_approve_is_audited(session):
    admin, mechanic_a, mechanic_b, item = await _setup_visit_with_mechanic(session)
    await WorkItemService(session).approve(item.id, admin)

    rows = await _audit_rows(session, item.id, "approve")
    assert len(rows) == 1
    assert rows[0].user_id == admin.id
    assert rows[0].new_value == {"approved_via": ApprovedVia.CRM_STATUS.value}


async def test_list_mine_includes_vehicle_plate_and_make_model(session):
    from app.modules.visits.work_items_schemas import WorkItemMineOut

    admin, mechanic_a, mechanic_b, item = await _setup_visit_with_mechanic(session)

    mine = await WorkItemService(session).list_mine(mechanic_a)

    out = WorkItemMineOut.model_validate(mine[0])
    assert out.plate_number == "А123"
    assert out.make_model == "Toyota Camry"
