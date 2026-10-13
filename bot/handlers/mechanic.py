from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot import nav
from bot.api_client import ApiClient
from bot.formatting import format_date, format_hours
from bot.handlers.navigation import option_rows
from bot.periods import PERIOD_LABELS, since_for
from bot.work_item_status import work_item_icon

MY_WORKS_LIMIT = 30
# Read-only text list; 30 entries stay well under Telegram's 4096-char message limit.
DONE_WORKS_LIMIT = 30

MY_STATUSES = [("all", "Все"), ("in_progress", "В работе"), ("not_ready", "Не начаты"),
               ("waiting_parts", "Запчасти"), ("ready", "Готовы")]
MY_SORTS = [("urgency", "По срочности"), ("car", "По машинам")]
DONE_PERIODS = [(p, PERIOD_LABELS[p]) for p in ("week", "month", "all")]
DONE_OUTCOMES = [("all", "Все"), ("issued", "Выданы"), ("cancelled", "Отменены")]


@nav.screen("my_works")
async def render_my_works(api: ApiClient, user: dict, args: dict) -> nav.Rendered:
    status, sort = args.get("st", "all"), args.get("s", "urgency")
    items = await api.list_my_work_items(status=None if status == "all" else [status], sort=sort)
    rows = option_rows("st", MY_STATUSES, status) + [[nav.cycle_button("↕", "s", MY_SORTS, sort)]]
    if not items:
        empty = "У вас нет назначенных работ." if status == "all" else "Нет работ с этим фильтром."
        return empty, InlineKeyboardMarkup(inline_keyboard=rows)
    for item in items[:MY_WORKS_LIMIT]:
        work = f"{work_item_icon(item['status'])} {item['name']}"
        plate = item.get("plate_number")
        # By car the plate leads, so a car's works read as one block.
        label = (f"{plate} · {work}" if sort == "car" else f"{work} · {plate}") if plate else work
        rows.append([InlineKeyboardButton(text=label, callback_data=nav.go_data("work", item["visit_id"], item["id"]))])
    text = f"Мои работы ({len(items)})"
    if len(items) > MY_WORKS_LIMIT:
        text += f"\nПоказаны первые {MY_WORKS_LIMIT}."
    return text, InlineKeyboardMarkup(inline_keyboard=rows)


@nav.screen("done_works")
async def render_done_works(api: ApiClient, user: dict, args: dict) -> nav.Rendered:
    """Finished work in closed visits, newest first. Text only: closed work can't change."""
    period, outcome = args.get("p", "month"), args.get("o", "all")
    result = await api.list_my_done_work_items(since=since_for(period), outcome=None if outcome == "all" else outcome)
    markup = InlineKeyboardMarkup(inline_keyboard=option_rows("p", DONE_PERIODS, period) + option_rows("o", DONE_OUTCOMES, outcome))
    header = f"Выполненные работы · {PERIOD_LABELS.get(period, period)}"
    items = result["items"]
    if not items:
        return f"{header}\nВыполненных работ пока нет.", markup
    entries = []
    for item in items[:DONE_WORKS_LIMIT]:
        cancelled = item["visit_status"] == "cancelled"
        line = f"{'❌' if cancelled else '✅'} {format_date(item['closed_at'])}"
        if item.get("plate_number"):
            line += f" · {item['plate_number']} {item.get('make_model') or ''}".rstrip()
        if cancelled:
            line += " · заезд отменён"
        entries.append(f"{line}\n{item['name']}")
    text = f"{header}\nРабот: {result['count']} · {format_hours(result['total_norm_hours'])}\n\n" + "\n\n".join(entries)
    if result["count"] > len(entries):
        text += f"\n\nПоказаны последние {len(entries)}."
    return text, markup
