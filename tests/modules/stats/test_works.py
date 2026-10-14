from app.core.enums import WorkCategory as C
from app.modules.stats.service import StatsService
from tests.modules.stats.helpers import NOW, msk, visit, work, world


async def test_works_and_clients(session):
    w = await world(session)
    await visit(session, w, master=w.master_a, created=msk(8, 20), closed=msk(8, 21))  # w.client's earlier visit
    v1 = await visit(session, w, master=w.master_a, created=msk(10, 2), closed=msk(10, 5))
    await work(session, v1, name="Замена масла", hours=1, rate=2000)
    await work(session, v1, name="Диагностика", hours=1, rate=1000, category=C.DIAGNOSTICS)
    await work(session, v1, name="Замена колодок", hours=2, rate=1500, category=C.CHASSIS, extra=True, approved=True)
    v2 = await visit(session, w, master=w.master_a, created=msk(10, 6), closed=msk(10, 8), client=w.client2)
    await work(session, v2, name="Замена масла", hours=1, rate=2000)
    await work(session, v2, name="Развал", hours=1, rate=1000, category=C.CHASSIS, extra=True, approved=False)

    out = await StatsService(session, now=NOW).works("month")

    k = {x.key: x for x in out.kpis}
    assert (k["new_clients"].value, k["new_clients"].delta_pct) == (1, 0)
    assert (k["repeat_clients"].value, k["repeat_clients"].delta_pct) == (1, None)
    assert (k["extra_approved"].value, k["extra_approved"].unit, k["extra_approved"].delta_pct) == (50, "pct", None)
    assert (k["top_make"].value, k["top_make"].compare) == ("Toyota", False)
    top, clients, categories = out.charts
    assert top.labels == ["Замена масла", "Диагностика", "Замена колодок", "Развал"]
    assert top.series[0].values == [2, 1, 1, 1]
    assert (clients.kind, clients.labels, clients.series[0].values) == ("share", ["Новые", "Повторные"], [1, 1])
    assert categories.labels == ["ТО", "Ходовая", "Диагностика"]
    assert categories.series[0].values == [4000, 4000, 1000]


async def test_works_empty(session):
    await world(session)

    out = await StatsService(session, now=NOW).works("month")

    k = {x.key: x for x in out.kpis}
    assert (k["extra_approved"].value, k["top_make"].value) == (0, "—")
