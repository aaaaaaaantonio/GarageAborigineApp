import uuid

from sqlalchemy import select

from app.core.enums import UserRole, VisitStatus
from app.modules.clients.schemas import ClientCreate
from app.modules.clients.service import ClientService
from app.modules.notifications.logging_sender import NotificationOutbox
from app.modules.users.models import User
from app.modules.vehicles.schemas import VehicleCreate
from app.modules.vehicles.service import VehicleService
from app.modules.visits.schemas import VisitCreate
from app.modules.visits.service import VisitService


async def test_status_change_to_waiting_parts_writes_notification(session):
    admin = User(role=UserRole.ADMIN, full_name="Админ", branch_id=uuid.uuid4())
    master = User(role=UserRole.MASTER, full_name="Мастер", branch_id=uuid.uuid4())
    session.add_all([admin, master])
    await session.flush()
    client = await ClientService(session).create_client(ClientCreate(full_name="Иван", phone="79991234567"), admin)
    vehicle = await VehicleService(session).create_vehicle(
        VehicleCreate(vin="X" * 17, plate_number="А123", make="Toyota", model="Camry"), admin
    )
    visit_service = VisitService(session)
    visit = await visit_service.create_visit(
        VisitCreate(client_id=client.id, vehicle_id=vehicle.id, assigned_master_id=master.id, mileage_at_intake=1000),
        admin,
    )
    for status in (VisitStatus.DIAGNOSTICS, VisitStatus.APPROVAL, VisitStatus.IN_PROGRESS):
        visit = await visit_service.change_status(visit.id, status, admin)
    await visit_service.change_status(visit.id, VisitStatus.WAITING_PARTS, admin)

    rows = list((await session.execute(select(NotificationOutbox))).scalars())
    assert any(r.kind == "status_changed" for r in rows)
