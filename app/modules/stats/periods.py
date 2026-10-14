"""Rolling stats windows in Moscow time, their chart steps, and period-over-period change."""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

MSK = ZoneInfo("Europe/Moscow")
Period = Literal["week", "month", "quarter", "year"]
PERIOD_DAYS: dict[str, int] = {"week": 7, "month": 30, "quarter": 90, "year": 365}
MONTHS = ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]


@dataclass(frozen=True)
class Window:
    start: datetime  # inclusive
    end: datetime  # exclusive

    def __contains__(self, moment: datetime) -> bool:
        return self.start <= moment < self.end


def _midnight(day: date) -> datetime:
    return datetime.combine(day, time(), tzinfo=MSK)


def windows(period: Period, now: datetime | None = None) -> tuple[Window, Window]:
    """The window ending with today (Moscow) and the same-length window right before it."""
    today = (now or datetime.now(MSK)).astimezone(MSK).date()
    end = _midnight(today + timedelta(days=1))
    length = timedelta(days=PERIOD_DAYS[period])
    current = Window(end - length, end)
    return current, Window(current.start - length, current.start)


def buckets(period: Period, window: Window) -> list[tuple[str, Window]]:
    """Chart steps covering `window`: days (week), calendar months (year), else 7-day steps ending today."""
    steps: list[tuple[str, Window]] = []
    if period == "week":
        start = window.start
        while start < window.end:
            end = start + timedelta(days=1)
            steps.append((f"{start:%d.%m}", Window(start, end)))
            start = end
        return steps
    if period == "year":
        start = window.start
        while start < window.end:
            following = _midnight(date(start.year + start.month // 12, start.month % 12 + 1, 1))
            end = min(following, window.end)
            steps.append((f"{MONTHS[start.month - 1]} {start:%y}", Window(start, end)))
            start = end
        return steps
    end = window.end
    while end > window.start:
        start = max(end - timedelta(days=7), window.start)
        steps.append((f"{start:%d.%m}–{end - timedelta(days=1):%d.%m}", Window(start, end)))
        end = start
    return steps[::-1]


def delta_pct(current: float, previous: float) -> int | None:
    if not previous:
        return None
    return round((current - previous) / previous * 100)
