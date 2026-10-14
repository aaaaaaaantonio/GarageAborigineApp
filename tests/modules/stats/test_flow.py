from app.core.enums import VisitStatus as S
from app.modules.stats.service import StatsService
from tests.modules.stats.helpers import NOW, msk, visit, world


async def _flow_world(session):
    w = await world(session)
    # a: принят 12 ч, диагностика 24 ч, согласование 48 ч, ремонт 24 ч, готов 12 ч → 5 дн.
    await visit(session, w, master=w.master_a, created=msk(10, 1, 10), closed=msk(10, 6, 10), history=[
        (S.DIAGNOSTICS, msk(10, 1, 22)), (S.APPROVAL, msk(10, 2, 22)), (S.IN_PROGRESS, msk(10, 4, 22)), (S.READY, msk(10, 5, 22)),
    ])
    # b: принят 12 ч, готов 36 ч → 2 дн.
    await visit(session, w, master=w.master_a, created=msk(10, 6, 10), closed=msk(10, 8, 10), history=[(S.READY, msk(10, 6, 22))])
    await visit(session, w, master=w.master_a, created=msk(10, 10), status=S.IN_PROGRESS)
    await visit(session, w, master=w.master_b, created=msk(10, 12), status=S.CANCELLED, closed=msk(10, 13))
    await visit(session, w, master=w.master_a, created=msk(9, 1), closed=msk(9, 3))  # previous window
    return w


async def test_flow_kpis_and_charts(session):
    await _flow_world(session)

    out = await StatsService(session, now=NOW).flow("month")

    k = {x.key: x for x in out.kpis}
    assert (k["accepted"].value, k["accepted"].delta_pct) == (4, 300)
    assert (k["issued"].value, k["issued"].delta_pct) == (2, 100)
    assert (k["open_now"].value, k["open_now"].compare) == (1, False)
    assert (k["cancelled"].value, k["cancelled"].delta_pct) == (1, None)
    accepted, statuses = out.charts
    assert accepted.series[0].values == [0, 0, 0, 2, 2]
    assert statuses.kind == "hbars" and statuses.unit == "days"
    assert statuses.labels == ["Принят", "Диагностика", "Согласование", "Ремонт", "Ждём запчасти", "Готов"]
    assert statuses.series[0].values == [0.5, 0.5, 1.0, 0.5, 0.0, 1.0]
    assert statuses.sub == "в среднем, дней · от приёма до выдачи 3,5 дн."


async def test_flow_empty(session):
    await world(session)

    out = await StatsService(session, now=NOW).flow("month")

    assert out.charts[1].series[0].values == [0.0] * 6
    assert out.charts[1].sub == "в среднем, дней"
