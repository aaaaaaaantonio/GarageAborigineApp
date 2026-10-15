from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot import nav
from bot.api_client import ApiClient
from bot.formatting import format_date, format_hours, format_number
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
    opened = args.get(nav.OPEN, "-")
    rows = nav.dropdown("Статус", "st", MY_STATUSES, status, opened) + nav.dropdown("Порядок", "s", MY_SORTS, sort, opened)
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
    opened = args.get(nav.OPEN, "-")
    markup = InlineKeyboardMarkup(
        inline_keyboard=nav.dropdown("Период", "p", DONE_PERIODS, period, opened) + nav.dropdown("Итог", "o", DONE_OUTCOMES, outcome, opened)
    )
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


MECH_VISIT_TEXT_LIMIT = 3800  # keeps the card under Telegram's 4096 chars
TRUNCATED_NOTE = "…показаны не все работы — откройте карточку в веб-приложении"
NO_SCHEME = "схема оплаты не задана"


def _rub(value) -> str:
    return f"{format_number(value)} ₽"


def _pay(value) -> str:
    return NO_SCHEME if value is None else _rub(value)


@nav.screen("mech_visit", params=("visit_id",))
async def render_mech_visit(api: ApiClient, user: dict, args: dict) -> nav.Rendered:
    """The visit card for a mechanic: the server already left out what the admin hides."""
    v = await api.get_mechanic_view(args["visit_id"])
    prices = v["total_amount"] is not None
    lines = [
        f"🚗 {v['plate_number']} · {v['make_model']}",
        f"Пробег: {format_number(v['mileage_at_intake'])} км · Мастер: {v['master_name']}",
    ]
    for label, key in (("Клиент", "client_name"), ("Телефон", "client_phone"), ("VIN", "vin")):
        if v.get(key):
            lines.append(f"{label}: {v[key]}")
        if key == "client_phone" and v.get("client_telegram_username"):
            lines.append(f"Telegram: @{v['client_telegram_username'].lstrip('@')}")
    footer: list[str] = []
    if prices:
        footer.append("")
        if v["discount"]:
            footer.append(f"Скидка: {_rub(v['discount'])}")
        footer += [f"Итого по заезду: {_rub(v['total_amount'])}", f"Ваш заработок по заезду: {_pay(v['my_pay_total'])}"]
    used = len("\n".join(lines + footer)) + len(TRUNCATED_NOTE) + 2
    truncated = False
    for w in v["works"]:
        block = ["", f"{work_item_icon(w['status'])} {w['name']}{' · моя' if w['is_mine'] else ''}"]
        detail = f"   {w['mechanic_name'] or 'без исполнителя'} · {format_hours(w['norm_hours'])}"
        block.append(detail + (f" · {_rub(w['amount'])}" if prices and w["amount"] is not None else ""))
        if prices and w["is_mine"]:
            block.append(f"   Ваш заработок: {_pay(w['my_pay'])}")
        for p in w["parts"]:
            block.append(f"   🔩 {p['name']} × {p['quantity']}" + (f" · {_rub(p['amount'])}" if p["amount"] is not None else ""))
        size = len("\n".join(block)) + 1
        if used + size > MECH_VISIT_TEXT_LIMIT:
            truncated = True
            break
        used += size
        lines += block
    if truncated:
        lines += ["", TRUNCATED_NOTE]
    lines += footer
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=[])
