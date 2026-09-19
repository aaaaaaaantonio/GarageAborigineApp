import uuid

import pytest

from app.core.enums import UserRole, VisitStatus, WorkCategory
from app.core.exceptions import CancelReasonRequired, InvalidTransition, NotAllWorkItemsReady, VisitNotFound
from app.modules.clients.schemas import ClientCreate
from app.modules.clients.service import ClientService
from app.modules.users.models import User
from app.modules.vehicles.schemas import VehicleCreate
from app.modules.vehicles.service import VehicleService
from app.modules.visits.schemas import VisitCreate
from app.modules.visits.service import VisitService
from app.modules.visits.work_items_schemas import WorkItemCreate
from app.modules.visits.work_items_service import WorkItemService


async def _create_visit(session):
    admin = User(role=UserRole.ADMIN, full_name="Админ", branch_id=uuid.uuid4())
    master = User(role=UserRole.MASTER, full_name="Мастер", branch_id=uuid.uuid4())
    session.add_all([admin, master])
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
    return admin, visit


async def test_valid_transition_logs_status_change(session):
    admin, visit = await _create_visit(session)
    updated = await VisitService(session).change_status(visit.id, VisitStatus.DIAGNOSTICS, admin)
    assert updated.status == VisitStatus.DIAGNOSTICS


async def test_invalid_transition_rejected(session):
    admin, visit = await _create_visit(session)
    with pytest.raises(InvalidTransition):
        await VisitService(session).change_status(visit.id, VisitStatus.READY, admin)


async def test_cancel_without_reason_rejected(session):
    admin, visit = await _create_visit(session)
    with pytest.raises(CancelReasonRequired):
        await VisitService(session).change_status(visit.id, VisitStatus.CANCELLED, admin, reason=None)


async def test_ready_blocked_until_all_work_items_ready(session):
    admin, visit = await _create_visit(session)
    for status in (VisitStatus.DIAGNOSTICS, VisitStatus.APPROVAL, VisitStatus.IN_PROGRESS):
        visit = await VisitService(session).change_status(visit.id, status, admin)

    await WorkItemService(session).add_item(
        visit.id,
        WorkItemCreate(
            free_text_name="Замена масла",
            category=WorkCategory.MAINTENANCE,
            norm_hours=1.0,
            hourly_rate=1500,
        ),
        admin,
    )

    with pytest.raises(NotAllWorkItemsReady):
        await VisitService(session).change_status(visit.id, VisitStatus.READY, admin)


async def test_change_status_unknown_visit_raises_not_found(session):
    admin, visit = await _create_visit(session)
    with pytest.raises(VisitNotFound):
        await VisitService(session).change_status(uuid.uuid4(), VisitStatus.DIAGNOSTICS, admin)
