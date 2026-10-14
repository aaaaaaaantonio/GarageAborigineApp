# app/modules/stats/service.py
"""Stats sections. Each returns StatsOut: KPI tiles (with change against the previous
window) and charts whose labels are the window's steps or ranked rows."""
import uuid
from collections import defaultdict
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import UserRole, VisitStatus, WorkCategory
from app.modules.stats.periods import Period, Window, buckets, delta_pct, windows
from app.modules.stats.repository import StatsRepository
from app.modules.stats.schemas import Chart, ChartKind, Kpi, Series, StatsOut, Unit

FUNNEL = [
    VisitStatus.RECEIVED, VisitStatus.DIAGNOSTICS, VisitStatus.APPROVAL,
    VisitStatus.IN_PROGRESS, VisitStatus.WAITING_PARTS, VisitStatus.READY,
]
STATUS_LABELS = {
    VisitStatus.RECEIVED: "Принят", VisitStatus.DIAGNOSTICS: "Диагностика", VisitStatus.APPROVAL: "Согласование",
    VisitStatus.IN_PROGRESS: "Ремонт", VisitStatus.WAITING_PARTS: "Ждём запчасти", VisitStatus.READY: "Готов",
}
CATEGORY_LABELS = {
    WorkCategory.DIAGNOSTICS: "Диагностика", WorkCategory.MAINTENANCE: "ТО", WorkCategory.BODY: "Кузовные",
    WorkCategory.ELECTRICAL: "Электрика", WorkCategory.CHASSIS: "Ходовая", WorkCategory.OTHER: "Прочее",
}
DAY_SECONDS = 86400

Steps = list[tuple[str, Window]]


def _bucketed(steps: Steps, points) -> list[float]:
    """Sum (moment, amount) points into the steps they fall in."""
    values = [0.0] * len(steps)
    for moment, amount in points:
        for i, (_, window) in enumerate(steps):
            if moment in window:
                values[i] += float(amount)
                break
    return [round(v, 2) for v in values]


def _kpi(key: str, label: str, value: float | str, unit: Unit, previous: float | None = None, compare: bool = True) -> Kpi:
    delta = delta_pct(value, previous) if compare and previous is not None else None
    return Kpi(key=key, label=label, value=value, unit=unit, delta_pct=delta, compare=compare)


def _chart(key: str, kind: ChartKind, title: str, unit: Unit, labels: list[str], *series: tuple[str, list[float]],
           sub: str | None = None) -> Chart:
    return Chart(key=key, kind=kind, title=title, sub=sub, unit=unit, labels=labels,
                 series=[Series(name=name, values=values) for name, values in series])


def _ranked(totals: dict[str, float]) -> tuple[list[str], list[float]]:
    """Rows sorted by value, largest first; ties by label so the order is stable."""
    rows = sorted(totals.items(), key=lambda item: (-item[1], item[0]))
    return [label for label, _ in rows], [round(value, 2) for _, value in rows]


def _labor(line) -> float:
    return float(line.norm_hours) * float(line.hourly_rate)


class StatsService:
    def __init__(self, session: AsyncSession, now: datetime | None = None):
        self.repo = StatsRepository(session)
        self.now = now

    def _windows(self, period: Period) -> tuple[Window, Window, Steps]:
        current, previous = windows(period, self.now)
        return current, previous, buckets(period, current)

    async def money(self, period: Period, master_id: uuid.UUID | None = None) -> StatsOut:
        current, previous, steps = self._windows(period)
        issued = await self.repo.closed_visits(VisitStatus.ISSUED, current, master_id)
        issued_prev = await self.repo.closed_visits(VisitStatus.ISSUED, previous, master_id)
        revenue = sum(float(v.total_amount) for v in issued)
        revenue_prev = sum(float(v.total_amount) for v in issued_prev)
        average = revenue / len(issued) if issued else 0
        average_prev = revenue_prev / len(issued_prev) if issued_prev else 0

        ids = [v.id for v in issued]
        labor: dict[uuid.UUID, float] = defaultdict(float)
        for line in await self.repo.work_lines(ids):
            labor[line.visit_id] += _labor(line)
        parts = await self.repo.part_sums(ids)
        labor_total, parts_total = sum(labor.values()), sum(parts.values())
        if labor_total + parts_total:
            share = round(labor_total / (labor_total + parts_total) * 100)
            split = f"{share} / {100 - share} %"
        else:
            split = "—"

        labels = [label for label, _ in steps]
        return StatsOut(
            section="money", period=period,
            kpis=[
                _kpi("revenue", "Выручка", round(revenue, 2), "rub", revenue_prev),
                _kpi("avg_check", "Средний чек", round(average), "rub", average_prev),
                _kpi("issued", "Выдано заездов", len(issued), "count", len(issued_prev)),
                _kpi("work_share", "Работы / запчасти", split, "text", compare=False),
            ],
            charts=[
                _chart("revenue", "bars", "Выручка", "rub", labels,
                       ("Выручка", _bucketed(steps, ((v.closed_at, v.total_amount) for v in issued))),
                       sub="по дате выдачи машины"),
                _chart("revenue_split", "stack", "Из чего выручка", "rub", labels,
                       ("Работы", _bucketed(steps, ((v.closed_at, labor[v.id]) for v in issued))),
                       ("Запчасти", _bucketed(steps, ((v.closed_at, parts.get(v.id, 0)) for v in issued))),
                       sub="до скидки"),
            ],
        )
