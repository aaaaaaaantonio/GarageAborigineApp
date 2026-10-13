import uuid

import pytest

from app.core.enums import UserRole, VisitStatus, WorkCategory, WorkItemStatus
from app.modules.users.models import User
from app.modules.vehicles.schemas import VehicleCreate
from app.modules.vehicles.service import VehicleService
from app.modules.visits.models import Visit
from app.modules.visits.schemas import VisitCreate
from app.modules.visits.service import VisitService
from app.modules.visits.work_items_schemas import WorkItemCreate
from app.modules.visits.work_items_service import BOARD_LIMIT, WorkItemService
from tests.modules.visits.test_visit_routes import _get, _world, api_app  # noqa: F401


async def _car(session, admin, client, master, plate, vin_char):
    vehicle = await VehicleService(session).create_vehicle(
        VehicleCreate(vin=vin_char * 17, plate_number=plate, make="Kia", model="Rio"), admin
    )
    return await VisitService(session).create_visit(
        VisitCreate(client_id=client.id, vehicle_id=vehicle.id, assigned_master_id=master.id, mileage_at_intake=1),
        admin,
    )


async def _work(session, admin, visit, name, status=WorkItemStatus.NOT_READY, mechanic=None,
                category=WorkCategory.OTHER, approved=True):
    item = await WorkItemService(session).add_item(
        visit.id,
        WorkItemCreate(free_text_name=name, category=category, norm_hours=1, hourly_rate=1000,
                       assigned_mechanic_id=mechanic.id if mechanic else None),
        admin,
    )
    item.status = status
    item.approved_by_client = approved
    await session.flush()
    return item


async def _board_world(session):
    admin, me, other, mechanic, client, vehicle = await _world(session)
    zoe = User(role=UserRole.MECHANIC, full_name="Яковлев", branch_id=uuid.uuid4())
    session.add(zoe)
    await session.flush()
    car_a = await _car(session, admin, client, me, "А111АА77", "B")
    car_b = await _car(session, admin, client, me, "В222ВВ77", "C")
    closed = await _car(session, admin, client, me, "С333СС77", "D")
    w = {
        "a_doing": await _work(session, admin, car_a, "А в работе", WorkItemStatus.IN_PROGRESS, mechanic,
                               WorkCategory.CHASSIS),
        "a_free": await _work(session, admin, car_a, "А без исполнителя", approved=False),
        "b_parts": await _work(session, admin, car_b, "Б ждёт", WorkItemStatus.WAITING_PARTS, zoe,
                               WorkCategory.ELECTRICAL),
        "b_ready": await _work(session, admin, car_b, "Б готово", WorkItemStatus.READY, mechanic),
    }
    await _work(session, admin, closed, "Закрытый заезд", WorkItemStatus.READY, mechanic)
    (await session.get(Visit, closed.id)).status = VisitStatus.ISSUED
    await session.flush()
    return admin, me, mechanic, zoe, w


def _names(resp):
    assert resp.status_code == 200, resp.text
    return [i["name"] for i in resp.json()["items"]]


async def test_board_groups_by_mechanic_unassigned_first(api_app, session):
    admin, me, mechanic, zoe, w = await _board_world(session)

    resp = await _get(api_app, "/work-items/board", me)

    assert _names(resp) == ["А без исполнителя", "А в работе", "Б готово", "Б ждёт"]
    item = resp.json()["items"][1]
    assert item["assigned_mechanic_name"] == "Механик"
    assert item["plate_number"] == "А111АА77" and item["make_model"] == "Kia Rio"
    assert item["category"] == "chassis" and item["visit_status"] == "received"
    assert item["norm_hours"] == 1.0 and item["approved_by_client"] is True
    assert resp.json()["has_more"] is False


async def test_board_group_by_status_and_by_car(api_app, session):
    admin, me, mechanic, zoe, w = await _board_world(session)

    by_status = await _get(api_app, "/work-items/board?group=status", me)
    by_car = await _get(api_app, "/work-items/board?group=car", me)

    assert _names(by_status) == ["А в работе", "А без исполнителя", "Б ждёт", "Б готово"]
    assert _names(by_car) == ["А в работе", "А без исполнителя", "Б ждёт", "Б готово"]


async def test_board_filters(api_app, session):
    admin, me, mechanic, zoe, w = await _board_world(session)

    assert _names(await _get(api_app, f"/work-items/board?mechanic_id={zoe.id}", me)) == ["Б ждёт"]
    assert _names(await _get(api_app, "/work-items/board?unassigned=true", me)) == ["А без исполнителя"]
    assert _names(await _get(api_app, "/work-items/board?status=ready&status=waiting_parts&group=status", me)) == [
        "Б ждёт", "Б готово"]
    assert _names(await _get(api_app, "/work-items/board?category=electrical", admin)) == ["Б ждёт"]
    assert _names(await _get(api_app, "/work-items/board?unapproved=true", me)) == ["А без исполнителя"]


async def test_board_is_staff_only_and_validates(api_app, session):
    admin, me, mechanic, zoe, w = await _board_world(session)

    assert (await _get(api_app, "/work-items/board", mechanic)).status_code == 403
    assert (await _get(api_app, "/work-items/board?group=bogus", me)).status_code == 422


async def test_board_reports_has_more(api_app, session, monkeypatch):
    monkeypatch.setattr("app.modules.visits.work_items_service.BOARD_LIMIT", 2)
    admin, me, mechanic, zoe, w = await _board_world(session)

    resp = await _get(api_app, "/work-items/board", me)

    assert len(resp.json()["items"]) == 2 and resp.json()["has_more"] is True
    assert BOARD_LIMIT == 200
