# app/modules/stats/schemas.py
"""One shape for every stats section: KPI tiles plus charts. Labels are Russian so web and bot read the same."""
from typing import Literal

from pydantic import BaseModel

from app.modules.stats.periods import Period

Unit = Literal["rub", "count", "hours", "days", "pct", "text"]
ChartKind = Literal["bars", "stack", "hbars", "share"]


class Kpi(BaseModel):
    key: str
    label: str
    value: float | str
    unit: Unit
    delta_pct: int | None = None
    higher_is_better: bool = True  # False: a rise is bad news (cancelled), the web inverts the delta colour
    compare: bool = True  # False: a current-state figure with no previous period to compare to


class Series(BaseModel):
    name: str
    values: list[float]


class Chart(BaseModel):
    key: str
    kind: ChartKind
    title: str
    sub: str | None = None
    unit: Unit
    labels: list[str]
    series: list[Series]


class StatsOut(BaseModel):
    section: str
    period: Period
    kpis: list[Kpi]
    charts: list[Chart]
