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


def _ranked_by(totals: dict, labels: dict) -> tuple[list[str], list[float]]:
    """Rows keyed by identity (id), shown under `labels[key]`; sorted like `_ranked` by value, then label."""
    rows = sorted(totals.items(), key=lambda item: (-item[1], labels[item[0]]))
    return [labels[key] for key, _ in rows], [round(value, 2) for _, value in rows]


def _split(totals: dict[str, float], name: str) -> tuple[list[str], tuple[str, list[float]]]:
    """`_ranked` shaped as `_chart(..., labels, (name, values))` arguments."""
    labels, values = _ranked(totals)
    return labels, (name, values)


def _split_by(totals: dict, labels: dict, name: str) -> tuple[list[str], tuple[str, list[float]]]:
    labels_, values = _ranked_by(totals, labels)
    return labels_, (name, values)


def _assignee(line) -> str:
    if line.mechanic_id is None:
        return "Без исполнителя"
    return f"{line.mechanic_name} (админ)" if line.mechanic_role == UserRole.ADMIN else line.mechanic_name


def _labor(line) -> float:
    return float(line.norm_hours) * float(line.hourly_rate)


def _days(seconds: float) -> float:
    return round(seconds / DAY_SECONDS, 1)


def _time_in_statuses(visits, logs) -> tuple[list[float], float]:
    """Average days a closed visit spent in each funnel status, and from intake to close."""
    if not visits:
        return [0.0] * len(FUNNEL), 0.0
    history = defaultdict(list)
    for row in logs:
        history[row.visit_id].append((row.to_status, row.changed_at))
    spent: dict[VisitStatus, float] = defaultdict(float)
    through = 0.0
    for v in visits:
        steps = [(VisitStatus.RECEIVED, v.created_at), *sorted(history[v.id], key=lambda step: step[1])]
        for (status, start), (_, end) in zip(steps, steps[1:]):
            if status in STATUS_LABELS:
                spent[status] += (end - start).total_seconds()
        through += (v.closed_at - v.created_at).total_seconds()
    return [_days(spent[s] / len(visits)) for s in FUNNEL], _days(through / len(visits))


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

    async def flow(self, period: Period, master_id: uuid.UUID | None = None) -> StatsOut:
        current, previous, steps = self._windows(period)
        created = await self.repo.created_visits(current, master_id)
        created_prev = await self.repo.created_visits(previous, master_id)
        issued = await self.repo.closed_visits(VisitStatus.ISSUED, current, master_id)
        issued_prev = await self.repo.closed_visits(VisitStatus.ISSUED, previous, master_id)
        cancelled = await self.repo.closed_visits(VisitStatus.CANCELLED, current, master_id)
        cancelled_prev = await self.repo.closed_visits(VisitStatus.CANCELLED, previous, master_id)
        per_status, through = _time_in_statuses(issued, await self.repo.status_logs([v.id for v in issued]))
        sub = "в среднем, дней"
        if issued:
            sub += f" · от приёма до выдачи {str(through).replace('.', ',')} дн."
        return StatsOut(
            section="flow", period=period,
            kpis=[
                _kpi("accepted", "Принято", len(created), "count", len(created_prev)),
                _kpi("issued", "Выдано", len(issued), "count", len(issued_prev)),
                _kpi("open_now", "Сейчас в работе", await self.repo.open_count(master_id), "count", compare=False),
                _kpi("cancelled", "Отменено", len(cancelled), "count", len(cancelled_prev)),
            ],
            charts=[
                _chart("accepted", "bars", "Принято машин", "count", [label for label, _ in steps],
                       ("Принято", _bucketed(steps, ((v.created_at, 1) for v in created)))),
                _chart("time_in_status", "hbars", "Сколько стоят в каждом статусе", "days",
                       [STATUS_LABELS[s] for s in FUNNEL], ("Дней", per_status), sub=sub),
            ],
        )

    async def staff(self, period: Period, master_id: uuid.UUID | None = None) -> StatsOut:
        current, previous, _ = self._windows(period)
        issued = await self.repo.closed_visits(VisitStatus.ISSUED, current, master_id)
        issued_prev = await self.repo.closed_visits(VisitStatus.ISSUED, previous, master_id)
        lines = await self.repo.work_lines([v.id for v in issued])
        lines_prev = await self.repo.work_lines([v.id for v in issued_prev])
        hours: dict[uuid.UUID | None, float] = defaultdict(float)
        names: dict[uuid.UUID | None, str] = {}
        for line in lines:
            hours[line.mechanic_id] += float(line.norm_hours)
            names[line.mechanic_id] = _assignee(line)
        revenue: dict[uuid.UUID, float] = defaultdict(float)
        master_names: dict[uuid.UUID, str] = {}
        for v in issued:
            revenue[v.master_id] += float(v.total_amount)
            master_names[v.master_id] = v.master_name
        total = sum(hours.values())
        total_prev = sum(float(line.norm_hours) for line in lines_prev)
        return StatsOut(
            section="staff", period=period,
            kpis=[
                _kpi("hours", "Нормо-часов закрыто", round(total, 2), "hours", total_prev),
                _kpi("works", "Работ выполнено", len(lines), "count", len(lines_prev)),
            ],
            charts=[
                _chart("hours_by_assignee", "hbars", "Нормо-часы по исполнителям", "hours",
                       *_split_by(hours, names, "Нормо-часы"), sub="работы выданных машин"),
                _chart("revenue_by_master", "hbars", "Выручка по мастерам", "rub",
                       *_split_by(revenue, master_names, "Выручка")),
            ],
        )

    async def works(self, period: Period, master_id: uuid.UUID | None = None) -> StatsOut:
        current, previous, _ = self._windows(period)
        issued = await self.repo.closed_visits(VisitStatus.ISSUED, current, master_id)
        lines = await self.repo.work_lines([v.id for v in issued])
        created = await self.repo.created_visits(current, master_id)
        created_prev = await self.repo.created_visits(previous, master_id)
        new, repeat = await self._clients(created, current)
        new_prev, repeat_prev = await self._clients(created_prev, previous)
        approved = await self._extra_approved(created)
        approved_prev = await self._extra_approved(created_prev)

        counts: dict[str, float] = defaultdict(float)
        by_category: dict[str, float] = defaultdict(float)
        for line in lines:
            counts[line.name] += 1
            by_category[CATEGORY_LABELS[line.category]] += _labor(line)
        top_labels, top_values = _ranked(counts)
        makes: dict[str, float] = defaultdict(float)
        for v in created:
            makes[v.make] += 1
        top_make = _ranked(makes)[0][0] if makes else "—"
        return StatsOut(
            section="works", period=period,
            kpis=[
                _kpi("new_clients", "Новые клиенты", new, "count", new_prev),
                _kpi("repeat_clients", "Повторные клиенты", repeat, "count", repeat_prev),
                _kpi("extra_approved", "Доп. работ согласовано", approved if approved is not None else 0, "pct",
                     approved_prev),
                _kpi("top_make", "Популярная марка", top_make, "text", compare=False),
            ],
            charts=[
                _chart("top_works", "hbars", "Топ работ", "count", top_labels[:5], ("Раз", top_values[:5]),
                       sub="сколько раз делали"),
                _chart("clients", "share", "Клиенты за период", "count", ["Новые", "Повторные"],
                       ("Клиенты", [new, repeat])),
                _chart("revenue_by_category", "hbars", "Выручка по категориям работ", "rub",
                       *_split(by_category, "Выручка")),
            ],
        )

    async def _clients(self, created, window: Window) -> tuple[int, int]:
        """Distinct clients with a visit created in `window`: new (first visit ever is in it) and repeat."""
        clients = {v.client_id for v in created}
        first = await self.repo.first_visit_at(list(clients))
        new = sum(1 for c in clients if first[c] in window)
        return new, len(clients) - new

    async def _extra_approved(self, created) -> int | None:
        """Share (%) of extra works the client approved, among visits created in the window; None if none."""
        extra = [line for line in await self.repo.work_lines([v.id for v in created]) if line.is_extra_work]
        return round(sum(1 for line in extra if line.approved_by_client) / len(extra) * 100) if extra else None
