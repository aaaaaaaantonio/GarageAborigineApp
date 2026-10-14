from app.core.enums import VisitStatus, WorkCategory as C, WorkItemStatus
from app.modules.stats.service import StatsService
from tests.modules.stats.helpers import NOW, msk, visit, work, world
from tests.modules.visits.test_visit_routes import _get, api_app  # noqa: F401


async def _mine_world(session):
    w = await world(session)
    v1 = await visit(session, w, master=w.master_a, created=msk(10, 9), closed=msk(10, 10), total=10000)
    await work(session, v1, name="Масло", hours=2, rate=1000, mechanic=w.mech_a)
    await work(session, v1, name="Рычаг", hours=1.5, rate=1000, mechanic=w.mech_a, category=C.CHASSIS)
    v2 = await visit(session, w, master=w.master_b, created=msk(10, 10), closed=msk(10, 11), total=4000)
    await work(session, v2, name="Стойки", hours=4, rate=1000, mechanic=w.mech_a, category=C.CHASSIS)
    await work(session, v2, name="Чужая", hours=9, rate=1000, mechanic=w.mech_b)
    open_visit = await visit(session, w, master=w.master_a, created=msk(10, 13), status=VisitStatus.IN_PROGRESS)
    await work(session, open_visit, name="В работе", hours=1, rate=1000, mechanic=w.mech_a, status=WorkItemStatus.IN_PROGRESS)
    await work(session, open_visit, name="Готово", hours=1, rate=1000, mechanic=w.mech_a)
    return w


async def test_master_sees_only_own_visits(session):
    w = await _mine_world(session)

    out = await StatsService(session, now=NOW).mine(w.master_a, "month")

    k = {x.key: x for x in out.kpis}
    assert out.section == "mine"
    assert (k["revenue"].value, k["avg_check"].value, k["issued"].value, k["open_now"].value) == (10000, 10000, 1, 1)
    assert [c.key for c in out.charts] == ["revenue", "time_in_status"]


async def test_mechanic_sees_own_hours_and_no_money(session):
    w = await _mine_world(session)

    out = await StatsService(session, now=NOW).mine(w.mech_a, "month")

    k = {x.key: x for x in out.kpis}
    assert (k["hours"].value, k["works"].value, k["in_progress"].value, k["avg_hours"].value) == (7.5, 3, 1, 2.5)
    hours, categories = out.charts
    assert hours.series[0].values == [0, 0, 0, 0, 7.5]
    assert (categories.labels, categories.series[0].values) == (["Ходовая", "ТО"], [5.5, 2])
    assert all(x.unit != "rub" for x in out.kpis) and all(c.unit != "rub" for c in out.charts)


async def test_mine_route_access(api_app, session):
    w = await world(session)

    assert (await _get(api_app, "/stats/mine", w.master_a)).status_code == 200
    assert (await _get(api_app, "/stats/mine", w.mech_a)).status_code == 200
    assert (await _get(api_app, "/stats/mine", w.admin)).status_code == 403
