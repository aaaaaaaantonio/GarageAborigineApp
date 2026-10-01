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


async def _visit_with_work_item(session):
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
    return admin, visit


async def test_get_visit_document_returns_generated_pdf_bytes(session, tmp_path):
    admin, visit = await _visit_with_work_item(session)
    service = DocumentService(session, storage=LocalFileStorage(root=str(tmp_path)))
    await service.generate_visit_document(visit.id)

    pdf_bytes = await service.get_visit_document(visit.id)

    assert pdf_bytes.startswith(b"%PDF")


async def test_get_visit_document_not_generated_raises(session, tmp_path):
    from app.core.exceptions import DocumentNotFound

    admin, visit = await _visit_with_work_item(session)
    service = DocumentService(session, storage=LocalFileStorage(root=str(tmp_path)))

    with pytest.raises(DocumentNotFound):
        await service.get_visit_document(visit.id)


async def test_document_file_route_returns_pdf(session, tmp_path, monkeypatch):
    from httpx import ASGITransport, AsyncClient

    from app.core.db import get_session
    from app.main import app
    from app.modules.documents import service as documents_service

    monkeypatch.setattr(documents_service, "LocalFileStorage", lambda: LocalFileStorage(root=str(tmp_path)))
    admin, visit = await _visit_with_work_item(session)

    async def override_get_session():
        yield session

    app.dependency_overrides[get_session] = override_get_session
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers = {"X-User-Id": str(admin.id)}
            generated = await client.post(f"/visits/{visit.id}/document", headers=headers)
            document_id = generated.json()["document_id"]
            resp = await client.get(f"/documents/{document_id}/file", headers=headers)
            missing = await client.get(f"/documents/{uuid.uuid4()}/file", headers=headers)
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF")
    assert missing.status_code == 404
