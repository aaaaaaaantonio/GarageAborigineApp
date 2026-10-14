# tests/modules/stats/test_money.py
from datetime import datetime, timezone

from app.core.enums import VisitStatus
from app.modules.stats.service import StatsService
from tests.modules.stats.helpers import NOW, msk, part, visit, work, world

LABELS = ["15.09–16.09", "17.09–23.09", "24.09–30.09", "01.10–07.10", "08.10–14.10"]


def _kpis(out):
    return {k.key: k for k in out.kpis}


async def _money_world(session):
    w = await world(session)
    v1 = await visit(session, w, master=w.master_a, created=msk(10, 8), closed=msk(10, 10), total=10000)
    item = await work(session, v1, name="Замена масла", hours=2, rate=1500, mechanic=w.mech_a)
    await part(session, v1, item, qty=1, price=7000)
    v2 = await visit(session, w, master=w.master_a, created=msk(9, 18), closed=msk(9, 20), total=6000)
    await work(session, v2, name="Ходовая", hours=4, rate=1500)
    await visit(session, w, master=w.master_a, created=msk(8, 30), closed=msk(9, 1), total=8000)  # previous window
    await visit(session, w, master=w.master_a, created=msk(10, 1), status=VisitStatus.CANCELLED, closed=msk(10, 5), total=5000)
    v5 = await visit(session, w, master=w.master_b, created=msk(10, 11), closed=msk(10, 12), total=4000)
    await work(session, v5, name="Диагностика", hours=1, rate=4000)
    return w


async def test_money_kpis_and_series(session):
    w = await _money_world(session)

    out = await StatsService(session, now=NOW).money("month")

    k = _kpis(out)
    assert (k["revenue"].value, k["revenue"].unit, k["revenue"].delta_pct) == (20000, "rub", 150)
    assert (k["avg_check"].value, k["avg_check"].delta_pct) == (6667, -17)
    assert (k["issued"].value, k["issued"].delta_pct) == (3, 200)
    assert (k["work_share"].value, k["work_share"].unit, k["work_share"].compare) == ("65 / 35 %", "text", False)
    revenue, split = out.charts
    assert (revenue.kind, revenue.labels) == ("bars", LABELS)
    assert revenue.series[0].values == [0, 6000, 0, 0, 14000]
    assert split.kind == "stack"
    assert [s.name for s in split.series] == ["Работы", "Запчасти"]
    assert split.series[0].values == [0, 6000, 0, 0, 7000]
    assert split.series[1].values == [0, 0, 0, 0, 7000]


async def test_money_for_one_master(session):
    w = await _money_world(session)

    out = await StatsService(session, now=NOW).money("month", master_id=w.master_b.id)

    assert _kpis(out)["revenue"].value == 4000
    assert _kpis(out)["issued"].value == 1


async def test_money_empty_period(session):
    await world(session)

    out = await StatsService(session, now=NOW).money("week")

    k = _kpis(out)
    assert (k["revenue"].value, k["revenue"].delta_pct) == (0, None)
    assert (k["avg_check"].value, k["work_share"].value) == (0, "—")
    assert out.charts[0].series[0].values == [0] * 7


async def test_issued_without_log_counts_at_creation(session):
    w = await world(session)
    await visit(session, w, master=w.master_a, created=msk(10, 9), total=3000)  # ISSUED, no log entry

    out = await StatsService(session, now=NOW).money("month")

    assert _kpis(out)["revenue"].value == 3000


async def test_deleted_visits_are_ignored(session):
    w = await world(session)
    gone = await visit(session, w, master=w.master_a, created=msk(10, 9), closed=msk(10, 10), total=3000)
    gone.deleted_at = datetime.now(timezone.utc)
    await session.flush()

    out = await StatsService(session, now=NOW).money("month")

    assert _kpis(out)["revenue"].value == 0
