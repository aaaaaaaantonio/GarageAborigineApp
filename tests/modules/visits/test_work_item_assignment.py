import uuid
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.db import get_session
from app.core.enums import UserRole
from app.core.exceptions import InvalidAssignedMechanic, WorkItemNotFound
from app.main import app
from app.modules.notifications.logging_sender import NotificationOutbox
from app.modules.users.models import User
from app.modules.visits.work_items_schemas import WorkItemOut
from app.modules.visits.work_items_service import WorkItemService
from tests.modules.visits.test_work_items import _audit_rows, _new_work_item, _setup_visit_with_mechanic


async def _outbox(session, kind):
    rows = (await session.execute(select(NotificationOutbox).where(NotificationOutbox.kind == kind))).scalars()
    return [r.payload for r in rows]


# --- service ---


async def test_assign_mechanic_moves_item_to_new_mechanic(session):
    admin, mechanic_a, mechanic_b, item = await _setup_visit_with_mechanic(session)

    updated = await WorkItemService(session).assign_mechanic(item.visit_id, item.id, mechanic_b.id, admin)

    assert updated.assigned_mechanic_id == mechanic_b.id
    assert updated.assigned_mechanic_name == "Механик Б"
    assert [i.id for i in await WorkItemService(session).list_mine(mechanic_b)] == [item.id]
    assert await WorkItemService(session).list_mine(mechanic_a) == []


async def test_assign_mechanic_none_unassigns(session):
    admin, mechanic_a, mechanic_b, item = await _setup_visit_with_mechanic(session)

    updated = await WorkItemService(session).assign_mechanic(item.visit_id, item.id, None, admin)

    assert updated.assigned_mechanic_id is None
    assert updated.assigned_mechanic_name is None


@pytest.mark.parametrize("who", ["master", "unknown", "deleted_mechanic"])
async def test_assign_mechanic_rejects_invalid_mechanic(session, who):
    admin, mechanic_a, mechanic_b, item = await _setup_visit_with_mechanic(session)
    if who == "master":
        assignee = User(role=UserRole.MASTER, full_name="Мастер 2", branch_id=uuid.uuid4())
        session.add(assignee)
        await session.flush()
        assignee_id = assignee.id
    elif who == "unknown":
        assignee_id = uuid.uuid4()
    else:
        mechanic_b.deleted_at = datetime.now(timezone.utc)
        await session.flush()
        assignee_id = mechanic_b.id

    with pytest.raises(InvalidAssignedMechanic):
        await WorkItemService(session).assign_mechanic(item.visit_id, item.id, assignee_id, admin)


async def test_assign_mechanic_item_of_other_visit_raises_not_found(session):
    admin, mechanic_a, mechanic_b, item = await _setup_visit_with_mechanic(session)
    with pytest.raises(WorkItemNotFound):
        await WorkItemService(session).assign_mechanic(uuid.uuid4(), item.id, mechanic_b.id, admin)


async def test_assign_mechanic_unknown_item_raises_not_found(session):
    admin, mechanic_a, mechanic_b, item = await _setup_visit_with_mechanic(session)
    with pytest.raises(WorkItemNotFound):
        await WorkItemService(session).assign_mechanic(item.visit_id, uuid.uuid4(), mechanic_b.id, admin)


async def test_assign_mechanic_is_audited(session):
    admin, mechanic_a, mechanic_b, item = await _setup_visit_with_mechanic(session)
    await WorkItemService(session).assign_mechanic(item.visit_id, item.id, mechanic_b.id, admin)

    rows = await _audit_rows(session, item.id, "assign_mechanic")
    assert len(rows) == 1
    assert rows[0].user_id == admin.id
    assert rows[0].old_value == {"assigned_mechanic_id": str(mechanic_a.id)}
    assert rows[0].new_value == {"assigned_mechanic_id": str(mechanic_b.id)}


async def test_assign_same_mechanic_is_a_no_op(session):
    admin, mechanic_a, mechanic_b, item = await _setup_visit_with_mechanic(session)
    assigned_before = await _outbox(session, "work_assigned")

    await WorkItemService(session).assign_mechanic(item.visit_id, item.id, mechanic_a.id, admin)

    assert await _audit_rows(session, item.id, "assign_mechanic") == []
    assert await _outbox(session, "work_assigned") == assigned_before
    assert await _outbox(session, "work_unassigned") == []


async def test_work_item_out_carries_mechanic(session):
    admin, mechanic_a, mechanic_b, item = await _setup_visit_with_mechanic(session)

    [listed] = await WorkItemService(session).list_for_visit(item.visit_id)
    out = WorkItemOut.model_validate(listed)

    assert out.assigned_mechanic_id == mechanic_a.id
    assert out.assigned_mechanic_name == "Механик А"


# --- notifications (outbox; no bot token in tests) ---


async def test_add_item_with_mechanic_notifies_mechanic(session):
    admin, mechanic_a, mechanic_b, item = await _setup_visit_with_mechanic(session)

    assert await _outbox(session, "work_assigned") == [
        {"work_item_id": str(item.id), "visit_id": str(item.visit_id), "mechanic_id": str(mechanic_a.id)}
    ]


async def test_add_item_without_mechanic_notifies_nobody(session):
    admin, mechanic_a, mechanic_b, item = await _setup_visit_with_mechanic(session)
    created = await WorkItemService(session).add_item(item.visit_id, await _new_work_item(None), admin)

    assert all(p["work_item_id"] != str(created.id) for p in await _outbox(session, "work_assigned"))


async def test_reassign_notifies_new_and_old_mechanic(session):
    admin, mechanic_a, mechanic_b, item = await _setup_visit_with_mechanic(session)
    await WorkItemService(session).assign_mechanic(item.visit_id, item.id, mechanic_b.id, admin)

    assigned = await _outbox(session, "work_assigned")
    assert assigned[-1]["mechanic_id"] == str(mechanic_b.id)
    assert await _outbox(session, "work_unassigned") == [
        {"work_item_id": str(item.id), "visit_id": str(item.visit_id), "mechanic_id": str(mechanic_a.id)}
    ]


async def test_unassign_notifies_only_old_mechanic(session):
    admin, mechanic_a, mechanic_b, item = await _setup_visit_with_mechanic(session)
    await WorkItemService(session).assign_mechanic(item.visit_id, item.id, None, admin)

    assert len(await _outbox(session, "work_assigned")) == 1  # only the original creation
    assert [p["mechanic_id"] for p in await _outbox(session, "work_unassigned")] == [str(mechanic_a.id)]


# --- route ---


@pytest.fixture
def api_app(session):
    async def override_get_session():
        yield session

    app.dependency_overrides[get_session] = override_get_session
    yield app
    app.dependency_overrides.clear()


async def _patch_mechanic(item, user, mechanic_id, visit_id=None):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.patch(
            f"/visits/{visit_id or item.visit_id}/work-items/{item.id}/mechanic",
            json={"assigned_mechanic_id": str(mechanic_id) if mechanic_id else None},
            headers={"X-User-Id": str(user.id)},
        )


async def test_route_reassigns_mechanic(api_app, session):
    admin, mechanic_a, mechanic_b, item = await _setup_visit_with_mechanic(session)

    resp = await _patch_mechanic(item, admin, mechanic_b.id)

    assert resp.status_code == 200
    assert resp.json()["assigned_mechanic_id"] == str(mechanic_b.id)
    assert resp.json()["assigned_mechanic_name"] == "Механик Б"


async def test_route_unassigns_mechanic(api_app, session):
    admin, mechanic_a, mechanic_b, item = await _setup_visit_with_mechanic(session)

    resp = await _patch_mechanic(item, admin, None)

    assert resp.status_code == 200
    assert resp.json()["assigned_mechanic_id"] is None


async def test_route_forbids_mechanic(api_app, session):
    admin, mechanic_a, mechanic_b, item = await _setup_visit_with_mechanic(session)

    resp = await _patch_mechanic(item, mechanic_a, mechanic_b.id)

    assert resp.status_code == 403


async def test_route_rejects_non_mechanic_with_422(api_app, session):
    admin, mechanic_a, mechanic_b, item = await _setup_visit_with_mechanic(session)

    resp = await _patch_mechanic(item, admin, admin.id)

    assert resp.status_code == 422


async def test_route_item_of_other_visit_is_404(api_app, session):
    admin, mechanic_a, mechanic_b, item = await _setup_visit_with_mechanic(session)

    resp = await _patch_mechanic(item, admin, mechanic_b.id, visit_id=uuid.uuid4())

    assert resp.status_code == 404
