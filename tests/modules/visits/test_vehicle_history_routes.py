import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.db import get_session
from app.core.enums import UserRole, VisitStatus, WorkCategory
from app.main import app
from app.modules.catalog.models import WorkCatalog
from app.modules.clients.schemas import ClientCreate
from app.modules.clients.service import ClientService
from app.modules.users.models import User
from app.modules.vehicles.schemas import VehicleCreate
from app.modules.vehicles.service import VehicleService
from app.modules.visits.schemas import VisitCreate
from app.modules.visits.service import VisitService
from app.modules.visits.work_items_schemas import WorkItemCreate
from app.modules.visits.work_items_service import WORK_HISTORY_LIMIT, WorkItemService

BASE = datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc)


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
    master = User(role=UserRole.MASTER, full_name="Мастер", branch_id=uuid.uuid4())
    mechanic = User(role=UserRole.MECHANIC, full_name="Механик", branch_id=uuid.uuid4())
    session.add_all([admin, master, mechanic])
    await session.flush()
    client = await ClientService(session).create_client(
        ClientCreate(full_name="Иванов", phone="79990000031"), admin
    )
    vehicle = await VehicleService(session).create_vehicle(
        VehicleCreate(vin="H" * 17, plate_number="Н123НН77", make="Toyota", model="Camry"), admin
    )
    return admin, master, mechanic, client, vehicle


async def _visit(session, admin, master, client, vehicle, hours, mileage, status=VisitStatus.RECEIVED):
    visit = await VisitService(session).create_visit(
        VisitCreate(
            client_id=client.id,
            vehicle_id=vehicle.id,
            assigned_master_id=master.id,
            mileage_at_intake=mileage,
            mileage_manually_confirmed=True,
        ),
        admin,
    )
    visit.created_at = BASE + timedelta(hours=hours)
    visit.status = status
    await session.flush()
    return visit


async def _work(session, admin, visit, *, name=None, catalog_item_id=None):
    return await WorkItemService(session).add_item(
        visit.id,
        WorkItemCreate(
            free_text_name=name,
            catalog_item_id=catalog_item_id,
            category=WorkCategory.MAINTENANCE,
            norm_hours=1.5,
            hourly_rate=2000,
        ),
        admin,
    )


async def test_history_lists_works_newest_visit_first_with_catalog_names(api_app, session):
    admin, master, mechanic, client, vehicle = await _world(session)
    catalog = WorkCatalog(
        name="Замена масла ДВС", category=WorkCategory.MAINTENANCE, default_norm_hours=1, created_by_user_id=admin.id
    )
    session.add(catalog)
    await session.flush()
    old = await _visit(session, admin, master, client, vehicle, hours=1, mileage=76_200)
    await _work(session, admin, old, name="Диагностика подвески")
    new = await _visit(session, admin, master, client, vehicle, hours=48, mileage=84_500)
    await _work(session, admin, new, catalog_item_id=catalog.id)
    await _work(session, admin, new, name="Замена фильтра салона")

    resp = await _get(api_app, f"/vehicles/{vehicle.id}/work-history", master)

    assert resp.status_code == 200
    items = resp.json()["items"]
    assert [i["visit_id"] for i in items] == [str(new.id), str(new.id), str(old.id)]
    assert {i["name"] for i in items[:2]} == {"Замена масла ДВС", "Замена фильтра салона"}
    assert items[2] == {
        "visit_id": str(old.id),
        "visit_at": items[2]["visit_at"],
        "mileage": 76_200,
        "name": "Диагностика подвески",
        "status": "not_ready",
    }
    assert items[2]["visit_at"].startswith("2026-09-01T10:00:00")
    assert resp.json()["has_more"] is False


async def test_history_excludes_cancelled_and_deleted_visits(api_app, session):
    admin, master, mechanic, client, vehicle = await _world(session)
    cancelled = await _visit(session, admin, master, client, vehicle, hours=1, mileage=1000, status=VisitStatus.CANCELLED)
    await _work(session, admin, cancelled, name="Отменённая работа")
    deleted = await _visit(session, admin, master, client, vehicle, hours=2, mileage=1000)
    await _work(session, admin, deleted, name="Удалённая работа")
    deleted.deleted_at = BASE
    kept = await _visit(session, admin, master, client, vehicle, hours=3, mileage=1000)
    await _work(session, admin, kept, name="Нормальная работа")
    await session.flush()

    resp = await _get(api_app, f"/vehicles/{vehicle.id}/work-history", master)

    assert [i["name"] for i in resp.json()["items"]] == ["Нормальная работа"]


async def test_history_has_no_price_or_client_fields_and_is_open_to_mechanic(api_app, session):
    admin, master, mechanic, client, vehicle = await _world(session)
    visit = await _visit(session, admin, master, client, vehicle, hours=1, mileage=1000)
    await _work(session, admin, visit, name="Работа")

    resp = await _get(api_app, f"/vehicles/{vehicle.id}/work-history", mechanic)

    assert resp.status_code == 200
    assert set(resp.json()) == {"items", "has_more"}
    assert set(resp.json()["items"][0]) == {"visit_id", "visit_at", "mileage", "name", "status"}


async def test_history_reports_has_more_over_limit(api_app, session):
    admin, master, mechanic, client, vehicle = await _world(session)
    visit = await _visit(session, admin, master, client, vehicle, hours=1, mileage=1000)
    for n in range(WORK_HISTORY_LIMIT + 1):
        await _work(session, admin, visit, name=f"Работа {n}")

    resp = await _get(api_app, f"/vehicles/{vehicle.id}/work-history", master)

    assert len(resp.json()["items"]) == WORK_HISTORY_LIMIT
    assert resp.json()["has_more"] is True


async def test_history_404_for_unknown_vehicle(api_app, session):
    admin, master, mechanic, client, vehicle = await _world(session)

    resp = await _get(api_app, f"/vehicles/{uuid.uuid4()}/work-history", master)

    assert resp.status_code == 404
