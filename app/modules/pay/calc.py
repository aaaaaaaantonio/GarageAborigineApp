"""A mechanic's pay for one work. Pure functions: the snapshot at issue, the stats and the
mechanic's visit card all use them, so the numbers always agree."""
from decimal import ROUND_HALF_UP, Decimal

from app.core.enums import PayScheme

CENT = Decimal("0.01")


def _d(value) -> Decimal:
    return Decimal(str(value))


def work_pay(norm_hours, hourly_rate, scheme: PayScheme | None, value) -> Decimal | None:
    """Pay for a work of `norm_hours` at the client's `hourly_rate`; None when the scheme is unknown."""
    if scheme is None or (scheme != PayScheme.FULL and value is None):
        return None
    hours = _d(norm_hours)
    if scheme == PayScheme.PERCENT:
        pay = hours * _d(hourly_rate) * _d(value) / 100
    elif scheme == PayScheme.PER_HOUR:
        pay = hours * _d(value)
    else:
        pay = hours * _d(hourly_rate)
    return pay.quantize(CENT, rounding=ROUND_HALF_UP)


def line_pay(snapshot, norm_hours, hourly_rate, scheme: PayScheme | None, value) -> Decimal | None:
    """The snapshot taken at issue if there is one, else the pay by the current scheme."""
    if snapshot is not None:
        return _d(snapshot)
    return work_pay(norm_hours, hourly_rate, scheme, value)
