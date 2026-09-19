import uuid
from pathlib import Path

import pytest

from app.core.enums import UserRole, WorkCategory
from app.core.exceptions import VisitNotFound
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


async def test_generate_visit_document_sets_document_url(session, tmp_path):
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
    await WorkItemService(session).add_item(
        visit.id,
        WorkItemCreate(free_text_name="Замена масла", category=WorkCategory.MAINTENANCE, norm_hours=1.0, hourly_rate=1500),
        admin,
    )

    storage = LocalFileStorage(root=str(tmp_path))
    url = await DocumentService(session, storage=storage).generate_visit_document(visit.id)

    assert url is not None
    updated_visit = await VisitService(session).get(visit.id)
    assert updated_visit.document_url == url

    pdf_bytes = Path(url).read_bytes()
    assert len(pdf_bytes) > 0
    assert pdf_bytes.startswith(b"%PDF")


async def test_generate_document_unknown_visit_raises_not_found(session, tmp_path):
    storage = LocalFileStorage(root=str(tmp_path))
    with pytest.raises(VisitNotFound):
        await DocumentService(session, storage=storage).generate_visit_document(uuid.uuid4())
