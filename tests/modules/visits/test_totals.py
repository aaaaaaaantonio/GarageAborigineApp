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


async def test_total_amount_recalculates_after_adding_work_and_parts(session):
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

    work_item = await WorkItemService(session).add_item(
        visit.id,
        WorkItemCreate(free_text_name="Замена масла", category=WorkCategory.MAINTENANCE, norm_hours=1.0, hourly_rate=1500),
        admin,
    )
    await PartItemService(session).add_item(
        visit.id,
        PartItemCreate(work_item_id=work_item.id, name="Масло", quantity=4, unit_price=500, availability_status=PartAvailability.IN_STOCK),
        admin,
    )

    updated_visit = await VisitService(session).get(visit.id)
    assert float(updated_visit.total_amount) == 1500 * 1.0 + 4 * 500
