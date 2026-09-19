import uuid

from app.core.enums import UserRole, VisitStatus, WorkCategory, WorkItemStatus
from app.modules.clients.schemas import ClientCreate
from app.modules.clients.service import ClientService
from app.modules.documents.service import DocumentService
from app.modules.documents.storage import LocalFileStorage
from app.modules.users.models import User
from app.modules.vehicles.schemas import VehicleCreate
from app.modules.vehicles.service import VehicleService
from app.modules.visits.schemas import VisitCreate
from app.modules.visits.service import VisitService
from app.modules.visits.work_items_schemas import WorkItemCreate
from app.modules.visits.work_items_service import WorkItemService


async def test_full_visit_lifecycle_produces_document(session, tmp_path):
    admin = User(role=UserRole.ADMIN, full_name="Админ", branch_id=uuid.uuid4())
    master = User(role=UserRole.MASTER, full_name="Мастер", branch_id=uuid.uuid4())
    mechanic = User(role=UserRole.MECHANIC, full_name="Механик", branch_id=uuid.uuid4())
    session.add_all([admin, master, mechanic])
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

    work_item_service = WorkItemService(session)
    item = await work_item_service.add_item(
        visit.id,
        WorkItemCreate(
            free_text_name="Замена масла",
            category=WorkCategory.MAINTENANCE,
            norm_hours=1.0,
            hourly_rate=1500,
            assigned_mechanic_id=mechanic.id,
        ),
        admin,
    )

    for status in (VisitStatus.DIAGNOSTICS, VisitStatus.APPROVAL, VisitStatus.IN_PROGRESS):
        visit = await visit_service.change_status(visit.id, status, admin)

    await work_item_service.update_status(item.id, WorkItemStatus.READY, mechanic)
    visit = await visit_service.change_status(visit.id, VisitStatus.READY, admin)
    assert visit.status == VisitStatus.READY

    storage = LocalFileStorage(root=str(tmp_path))
    url = await DocumentService(session, storage=storage).generate_visit_document(visit.id)
    assert url is not None
