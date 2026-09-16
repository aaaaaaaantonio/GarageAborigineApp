import uuid

from app.core.enums import PartAvailability, UserRole, WorkCategory
from app.modules.clients.schemas import ClientCreate
from app.modules.clients.service import ClientService
from app.modules.users.models import User
from app.modules.vehicles.schemas import VehicleCreate
from app.modules.vehicles.service import VehicleService
from app.modules.visits.part_items_schemas import PartItemCreate
from app.modules.visits.part_items_service import PartItemService
from app.modules.visits.schemas import VisitCreate
from app.modules.visits.service import VisitService
from app.modules.visits.work_items_schemas import WorkItemCreate
from app.modules.visits.work_items_service import WorkItemService


async def _setup_visit_with_work_item(session):
    admin = User(role=UserRole.ADMIN, full_name="Админ", branch_id=uuid.uuid4())
    master = User(role=UserRole.MASTER, full_name="Мастер", branch_id=uuid.uuid4())
    session.add_all([admin, master])
    await session.flush()

    client = await ClientService(session).create_client(ClientCreate(full_name="Иван", phone="79991234567"), admin)
    vehicle = await VehicleService(session).create_vehicle(
        VehicleCreate(vin="X" * 17, plate_number="А123", make="Toyota", model="Camry"), admin
    )
    visit = await VisitService(session).create_visit(
        VisitCreate(client_id=client.id, vehicle_id=vehicle.id, assigned_master_id=master.id, mileage_at_intake=1000),
        admin,
    )
    # norm_hours=0 so the work item itself doesn't contribute to the total,
    # keeping the part-item recalculation assertion isolated.
    work_item = await WorkItemService(session).add_item(
        visit.id,
        WorkItemCreate(free_text_name="Диагностика", category=WorkCategory.DIAGNOSTICS, norm_hours=0, hourly_rate=0),
        admin,
    )
    return admin, visit, work_item


async def test_add_item_creates_part_item_with_correct_fields(session):
    admin, visit, work_item = await _setup_visit_with_work_item(session)

    item = await PartItemService(session).add_item(
        visit.id,
        PartItemCreate(
            work_item_id=work_item.id,
            name="Фильтр масляный",
            article_number="OF-123",
            quantity=2,
            unit_price=350,
            availability_status=PartAvailability.ORDERED,
        ),
        admin,
    )

    assert item.id is not None
    assert item.visit_id == visit.id
    assert item.work_item_id == work_item.id
    assert item.name == "Фильтр масляный"
    assert item.article_number == "OF-123"
    assert item.quantity == 2
    assert float(item.unit_price) == 350
    assert item.availability_status == PartAvailability.ORDERED


async def test_add_item_recalculates_visit_total(session):
    admin, visit, work_item = await _setup_visit_with_work_item(session)

    await PartItemService(session).add_item(
        visit.id,
        PartItemCreate(work_item_id=work_item.id, name="Масло", quantity=3, unit_price=600),
        admin,
    )

    updated_visit = await VisitService(session).get(visit.id)
    assert float(updated_visit.total_amount) == 3 * 600
