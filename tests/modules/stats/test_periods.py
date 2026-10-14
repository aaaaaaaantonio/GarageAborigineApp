from datetime import datetime, timezone

from app.modules.stats.periods import MSK, buckets, delta_pct, windows

NOW = datetime(2026, 10, 14, 9, 0, tzinfo=timezone.utc)  # 12:00 МСК


def test_month_window_and_previous():
    cur, prev = windows("month", NOW)
    assert cur.start == datetime(2026, 9, 15, tzinfo=MSK)
    assert cur.end == datetime(2026, 10, 15, tzinfo=MSK)
    assert prev.start == datetime(2026, 8, 16, tzinfo=MSK)
    assert prev.end == cur.start


def test_window_edges_are_moscow_midnights():
    cur, prev = windows("week", NOW)
    assert datetime(2026, 10, 14, 23, 30, tzinfo=MSK) in cur
    assert datetime(2026, 10, 15, 0, 0, tzinfo=MSK) not in cur
    assert datetime(2026, 10, 8, 0, 10, tzinfo=MSK) in cur
    assert datetime(2026, 10, 7, 23, 50, tzinfo=MSK) in prev


def test_week_steps_are_days():
    cur, _ = windows("week", NOW)
    steps = buckets("week", cur)
    assert [label for label, _ in steps] == ["08.10", "09.10", "10.10", "11.10", "12.10", "13.10", "14.10"]


def test_month_steps_are_weeks_ending_today_oldest_shorter():
    cur, _ = windows("month", NOW)
    steps = buckets("month", cur)
    assert [label for label, _ in steps] == ["15.09–16.09", "17.09–23.09", "24.09–30.09", "01.10–07.10", "08.10–14.10"]
    assert steps[0][1].start == cur.start and steps[-1][1].end == cur.end


def test_quarter_has_thirteen_steps():
    cur, _ = windows("quarter", NOW)
    assert len(buckets("quarter", cur)) == 13


def test_year_steps_are_calendar_months():
    cur, _ = windows("year", NOW)
    labels = [label for label, _ in buckets("year", cur)]
    assert labels[0] == "окт 25" and labels[1] == "ноя 25" and labels[-1] == "окт 26"
    assert len(labels) == 13


def test_delta_pct():
    assert delta_pct(20000, 8000) == 150
    assert delta_pct(6666.67, 8000) == -17
    assert delta_pct(5, 0) is None
    assert delta_pct(0, 0) is None
