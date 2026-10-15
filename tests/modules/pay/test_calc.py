from decimal import Decimal

from app.core.enums import PayScheme
from app.modules.pay.calc import line_pay, work_pay


def test_percent_of_the_work_cost():
    assert work_pay(2, 1500, PayScheme.PERCENT, 40) == Decimal("1200.00")


def test_fixed_per_norm_hour_ignores_the_client_rate():
    assert work_pay(1.5, 2000, PayScheme.PER_HOUR, 700) == Decimal("1050.00")


def test_full_cost():
    assert work_pay(1.5, 2000, PayScheme.FULL, None) == Decimal("3000.00")


def test_no_scheme_means_unknown():
    assert work_pay(1, 1000, None, None) is None
    assert work_pay(1, 1000, PayScheme.PERCENT, None) is None


def test_rounds_half_up_to_kopecks():
    assert work_pay(0.01, 1, PayScheme.PERCENT, 50) == Decimal("0.01")


def test_snapshot_wins_over_the_current_scheme():
    assert line_pay(777, 2, 1000, PayScheme.FULL, None) == Decimal("777")
    assert line_pay(None, 2, 1000, PayScheme.FULL, None) == Decimal("2000.00")
