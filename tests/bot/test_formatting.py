from bot.formatting import format_date, format_day
from bot.visit_status import visit_status_label
from bot.work_item_status import work_item_status_label


def test_dates_are_shown_in_moscow_time():
    # 22:30 UTC on Oct 1 is 01:30 MSK on Oct 2
    assert format_date("2026-10-01T22:30:00+00:00") == "02.10.2026"
    assert format_day("2026-10-01T22:30:00+00:00") == "02.10"


def test_status_labels_are_russian_and_fall_back_to_code():
    assert visit_status_label("in_progress") == "Ремонт"
    assert visit_status_label("waiting_parts") == "Ждём запчасти"
    assert visit_status_label("unknown") == "unknown"
    assert work_item_status_label("ready") == "Готово"
    assert work_item_status_label("not_ready") == "Не начата"
