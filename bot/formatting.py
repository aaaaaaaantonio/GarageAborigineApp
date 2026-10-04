"""Date display for staff in Moscow (UTC+3 all year; no DST since 2014).

A fixed offset avoids depending on the tzdata package in the slim image.
"""
from datetime import datetime, timedelta, timezone

MSK = timezone(timedelta(hours=3))


def _msk(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(MSK)


def format_date(value: str) -> str:
    return _msk(value).strftime("%d.%m.%Y")


def format_day(value: str) -> str:
    return _msk(value).strftime("%d.%m")


def format_number(value: float) -> str:
    """Space-grouped thousands; two decimals only when the value is fractional."""
    number = float(value)
    if number.is_integer():
        return f"{int(number):,}".replace(",", " ")
    return f"{number:,.2f}".replace(",", " ")
