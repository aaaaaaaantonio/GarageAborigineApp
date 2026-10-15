from unittest.mock import AsyncMock

from bot.handlers.stats import bar_lines, format_value, render_stats
from tests.bot.helpers import ADMIN, MECHANIC, buttons

STATS = {
    "section": "money", "period": "month",
    "kpis": [
        {"key": "revenue", "label": "Выручка", "value": 412300, "unit": "rub", "delta_pct": 12, "compare": True},
        {"key": "avg_check", "label": "Средний чек", "value": 15900, "unit": "rub", "delta_pct": -3, "compare": True},
        {"key": "issued", "label": "Выдано заездов", "value": 26, "unit": "count", "delta_pct": None, "compare": True},
        {"key": "work_share", "label": "Работы / запчасти", "value": "57 / 43 %", "unit": "text", "delta_pct": None, "compare": False},
    ],
    "charts": [{"key": "revenue", "kind": "bars", "title": "Выручка", "sub": None, "unit": "rub",
                "labels": ["01.10–07.10", "08.10–14.10"], "series": [{"name": "Выручка", "values": [50000, 100000]}]}],
}


def _api():
    api = AsyncMock()
    api.get_stats.return_value = STATS
    api.get_my_stats.return_value = STATS | {"section": "mine"}
    api.list_masters.return_value = [{"id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "full_name": "Кузнецов"}]
    return api


def test_format_value():
    assert format_value(412300, "rub") == "412 300 ₽"
    assert format_value(0.5, "days") == "0,5 дн."
    assert format_value(7.5, "hours") == "7,5 н/ч"
    assert format_value(50, "pct") == "50%"
    assert format_value("Toyota", "text") == "Toyota"


def test_bar_lines_scale_to_the_largest():
    assert bar_lines(["a", "b"], [50000, 100000], "rub") == ["a  ████  50 000 ₽", "b  ████████  100 000 ₽"]
    assert bar_lines(["a"], [0], "rub") == ["Нет данных за период"]


async def test_admin_summary_and_filters():
    api = _api()

    text, markup = await render_stats(api, ADMIN, {})

    api.get_stats.assert_awaited_once_with("money", "month", master_id=None)
    assert text.splitlines()[:6] == [
        "📊 Статистика · Месяц · Деньги", "",
        "Выручка: 412 300 ₽  ▲ 12%", "Средний чек: 15 900 ₽  ▼ 3%", "Выдано заездов: 26", "Работы / запчасти: 57 / 43 %",
    ]
    assert "08.10–14.10  ████████  100 000 ₽" in text
    assert [b[0] for b in buttons(markup)] == ["Период: Месяц ▾", "Раздел: Деньги ▾", "Мастер: Все мастера ▾"]


async def test_admin_section_and_master_args():
    api = _api()

    await render_stats(api, ADMIN, {"p": "year", "sec": "flow", "m": "qqqqqqqqqqqqqqqqqqqqqq"})

    section, period = api.get_stats.await_args.args
    assert (section, period) == ("flow", "year")
    assert api.get_stats.await_args.kwargs["master_id"] is not None


async def test_mechanic_sees_own_stats_with_period_only():
    api = _api()

    text, markup = await render_stats(api, MECHANIC, {"p": "week"})

    api.get_my_stats.assert_awaited_once_with("week")
    api.get_stats.assert_not_awaited()
    assert text.startswith("📊 Моя статистика · Неделя")
    assert [b[0] for b in buttons(markup)] == ["Период: Неделя ▾"]


async def test_chart_sub_and_rounded_roubles():
    api = _api()
    api.get_stats.return_value = STATS | {"charts": [
        {"key": "s", "kind": "hbars", "title": "Время в статусах", "sub": "от приёма до выдачи 3,5 дн.", "unit": "days",
         "labels": ["Принят"], "series": [{"name": "x", "values": [0.5]}]},
        {"key": "r", "kind": "bars", "title": "Выручка", "sub": None, "unit": "rub",
         "labels": ["a"], "series": [{"name": "x", "values": [412300.5]}]},
    ]}

    text, _ = await render_stats(api, ADMIN, {})

    assert "Время в статусах (от приёма до выдачи 3,5 дн.):" in text
    assert "Выручка:" in text
    assert "a  ████████  412 301 ₽" in text or "a  ████████  412 300 ₽" in text
    assert format_value(412300.5, "rub") in ("412 301 ₽", "412 300 ₽")
