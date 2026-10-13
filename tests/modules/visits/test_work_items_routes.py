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
    assert body["count"] == 1 and body["total_norm_hours"] == 1.0 and body["has_more"] is False
    items = body["items"]
    assert [w["id"] for w in items] == [str(item.id)]
    assert items[0]["name"] == "Замена масла"
    assert items[0]["plate_number"] == "А123"
    assert items[0]["make_model"] == "Toyota Camry"
    assert items[0]["visit_status"] == "issued"
    assert items[0]["visit_date"] and items[0]["closed_at"]
    assert items[0]["norm_hours"] == 1.0
    assert "amount" not in items[0] and "hourly_rate" not in items[0]
    assert forbidden.status_code == 403


async def test_mine_route_accepts_status_and_sort(api_app, session):
    admin, mechanic_a, mechanic_b, item = await _setup_visit_with_mechanic(session)
    transport = ASGITransport(app=api_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        hit = await client.get("/work-items/mine?status=not_ready&sort=car", headers=staff_headers(mechanic_a.id))
        miss = await client.get("/work-items/mine?status=ready", headers=staff_headers(mechanic_a.id))
        bad = await client.get("/work-items/mine?sort=bogus", headers=staff_headers(mechanic_a.id))

    assert [w["id"] for w in hit.json()] == [str(item.id)]
    assert miss.json() == []
    assert bad.status_code == 422


async def test_done_route_accepts_since_and_outcome(api_app, session):
    admin, mechanic_a, mechanic_b, item = await _setup_visit_with_mechanic(session)
    item.status = WorkItemStatus.READY
    visit = await session.get(Visit, item.visit_id)
    visit.status = VisitStatus.CANCELLED
    await session.flush()
    transport = ASGITransport(app=api_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        issued = await client.get("/work-items/mine/done?outcome=issued", headers=staff_headers(mechanic_a.id))
        cancelled = await client.get("/work-items/mine/done?outcome=cancelled&since=2000-01-01T00:00:00Z",
                                     headers=staff_headers(mechanic_a.id))
        bad = await client.get("/work-items/mine/done?outcome=ready", headers=staff_headers(mechanic_a.id))

    assert issued.json()["items"] == []
    assert [w["id"] for w in cancelled.json()["items"]] == [str(item.id)]
    assert bad.status_code == 422
