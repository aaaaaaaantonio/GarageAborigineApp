import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.db import get_session
from app.core.enums import UserRole, VisitStatus
from app.main import app
from app.modules.clients.schemas import ClientCreate
from app.modules.clients.service import ClientService
from app.modules.users.models import User
from app.modules.vehicles.schemas import VehicleCreate
from app.modules.vehicles.service import VehicleService
from app.modules.visits.schemas import VisitCreate
from app.modules.visits.service import VISIT_LIST_LIMIT, VisitService

BASE = datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc)


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
    me = User(role=UserRole.MASTER, full_name="Мастер Я", branch_id=uuid.uuid4())
    other = User(role=UserRole.MASTER, full_name="Мастер Другой", branch_id=uuid.uuid4())
    mechanic = User(role=UserRole.MECHANIC, full_name="Механик", branch_id=uuid.uuid4())
    session.add_all([admin, me, other, mechanic])
    await session.flush()
    client = await ClientService(session).create_client(
        ClientCreate(full_name="Иванов Пётр", phone="79990000001"), admin
    )
    vehicle = await VehicleService(session).create_vehicle(
        VehicleCreate(vin="A" * 17, plate_number="А123ВС77", make="Toyota", model="Camry"), admin
    )
    return admin, me, other, mechanic, client, vehicle


async def _visit(session, admin, client, vehicle, master, hours, status=VisitStatus.RECEIVED):
    visit = await VisitService(session).create_visit(
        VisitCreate(
            client_id=client.id,
            vehicle_id=vehicle.id,
            assigned_master_id=master.id,
            mileage_at_intake=1000,
            mileage_manually_confirmed=True,
        ),
        admin,
    )
    visit.created_at = BASE + timedelta(hours=hours)
    visit.status = status
    await session.flush()
    return visit


async def test_list_active_puts_viewer_visits_first_then_newest(api_app, session):
    admin, me, other, mechanic, client, vehicle = await _world(session)
    mine_old = await _visit(session, admin, client, vehicle, me, hours=1)
    theirs_new = await _visit(session, admin, client, vehicle, other, hours=3)
    mine_new = await _visit(session, admin, client, vehicle, me, hours=2)

    resp = await _get(api_app, "/visits?active=true", me)

    assert resp.status_code == 200
    ids = [item["id"] for item in resp.json()["items"]]
    assert ids == [str(mine_new.id), str(mine_old.id), str(theirs_new.id)]
    assert resp.json()["has_more"] is False


async def test_list_active_excludes_issued_and_cancelled(api_app, session):
    admin, me, other, mechanic, client, vehicle = await _world(session)
    open_visit = await _visit(session, admin, client, vehicle, me, hours=1)
    await _visit(session, admin, client, vehicle, me, hours=2, status=VisitStatus.ISSUED)
    await _visit(session, admin, client, vehicle, me, hours=3, status=VisitStatus.CANCELLED)

    active = await _get(api_app, "/visits?active=true", me)
    everything = await _get(api_app, "/visits", me)

    assert [i["id"] for i in active.json()["items"]] == [str(open_visit.id)]
    assert len(everything.json()["items"]) == 3


async def test_list_filters_by_client_and_vehicle(api_app, session):
    admin, me, other, mechanic, client, vehicle = await _world(session)
    client2 = await ClientService(session).create_client(
        ClientCreate(full_name="Петрова Анна", phone="79990000002"), admin
    )
    vehicle2 = await VehicleService(session).create_vehicle(
        VehicleCreate(vin="B" * 17, plate_number="В001ОР50", make="Lada", model="Vesta"), admin
    )
    first = await _visit(session, admin, client, vehicle, me, hours=1)
    second = await _visit(session, admin, client2, vehicle2, me, hours=2)

    by_client = await _get(api_app, f"/visits?client_id={client.id}", me)
    by_vehicle = await _get(api_app, f"/visits?vehicle_id={vehicle2.id}", me)

    assert [i["id"] for i in by_client.json()["items"]] == [str(first.id)]
    assert [i["id"] for i in by_vehicle.json()["items"]] == [str(second.id)]


async def test_list_excludes_soft_deleted_visits_clients_vehicles(api_app, session):
    admin, me, other, mechanic, client, vehicle = await _world(session)
    deleted_visit = await _visit(session, admin, client, vehicle, me, hours=1)
    deleted_visit.deleted_at = BASE
    client2 = await ClientService(session).create_client(
        ClientCreate(full_name="Удалённый", phone="79990000003"), admin
    )
    await _visit(session, admin, client2, vehicle, me, hours=2)
    client2.deleted_at = BASE
    vehicle2 = await VehicleService(session).create_vehicle(
        VehicleCreate(vin="C" * 17, plate_number="Х999ХХ99", make="Kia", model="Rio"), admin
    )
    await _visit(session, admin, client, vehicle2, me, hours=3)
    vehicle2.deleted_at = BASE
    kept = await _visit(session, admin, client, vehicle, me, hours=4)
    await session.flush()

    resp = await _get(api_app, "/visits", me)

    assert [i["id"] for i in resp.json()["items"]] == [str(kept.id)]


async def test_list_reports_has_more_over_limit(api_app, session):
    admin, me, other, mechanic, client, vehicle = await _world(session)
    for hours in range(VISIT_LIST_LIMIT + 1):
        await _visit(session, admin, client, vehicle, me, hours=hours)

    resp = await _get(api_app, "/visits", me)

    assert len(resp.json()["items"]) == VISIT_LIST_LIMIT
    assert resp.json()["has_more"] is True


async def test_list_items_carry_summary_fields(api_app, session):
    admin, me, other, mechanic, client, vehicle = await _world(session)
    visit = await _visit(session, admin, client, vehicle, me, hours=1)

    item = (await _get(api_app, "/visits", admin)).json()["items"][0]

    assert item["id"] == str(visit.id)
    assert item["status"] == "received"
    assert item["client_id"] == str(client.id)
    assert item["client_name"] == "Иванов Пётр"
    assert item["vehicle_id"] == str(vehicle.id)
    assert item["plate_number"] == vehicle.plate_number
    assert item["make_model"] == "Toyota Camry"
    assert item["assigned_master_id"] == str(me.id)
    assert item["master_name"] == "Мастер Я"
    assert item["created_at"].startswith("2026-10-01T10:00:00")


async def test_list_forbidden_for_mechanic(api_app, session):
    admin, me, other, mechanic, client, vehicle = await _world(session)

    resp = await _get(api_app, "/visits", mechanic)

    assert resp.status_code == 403


async def test_get_visit_returns_summary(api_app, session):
    admin, me, other, mechanic, client, vehicle = await _world(session)
    visit = await _visit(session, admin, client, vehicle, me, hours=1)

    body = (await _get(api_app, f"/visits/{visit.id}", me)).json()

    assert body["client_name"] == "Иванов Пётр"
    assert body["master_name"] == "Мастер Я"
    assert body["make_model"] == "Toyota Camry"


async def test_create_and_change_status_routes_return_summary(api_app, session):
    admin, me, other, mechanic, client, vehicle = await _world(session)
    transport = ASGITransport(app=api_app)
    headers = {"X-User-Id": str(me.id)}
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        created = await http.post(
            "/visits",
            json={
                "client_id": str(client.id),
                "vehicle_id": str(vehicle.id),
                "assigned_master_id": str(me.id),
                "mileage_at_intake": 2000,
            },
            headers=headers,
        )
        changed = await http.patch(
            f"/visits/{created.json()['id']}/status", json={"new_status": "diagnostics"}, headers=headers
        )

    assert created.status_code == 201
    assert created.json()["plate_number"] == vehicle.plate_number
    assert changed.status_code == 200
    assert changed.json()["status"] == "diagnostics"
    assert changed.json()["client_name"] == "Иванов Пётр"
