from app.modules.stats.service import StatsService
from tests.modules.stats.helpers import NOW, msk, visit, work, world


async def test_staff_hours_and_master_revenue(session):
    w = await world(session)
    v1 = await visit(session, w, master=w.master_a, created=msk(10, 9), closed=msk(10, 10), total=10000)
    await work(session, v1, name="A", hours=2, rate=1000, mechanic=w.mech_a)
    await work(session, v1, name="B", hours=3, rate=1000, mechanic=w.mech_b)
    await work(session, v1, name="C", hours=1, rate=1000, mechanic=w.admin)
    await work(session, v1, name="D", hours=0.5, rate=1000)
    v2 = await visit(session, w, master=w.master_b, created=msk(10, 10), closed=msk(10, 11), total=4000)
    await work(session, v2, name="E", hours=4, rate=1000, mechanic=w.mech_a)
    v3 = await visit(session, w, master=w.master_a, created=msk(8, 31), closed=msk(9, 1), total=1000)
    await work(session, v3, name="F", hours=1, rate=1000, mechanic=w.mech_a)

    out = await StatsService(session, now=NOW).staff("month")

    k = {x.key: x for x in out.kpis}
    assert (k["hours"].value, k["hours"].unit, k["hours"].delta_pct) == (10.5, "hours", 950)
    assert (k["works"].value, k["works"].delta_pct) == (5, 400)
    hours, revenue = out.charts
    assert hours.labels == ["Морозов", "Соколов", "Иванов (админ)", "Без исполнителя"]
    assert hours.series[0].values == [6, 3, 1, 0.5]
    assert (revenue.labels, revenue.series[0].values, revenue.unit) == (["Кузнецов", "Белова"], [10000, 4000], "rub")
