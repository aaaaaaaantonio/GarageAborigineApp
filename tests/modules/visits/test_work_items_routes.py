import pytest
from httpx import ASGITransport, AsyncClient

from app.core.db import get_session
from app.core.enums import VisitStatus, WorkItemStatus
from app.main import app
from app.modules.visits.models import Visit
from tests.modules.visits.test_work_items import _setup_visit_with_mechanic
from tests.helpers import staff_headers


@pytest.fixture
def api_app(session):
    async def override_get_session():
        yield session

    app.dependency_overrides[get_session] = override_get_session
    yield app
    app.dependency_overrides.clear()


async def test_list_work_items_route_returns_resolved_name_and_visit_id(api_app, session):
    admin, mechanic_a, mechanic_b, item = await _setup_visit_with_mechanic(session)

    transport = ASGITransport(app=api_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"/visits/{item.visit_id}/work-items", headers=staff_headers(admin.id))

    assert resp.status_code == 200
    body = resp.json()
    assert body[0]["name"] == "Замена масла"
    assert body[0]["visit_id"] == str(item.visit_id)


async def test_add_work_item_route_rejects_non_mechanic_assignee_with_422(api_app, session):
    admin, mechanic_a, mechanic_b, item = await _setup_visit_with_mechanic(session)

    transport = ASGITransport(app=api_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"/visits/{item.visit_id}/work-items",
            json={
                "free_text_name": "Диагностика",
                "category": "maintenance",
                "norm_hours": 1.0,
                "hourly_rate": 1500,
                "assigned_mechanic_id": str(admin.id),
            },
            headers=staff_headers(admin.id),
        )

    assert resp.status_code == 422
    assert "MECHANIC" in resp.json()["detail"]


async def test_list_done_route_returns_closed_work_for_mechanic(api_app, session):
    admin, mechanic_a, mechanic_b, item = await _setup_visit_with_mechanic(session)
    item.status = WorkItemStatus.READY
    visit = await session.get(Visit, item.visit_id)
    visit.status = VisitStatus.ISSUED
    await session.flush()

    transport = ASGITransport(app=api_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/work-items/mine/done", headers=staff_headers(mechanic_a.id))
        forbidden = await client.get("/work-items/mine/done", headers=staff_headers(admin.id))

    assert resp.status_code == 200
    body = resp.json()
    assert [w["id"] for w in body] == [str(item.id)]
    assert body[0]["name"] == "Замена масла"
    assert body[0]["plate_number"] == "А123"
    assert body[0]["make_model"] == "Toyota Camry"
    assert body[0]["visit_status"] == "issued"
    assert body[0]["visit_date"]
    assert forbidden.status_code == 403
