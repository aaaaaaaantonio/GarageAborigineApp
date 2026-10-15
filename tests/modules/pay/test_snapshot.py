from decimal import Decimal

from app.core.enums import PayScheme, VisitStatus
from app.modules.visits.service import VisitService
from app.modules.visits.work_items_service import WorkItemService
from tests.modules.stats.helpers import msk, visit, work, world


async def _issue(session, w, v):
    await VisitService(session).change_status(v.id, VisitStatus.ISSUED, w.admin)
    await session.flush()


async def test_issue_fixes_pay_for_mechanics_with_a_scheme(session):
    w = await world(session)
    w.mech_a.pay_scheme, w.mech_a.pay_value = PayScheme.PERCENT, 50
    v = await visit(session, w, master=w.master_a, created=msk(10, 9), status=VisitStatus.READY)
    own = await work(session, v, name="Масло", hours=2, rate=1000, mechanic=w.mech_a)
    by_admin = await work(session, v, name="Сам", hours=1, rate=1000, mechanic=w.admin)
    no_scheme = await work(session, v, name="Чужая", hours=1, rate=1000, mechanic=w.mech_b)
    nobody = await work(session, v, name="Ничья", hours=1, rate=1000)

    await _issue(session, w, v)

    assert own.mechanic_pay == Decimal("1000.00")
    assert (by_admin.mechanic_pay, no_scheme.mechanic_pay, nobody.mechanic_pay) == (None, None, None)


async def test_changing_the_scheme_later_keeps_the_snapshot(session):
    w = await world(session)
    w.mech_a.pay_scheme, w.mech_a.pay_value = PayScheme.PERCENT, 50
    v = await visit(session, w, master=w.master_a, created=msk(10, 9), status=VisitStatus.READY)
    own = await work(session, v, name="Масло", hours=2, rate=1000, mechanic=w.mech_a)
    await _issue(session, w, v)

    w.mech_a.pay_value = 10
    await session.flush()
    await session.refresh(own)

    assert own.mechanic_pay == Decimal("1000.00")


async def test_reassigning_an_issued_work_recomputes_it_for_the_new_mechanic(session):
    w = await world(session)
    w.mech_a.pay_scheme, w.mech_a.pay_value = PayScheme.PERCENT, 50
    w.mech_b.pay_scheme, w.mech_b.pay_value = PayScheme.FULL, None
    v = await visit(session, w, master=w.master_a, created=msk(10, 9), status=VisitStatus.READY)
    item = await work(session, v, name="Масло", hours=2, rate=1000, mechanic=w.mech_a)
    await _issue(session, w, v)

    await WorkItemService(session).assign_mechanic(v.id, item.id, w.mech_b.id, w.admin)

    assert item.mechanic_pay == Decimal("2000.00")


async def test_reassigning_an_open_work_does_not_snapshot(session):
    w = await world(session)
    w.mech_a.pay_scheme, w.mech_a.pay_value = PayScheme.FULL, None
    v = await visit(session, w, master=w.master_a, created=msk(10, 9), status=VisitStatus.IN_PROGRESS)
    item = await work(session, v, name="Масло", hours=2, rate=1000, mechanic=w.mech_b)

    await WorkItemService(session).assign_mechanic(v.id, item.id, w.mech_a.id, w.admin)

    assert item.mechanic_pay is None


async def test_work_added_to_an_issued_visit_gets_a_snapshot(session):
    from app.core.enums import WorkCategory
    from app.modules.visits.work_items_schemas import WorkItemCreate

    w = await world(session)
    w.mech_a.pay_scheme, w.mech_a.pay_value = PayScheme.PERCENT, 50
    v = await visit(session, w, master=w.master_a, created=msk(10, 9), status=VisitStatus.READY)
    await work(session, v, name="Масло", hours=1, rate=1000, mechanic=w.mech_a)
    await _issue(session, w, v)

    item = await WorkItemService(session).add_item(
        v.id,
        WorkItemCreate(free_text_name="Доп", category=WorkCategory.MAINTENANCE, norm_hours=2, hourly_rate=1000,
                       assigned_mechanic_id=w.mech_a.id),
        w.admin,
    )
    assert item.mechanic_pay == Decimal("1000.00")

    w.mech_a.pay_value = 10
    await session.flush()
    await session.refresh(item)
    assert item.mechanic_pay == Decimal("1000.00")


async def test_reassigning_an_issued_work_to_admin_or_schemeless_clears_pay(session):
    w = await world(session)
    w.mech_a.pay_scheme, w.mech_a.pay_value = PayScheme.FULL, None
    v = await visit(session, w, master=w.master_a, created=msk(10, 9), status=VisitStatus.READY)
    item = await work(session, v, name="Масло", hours=2, rate=1000, mechanic=w.mech_a)
    await _issue(session, w, v)
    assert item.mechanic_pay == Decimal("2000.00")

    await WorkItemService(session).assign_mechanic(v.id, item.id, w.admin.id, w.admin)
    assert item.mechanic_pay is None

    await WorkItemService(session).assign_mechanic(v.id, item.id, w.mech_a.id, w.admin)
    assert item.mechanic_pay == Decimal("2000.00")
    await WorkItemService(session).assign_mechanic(v.id, item.id, w.mech_b.id, w.admin)
    assert item.mechanic_pay is None
