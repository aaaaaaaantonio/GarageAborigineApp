import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.db import get_session
from app.core.enums import UserRole, WorkCategory
from app.main import app
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
from tests.helpers import staff_headers


@pytest.fixture
def api_app(session):
    async def override_get_session():
        yield session

    app.dependency_overrides[get_session] = override_get_session
    yield app
    app.dependency_overrides.clear()


async def _get(api_app, path, user):
    async with AsyncClient(transport=ASGITransport(app=api_app), base_url="http://test") as client:
        return await client.get(path, headers=staff_headers(user.id))


@pytest.fixture
async def world(session):
    admin = User(role=UserRole.ADMIN, full_name="Админ", branch_id=uuid.uuid4())
    master = User(role=UserRole.MASTER, full_name="Мастер", branch_id=uuid.uuid4())
    mechanic = User(role=UserRole.MECHANIC, full_name="Сидоров", branch_id=uuid.uuid4())
    session.add_all([admin, master, mechanic])
    await session.flush()
    client = await ClientService(session).create_client(ClientCreate(full_name="Иван", phone="79991230001"), admin)
    vehicle = await VehicleService(session).create_vehicle(
        VehicleCreate(vin="B" * 17, plate_number="А123ВС77", make="Toyota", model="Camry"), admin
    )
    visit = await VisitService(session).create_visit(
        VisitCreate(client_id=client.id, vehicle_id=vehicle.id, assigned_master_id=master.id, mileage_at_intake=1000),
        admin,
    )
    works = WorkItemService(session)
    oil = await works.add_item(
        visit.id,
        WorkItemCreate(free_text_name="Замена масла", category=WorkCategory.MAINTENANCE, norm_hours=0.5,
                       hourly_rate=2400, assigned_mechanic_id=mechanic.id),
        admin,
    )
    pads = await works.add_item(
        visit.id,
        WorkItemCreate(free_text_name="Колодки", category=WorkCategory.CHASSIS, norm_hours=1.2, hourly_rate=2000),
        admin,
    )
    parts = PartItemService(session)
    await parts.add_item(visit.id, PartItemCreate(work_item_id=oil.id, name="Фильтр", quantity=1, unit_price=450.5), admin)
    await parts.add_item(visit.id, PartItemCreate(work_item_id=oil.id, name="Масло 5W30", quantity=4, unit_price=900), admin)
    await session.flush()
    return admin, master, mechanic, visit, oil, pads


async def test_lines_have_prices_parts_and_totals(api_app, world, session):
    _, master, _, visit, oil, pads = world
    resp = await _get(api_app, f"/visits/{visit.id}/lines", master)
    assert resp.status_code == 200
    body = resp.json()
    works = {w["name"]: w for w in body["works"]}
    assert sorted(works) == ["Замена масла", "Колодки"]
    first, second = works["Замена масла"], works["Колодки"]
    assert first["amount"] == 1200.0
    assert first["assigned_mechanic_name"] == "Сидоров"
    assert [(p["name"], p["quantity"], p["amount"]) for p in first["parts"]] == [
        ("Масло 5W30", 4, 3600.0),
        ("Фильтр", 1, 450.5),
    ]
    assert second["amount"] == 2400.0 and second["parts"] == []
    assert body["works_total"] == 3600.0
    assert body["parts_total"] == 4050.5
    assert body["discount"] == 0.0
    assert body["total"] == 7650.5
    await session.refresh(visit)
    assert float(visit.total_amount) == body["total"]


async def test_mechanic_forbidden(api_app, world):
    _, _, mechanic, visit, _, _ = world
    assert (await _get(api_app, f"/visits/{visit.id}/lines", mechanic)).status_code == 403


async def test_unknown_visit_404(api_app, world):
    _, master, _, _, _, _ = world
    assert (await _get(api_app, f"/visits/{uuid.uuid4()}/lines", master)).status_code == 404
