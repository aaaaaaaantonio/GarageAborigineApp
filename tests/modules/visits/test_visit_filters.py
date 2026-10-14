from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import pytest

from app.core.enums import VisitStatus, WorkCategory, WorkItemStatus
from app.modules.visits.models import VisitStatusLog
from app.modules.visits.service import VISIT_LIST_LIMIT
from app.modules.visits.work_items_schemas import WorkItemCreate
from app.modules.visits.work_items_service import WorkItemService
from tests.modules.visits.test_visit_routes import BASE, _get, _visit, _world, api_app  # noqa: F401

NOW = datetime.now(timezone.utc)


def _ids(resp):
    assert resp.status_code == 200, resp.text
    return [item["id"] for item in resp.json()["items"]]


async def _log(session, visit, to_status, at):
    session.add(VisitStatusLog(visit_id=visit.id, to_status=to_status, changed_by_user_id=visit.assigned_master_id,
                               changed_at=at))
    await session.flush()


async def test_status_filter_is_repeatable(api_app, session):
    admin, me, other, mechanic, client, vehicle = await _world(session)
    a = await _visit(session, admin, client, vehicle, me, 1, VisitStatus.APPROVAL)
    b = await _visit(session, admin, client, vehicle, me, 2, VisitStatus.READY)
    await _visit(session, admin, client, vehicle, me, 3, VisitStatus.IN_PROGRESS)

    resp = await _get(api_app, "/visits?status=approval&status=ready", me)

    assert set(_ids(resp)) == {str(a.id), str(b.id)}


async def test_closed_returns_only_issued_and_cancelled(api_app, session):
    admin, me, other, mechanic, client, vehicle = await _world(session)
    issued = await _visit(session, admin, client, vehicle, me, 1, VisitStatus.ISSUED)
    cancelled = await _visit(session, admin, client, vehicle, me, 2, VisitStatus.CANCELLED)
    await _visit(session, admin, client, vehicle, me, 3, VisitStatus.READY)

    resp = await _get(api_app, "/visits?closed=true", me)

    assert set(_ids(resp)) == {str(issued.id), str(cancelled.id)}


async def test_master_filter(api_app, session):
    admin, me, other, mechanic, client, vehicle = await _world(session)
    await _visit(session, admin, client, vehicle, me, 1)
    theirs = await _visit(session, admin, client, vehicle, other, 2)

    resp = await _get(api_app, f"/visits?master_id={other.id}", admin)

    assert _ids(resp) == [str(theirs.id)]


async def test_unassigned_work_filter(api_app, session):
    admin, me, other, mechanic, client, vehicle = await _world(session)
    with_gap = await _visit(session, admin, client, vehicle, me, 1)
    staffed = await _visit(session, admin, client, vehicle, me, 2)
    await _visit(session, admin, client, vehicle, me, 3)  # no works at all
    service = WorkItemService(session)
    body = dict(free_text_name="Работа", category=WorkCategory.OTHER, norm_hours=1, hourly_rate=1000)
    await service.add_item(with_gap.id, WorkItemCreate(**body), admin)
    await service.add_item(with_gap.id, WorkItemCreate(**body, assigned_mechanic_id=mechanic.id), admin)
    await service.add_item(staffed.id, WorkItemCreate(**body, assigned_mechanic_id=mechanic.id), admin)

    resp = await _get(api_app, "/visits?unassigned_work=true", me)

    assert _ids(resp) == [str(with_gap.id)]


async def test_status_changed_at_falls_back_to_created_at_and_follows_the_log(api_app, session):
    admin, me, other, mechanic, client, vehicle = await _world(session)
    no_log = await _visit(session, admin, client, vehicle, me, 1)
    logged = await _visit(session, admin, client, vehicle, me, 2)
    await _log(session, logged, VisitStatus.DIAGNOSTICS, BASE + timedelta(days=1))
    await _log(session, logged, VisitStatus.APPROVAL, BASE + timedelta(days=2))

    items = {i["id"]: i for i in (await _get(api_app, "/visits", me)).json()["items"]}

    assert datetime.fromisoformat(items[str(no_log.id)]["status_changed_at"]) == no_log.created_at
    assert datetime.fromisoformat(items[str(logged.id)]["status_changed_at"]) == BASE + timedelta(days=2)


async def test_stale_filter_and_sort(api_app, session):
    admin, me, other, mechanic, client, vehicle = await _world(session)
    fresh = await _visit(session, admin, client, vehicle, me, 1, VisitStatus.IN_PROGRESS)
    await _log(session, fresh, VisitStatus.IN_PROGRESS, NOW - timedelta(hours=5))
    stuck = await _visit(session, admin, client, vehicle, me, 2, VisitStatus.WAITING_PARTS)
    await _log(session, stuck, VisitStatus.WAITING_PARTS, NOW - timedelta(days=5))
    stuck_longer = await _visit(session, admin, client, vehicle, me, 3, VisitStatus.APPROVAL)
    await _log(session, stuck_longer, VisitStatus.APPROVAL, NOW - timedelta(days=9))
    closed_long_ago = await _visit(session, admin, client, vehicle, me, 4, VisitStatus.ISSUED)
    await _log(session, closed_long_ago, VisitStatus.ISSUED, NOW - timedelta(days=30))

    stale = await _get(api_app, "/visits?stale=true", me)
    by_stale = await _get(api_app, "/visits?active=true&sort=stale", me)

    assert _ids(stale) == [str(stuck_longer.id), str(stuck.id)]
    assert _ids(by_stale) == [str(stuck_longer.id), str(stuck.id), str(fresh.id)]


async def test_work_movement_keeps_a_visit_from_being_stale(api_app, session):
    admin, me, other, mechanic, client, vehicle = await _world(session)
    worked_on = await _visit(session, admin, client, vehicle, me, 1, VisitStatus.IN_PROGRESS)
    await _log(session, worked_on, VisitStatus.IN_PROGRESS, NOW - timedelta(days=6))
    added_to = await _visit(session, admin, client, vehicle, me, 2, VisitStatus.IN_PROGRESS)
    await _log(session, added_to, VisitStatus.IN_PROGRESS, NOW - timedelta(days=6))
    idle = await _visit(session, admin, client, vehicle, me, 3, VisitStatus.IN_PROGRESS)
    await _log(session, idle, VisitStatus.IN_PROGRESS, NOW - timedelta(days=6))
    service = WorkItemService(session)
    body = dict(free_text_name="Работа", category=WorkCategory.OTHER, norm_hours=1, hourly_rate=1000)
    item = await service.add_item(worked_on.id, WorkItemCreate(**body), admin)
    item.created_at = NOW - timedelta(days=6)
    await session.flush()
    await service.update_status(item.id, WorkItemStatus.IN_PROGRESS, admin)
    old = await service.add_item(idle.id, WorkItemCreate(**body), admin)
    old.created_at = NOW - timedelta(days=6)
    await service.add_item(added_to.id, WorkItemCreate(**body), admin)
    await session.flush()

    stale = await _get(api_app, "/visits?stale=true", me)
    items = {i["id"]: i for i in (await _get(api_app, "/visits", me)).json()["items"]}

    assert _ids(stale) == [str(idle.id)]
    assert NOW - datetime.fromisoformat(items[str(worked_on.id)]["last_activity_at"]) < timedelta(hours=1)
    assert NOW - datetime.fromisoformat(items[str(idle.id)]["last_activity_at"]) > timedelta(days=5)


async def test_sort_by_status_follows_the_funnel(api_app, session):
    admin, me, other, mechanic, client, vehicle = await _world(session)
    ready = await _visit(session, admin, client, vehicle, me, 1, VisitStatus.READY)
    received = await _visit(session, admin, client, vehicle, me, 2, VisitStatus.RECEIVED)
    parts = await _visit(session, admin, client, vehicle, me, 3, VisitStatus.WAITING_PARTS)
    repair = await _visit(session, admin, client, vehicle, me, 4, VisitStatus.IN_PROGRESS)

    resp = await _get(api_app, "/visits?sort=status", me)

    assert _ids(resp) == [str(received.id), str(repair.id), str(parts.id), str(ready.id)]


async def test_sort_by_amount_and_issued_total(api_app, session):
    admin, me, other, mechanic, client, vehicle = await _world(session)
    small = await _visit(session, admin, client, vehicle, me, 1, VisitStatus.ISSUED)
    big = await _visit(session, admin, client, vehicle, me, 2, VisitStatus.ISSUED)
    cancelled = await _visit(session, admin, client, vehicle, me, 3, VisitStatus.CANCELLED)
    small.total_amount, big.total_amount, cancelled.total_amount = 1000, 5000, 9000
    await session.flush()

    resp = await _get(api_app, "/visits?closed=true&sort=amount", me)

    assert _ids(resp) == [str(cancelled.id), str(big.id), str(small.id)]
    body = resp.json()
    assert body["total_count"] == 3
    assert body["issued_amount"] == 6000


async def test_since_filters_on_status_change(api_app, session):
    admin, me, other, mechanic, client, vehicle = await _world(session)
    recent = await _visit(session, admin, client, vehicle, me, 1, VisitStatus.ISSUED)
    await _log(session, recent, VisitStatus.ISSUED, NOW - timedelta(days=2))
    old = await _visit(session, admin, client, vehicle, me, 2, VisitStatus.ISSUED)
    await _log(session, old, VisitStatus.ISSUED, NOW - timedelta(days=40))

    since = quote((NOW - timedelta(days=7)).isoformat())
    resp = await _get(api_app, f"/visits?closed=true&since={since}", me)

    assert _ids(resp) == [str(recent.id)]


async def test_offset_pages_and_total_count_ignores_the_limit(api_app, session):
    admin, me, other, mechanic, client, vehicle = await _world(session)
    for hours in range(VISIT_LIST_LIMIT + 3):
        await _visit(session, admin, client, vehicle, me, hours)

    first = (await _get(api_app, "/visits", me)).json()
    second = (await _get(api_app, f"/visits?offset={VISIT_LIST_LIMIT}", me)).json()

    assert len(first["items"]) == VISIT_LIST_LIMIT and first["has_more"] is True
    assert len(second["items"]) == 3 and second["has_more"] is False
    assert first["total_count"] == second["total_count"] == VISIT_LIST_LIMIT + 3
    assert not {i["id"] for i in first["items"]} & {i["id"] for i in second["items"]}


@pytest.mark.parametrize("query", ["sort=bogus", "status=bogus", "offset=-1"])
async def test_bad_params_are_rejected(api_app, session, query):
    admin, me, *_ = await _world(session)
    assert (await _get(api_app, f"/visits?{query}", me)).status_code == 422
