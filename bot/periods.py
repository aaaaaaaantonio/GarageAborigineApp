"""List periods shared by the archive and the mechanic's done works."""
from datetime import datetime, timedelta, timezone

PERIOD_DAYS = {"week": 7, "month": 30, "quarter": 90}
PERIOD_LABELS = {"week": "Неделя", "month": "Месяц", "quarter": "Квартал", "all": "Всё"}


def since_for(period: str) -> str | None:
    """ISO start of the period; `all` (or anything unknown) has no start."""
    days = PERIOD_DAYS.get(period)
    return None if days is None else (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def days_since(iso: str | None) -> int:
    if not iso:
        return 0
    return max(0, (datetime.now(timezone.utc) - datetime.fromisoformat(iso)).days)
