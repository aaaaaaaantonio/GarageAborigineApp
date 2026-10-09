import uuid
from datetime import date, datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.db import get_session
from app.core.enums import UserRole
from app.main import app
from app.modules.clients.schemas import ClientCreate
from app.modules.clients.service import ClientService
from app.modules.users.models import User
from app.modules.vehicles.schemas import OwnershipCreate, VehicleCreate
from app.modules.vehicles.service import VehicleService


@pytest.fixture
def api_app(session):
    async def override_get_session():
        yield session

    app.dependency_overrides[get_session] = override_get_session
    yield app
    app.dependency_overrides.clear()


async def _get(api_app, path, user):
    transport = ASGITransport(app=api_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(path, headers={"X-User-Id": str(user.id)})


async def _world(session):
    admin = User(role=UserRole.ADMIN, full_name="Админ", branch_id=uuid.uuid4())
    mechanic = User(role=UserRole.MECHANIC, full_name="Механик", branch_id=uuid.uuid4())
    session.add_all([admin, mechanic])
    await session.flush()
    client = await ClientService(session).create_client(
        ClientCreate(full_name="Иванов Пётр", phone="79990000011"), admin
    )
    return admin, mechanic, client


async def _vehicle(session, admin, vin_char, plate):
    return await VehicleService(session).create_vehicle(
        VehicleCreate(vin=vin_char * 17, plate_number=plate, make="Toyota", model="Camry"), admin
    )


async def _own(session, admin, vehicle, client, date_to=None):
    ownership = await VehicleService(session).attach_owner(
        vehicle.id, OwnershipCreate(client_id=client.id, date_from=date(2026, 1, 1)), admin
    )
    ownership.date_to = date_to
    await session.flush()
    return ownership


async def test_client_vehicles_lists_current_ownerships_sorted_by_plate(api_app, session):
    admin, mechanic, client = await _world(session)
    second = await _vehicle(session, admin, "B", "О555ОО77")
    first = await _vehicle(session, admin, "A", "А111АА77")
    sold = await _vehicle(session, admin, "C", "Е222ЕЕ77")
    gone = await _vehicle(session, admin, "D", "К333КК77")
    for v in (second, first):
        await _own(session, admin, v, client)
    await _own(session, admin, sold, client, date_to=date(2026, 5, 1))
    await _own(session, admin, gone, client)
    gone.deleted_at = datetime.now(timezone.utc)
    await session.flush()

    resp = await _get(api_app, f"/clients/{client.id}/vehicles", admin)

    assert resp.status_code == 200
    assert [v["id"] for v in resp.json()] == [str(first.id), str(second.id)]


async def test_client_vehicles_404_for_unknown_client(api_app, session):
    admin, mechanic, client = await _world(session)

    resp = await _get(api_app, f"/clients/{uuid.uuid4()}/vehicles", admin)

    assert resp.status_code == 404


async def test_vehicle_owner_returns_current_owner(api_app, session):
    admin, mechanic, client = await _world(session)
    previous = await ClientService(session).create_client(
        ClientCreate(full_name="Прежний", phone="79990000012"), admin
    )
    vehicle = await _vehicle(session, admin, "A", "А111АА77")
    await _own(session, admin, vehicle, previous, date_to=date(2026, 3, 1))
    await _own(session, admin, vehicle, client)

    resp = await _get(api_app, f"/vehicles/{vehicle.id}/owner", admin)

    assert resp.status_code == 200
    assert resp.json()["id"] == str(client.id)
    assert resp.json()["full_name"] == "Иванов Пётр"


async def test_vehicle_owner_is_null_without_current_owner(api_app, session):
    admin, mechanic, client = await _world(session)
    vehicle = await _vehicle(session, admin, "A", "А111АА77")

    resp = await _get(api_app, f"/vehicles/{vehicle.id}/owner", admin)

    assert resp.status_code == 200
    assert resp.json() is None


async def test_vehicle_owner_404_for_unknown_vehicle(api_app, session):
    admin, mechanic, client = await _world(session)

    resp = await _get(api_app, f"/vehicles/{uuid.uuid4()}/owner", admin)

    assert resp.status_code == 404


async def test_mechanic_can_read_vehicle_but_not_owner_or_client_data(api_app, session):
    admin, mechanic, client = await _world(session)
    vehicle = await _vehicle(session, admin, "A", "А111АА77")
    await _own(session, admin, vehicle, client)

    vehicle_resp = await _get(api_app, f"/vehicles/{vehicle.id}", mechanic)
    owner_resp = await _get(api_app, f"/vehicles/{vehicle.id}/owner", mechanic)
    client_resp = await _get(api_app, f"/clients/{client.id}", mechanic)
    vehicles_resp = await _get(api_app, f"/clients/{client.id}/vehicles", mechanic)

    assert vehicle_resp.status_code == 200
    assert set(vehicle_resp.json()) == {"id", "vin", "plate_number", "make", "model", "mileage_current"}
    assert owner_resp.status_code == 403
    assert client_resp.status_code == 403
    assert vehicles_resp.status_code == 403


async def _post_vehicle(api_app, user, vin):
    transport = ASGITransport(app=api_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post(
            "/vehicles",
            json={"vin": vin, "plate_number": "А123ВС77", "make": "Toyota", "model": "Camry"},
            headers={"X-User-Id": str(user.id)},
        )


async def test_create_vehicle_normalizes_vin_and_accepts_frame_number(api_app, session):
    admin, _, _ = await _world(session)

    strict = await _post_vehicle(api_app, admin, "jtdbr32e 720012345")
    frame = await _post_vehicle(api_app, admin, "GX110-6012345")

    assert strict.status_code == 201
    assert strict.json()["vin"] == "JTDBR32E720012345"
    assert frame.status_code == 201


async def test_create_vehicle_rejects_invalid_vin(api_app, session):
    admin, _, _ = await _world(session)

    response = await _post_vehicle(api_app, admin, "А123ВС77")

    assert response.status_code == 422
    assert "vin" in response.text.lower()


async def test_create_vehicle_duplicate_vin_returns_409(api_app, session):
    admin, _, _ = await _world(session)

    await _post_vehicle(api_app, admin, "JTDBR32E720012345")
    second = await _post_vehicle(api_app, admin, "JTDBR32E720012345")

    assert second.status_code == 409
    assert "VIN" in second.json()["detail"]
