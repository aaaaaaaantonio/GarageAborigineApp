import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.db import get_session
from app.core.enums import UserRole
from app.main import app
from app.modules.clients.schemas import ClientCreate
from app.modules.clients.service import ClientService
from app.modules.users.models import User
from app.modules.vehicles.schemas import VehicleCreate
from app.modules.vehicles.service import VehicleService


@pytest.fixture
def api_app(session):
    async def override_get_session():
        yield session

    app.dependency_overrides[get_session] = override_get_session
    yield app
    app.dependency_overrides.clear()


async def _search(api_app, query, user):
    transport = ASGITransport(app=api_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get("/search", params={"q": query}, headers={"X-User-Id": str(user.id)})


async def _world(session):
    master = User(role=UserRole.MASTER, full_name="Мастер", branch_id=uuid.uuid4())
    mechanic = User(role=UserRole.MECHANIC, full_name="Механик", branch_id=uuid.uuid4())
    session.add_all([master, mechanic])
    await session.flush()
    await ClientService(session).create_client(ClientCreate(full_name="Сидоров Олег", phone="79990000021"), master)
    vehicle = await VehicleService(session).create_vehicle(
        VehicleCreate(vin="M" * 17, plate_number="М777ММ77", make="Mazda", model="CX-5"), master
    )
    return master, mechanic, vehicle


async def test_mechanic_search_by_client_phone_or_name_finds_nothing(api_app, session):
    master, mechanic, vehicle = await _world(session)

    by_phone = await _search(api_app, "79990000021", mechanic)
    by_name = await _search(api_app, "Сидоров Олег", mechanic)

    assert by_phone.status_code == 200
    assert by_phone.json() == []
    assert by_name.json() == []


async def test_mechanic_search_by_plate_finds_vehicle(api_app, session):
    master, mechanic, vehicle = await _world(session)

    resp = await _search(api_app, "М777ММ77", mechanic)

    assert [(r["entity"], r["id"]) for r in resp.json()] == [("vehicle", str(vehicle.id))]


async def test_master_search_by_phone_still_finds_client(api_app, session):
    master, mechanic, vehicle = await _world(session)

    resp = await _search(api_app, "79990000021", master)

    assert [r["entity"] for r in resp.json()] == ["client"]
