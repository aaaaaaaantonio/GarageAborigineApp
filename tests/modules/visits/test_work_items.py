import uuid

import pytest

from app.core.enums import UserRole, WorkCategory, WorkItemStatus
from app.core.exceptions import NotAssignedMechanic, VisitNotFound, WorkItemNotFound
from app.modules.clients.schemas import ClientCreate
from app.modules.clients.service import ClientService
from app.modules.users.models import User
from app.modules.vehicles.schemas import VehicleCreate
from app.modules.vehicles.service import VehicleService
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
