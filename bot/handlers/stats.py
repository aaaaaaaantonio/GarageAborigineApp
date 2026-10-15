"""Statistics as a text summary: KPIs with change against the previous period, then each chart as █ bars."""
from aiogram.types import InlineKeyboardMarkup

from bot import nav
from bot.api_client import ApiClient
from bot.callback_ids import decode_id
from bot.formatting import format_number
from bot.handlers.navigation import master_dropdown

STATS_PERIODS = [("week", "Неделя"), ("month", "Месяц"), ("quarter", "Квартал"), ("year", "Год")]
STATS_SECTIONS = [("money", "Деньги"), ("flow", "Поток"), ("staff", "Сотрудники"), ("works", "Работы и клиенты")]
UNIT_SUFFIX = {"rub": " ₽", "hours": " н/ч", "days": " дн.", "pct": "%", "count": ""}
BAR_WIDTH = 8  # symbols for the largest value


def _number(value: float) -> str:
    return format_number(value) if float(value).is_integer() else f"{value:.1f}".replace(".", ",")


def format_value(value, unit: str) -> str:
    return str(value) if unit == "text" else _number(float(value)) + UNIT_SUFFIX[unit]


def _delta(kpi: dict) -> str:
    pct = kpi["delta_pct"]
    if not kpi["compare"] or pct is None:
        return ""
    return "  = 0%" if pct == 0 else f"  {'▲' if pct > 0 else '▼'} {abs(pct)}%"


def bar_lines(labels: list[str], values: list[float], unit: str) -> list[str]:
    top = max(values, default=0)
    if top <= 0:
        return ["Нет данных за период"]
    return [
        f"{label}  {'█' * max(1, round(v / top * BAR_WIDTH)) if v else '·'}  {format_value(v, unit)}"
        for label, v in zip(labels, values)
    ]


def _chart_values(chart: dict) -> list[float]:
    """A stacked chart reads as its totals in text."""
    return [sum(column) for column in zip(*(s["values"] for s in chart["series"]))]


@nav.screen("stats")
async def render_stats(api: ApiClient, user: dict, args: dict) -> nav.Rendered:
    period, opened = args.get("p", "month"), args.get(nav.OPEN, "-")
    period_label = dict(STATS_PERIODS).get(period, period)
    rows = nav.dropdown("Период", "p", STATS_PERIODS, period, opened)
    if user["role"] == "admin":
        section, master = args.get("sec", "money"), args.get("m", "-")
        data = await api.get_stats(section, period, master_id=None if master == "-" else decode_id(master))
        header = f"📊 Статистика · {period_label} · {dict(STATS_SECTIONS).get(section, section)}"
        rows += nav.dropdown("Раздел", "sec", STATS_SECTIONS, section, opened)
        rows += await master_dropdown(api, master, opened)
    else:
        data = await api.get_my_stats(period)
        header = f"📊 Моя статистика · {period_label}"
    lines = [header, ""]
    lines += [f"{k['label']}: {format_value(k['value'], k['unit'])}{_delta(k)}" for k in data["kpis"]]
    for chart in data["charts"]:
        lines += ["", f"{chart['title']}:", *bar_lines(chart["labels"], _chart_values(chart), chart["unit"])]
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)
