"""Staff-only lists: the visit archive and the work board."""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot import nav
from bot.api_client import ApiClient
from bot.callback_ids import decode_id, encode_id
from bot.formatting import format_day, format_number
from bot.handlers.navigation import master_cycle, option_rows
from bot.periods import PERIOD_LABELS, since_for
from bot.visit_status import visit_status_label
from bot.work_item_status import WORK_ITEM_STATUS_LABELS, work_item_icon

ARCHIVE_PAGE = 30  # GET /visits page size
BOARD_TEXT_LIMIT = 40  # lines in the message; keeps it far below Telegram's 4096 chars
BOARD_BUTTONS = 30

ARCHIVE_PERIODS = [(p, PERIOD_LABELS[p]) for p in ("week", "month", "quarter", "all")]
ARCHIVE_OUTCOMES = [("all", "Все"), ("issued", "Выданы"), ("cancelled", "Отменены")]
ARCHIVE_SORTS = [("date", "По дате"), ("amount", "По сумме")]
OUTCOME_ICONS = {"issued": "✅", "cancelled": "❌"}

CATEGORY_LABELS = {
    "diagnostics": "Диагностика", "maintenance": "ТО", "body": "Кузовные",
    "electrical": "Электрика", "chassis": "Ходовая", "other": "Прочее",
}
BOARD_GROUPS = [("mechanic", "По механику"), ("status", "По статусу"), ("car", "По машине")]


@nav.screen("archive")
async def render_archive(api: ApiClient, user: dict, args: dict) -> nav.Rendered:
    period, outcome, sort = args.get("p", "month"), args.get("o", "all"), args.get("s", "date")
    master, page = args.get("m", "-"), int(args.get("page", 0))
    params = {"closed": True, "since": since_for(period), "sort": sort, "offset": page * ARCHIVE_PAGE}
    if outcome != "all":
        params["status"] = [outcome]
    if user["role"] == "admin" and master != "-":
        params["master_id"] = decode_id(master)
    result = await api.list_visits(**params)
    rows = option_rows("p", ARCHIVE_PERIODS, period, per_row=4) + option_rows("o", ARCHIVE_OUTCOMES, outcome)
    controls = [nav.cycle_button("↕", "s", ARCHIVE_SORTS, sort)]
    if user["role"] == "admin":
        controls.append(await master_cycle(api, master))
    rows.append(controls)
    header = f"🗄 Архив заездов · {PERIOD_LABELS.get(period, period)}"
    visits = result["items"]
    if not visits:
        return f"{header}\nЗа этот период закрытых заездов нет.", InlineKeyboardMarkup(inline_keyboard=rows)
    for visit in visits:
        label = " · ".join([
            format_day(visit["status_changed_at"]), visit["plate_number"],
            f"{OUTCOME_ICONS.get(visit['status'], '')} {visit_status_label(visit['status'])}".strip(),
            f"{format_number(visit['total_amount'])} ₽",
        ])
        rows.append([InlineKeyboardButton(text=label, callback_data=nav.go_data("visit", visit["id"]))])
    total = result.get("total_count", len(visits))
    text = f"{header}\nЗаездов: {total} · Выручка: {format_number(result.get('issued_amount', 0))} ₽"
    pages = -(-total // ARCHIVE_PAGE)
    if pages > 1:
        text += f"\nстр. {page + 1}/{pages}"
        arrows = []
        if page > 0:
            arrows.append(InlineKeyboardButton(text="‹ Пред.", callback_data=f"{nav.OPT}:page:{page - 1}"))
        if result["has_more"]:
            arrows.append(InlineKeyboardButton(text="Далее ›", callback_data=f"{nav.OPT}:page:{page + 1}"))
        rows.append(arrows)
    return text, InlineKeyboardMarkup(inline_keyboard=rows)


def _board_title(item: dict, group: str) -> str:
    if group == "status":
        return WORK_ITEM_STATUS_LABELS.get(item["status"], item["status"])
    if group == "car":
        return f"{item.get('plate_number') or '—'} · {item.get('make_model') or ''}".strip()
    return item.get("assigned_mechanic_name") or "Без исполнителя"


def _board_line(item: dict, group: str) -> str:
    parts = [f"{work_item_icon(item['status'])} {item['name']}"]
    if group != "car" and item.get("plate_number"):
        parts.append(item["plate_number"])
    if group != "mechanic":
        parts.append(item.get("assigned_mechanic_name") or "без исполнителя")
    if not item.get("approved_by_client", True):
        parts.append("не согласовано")
    return " · ".join(parts)


@nav.screen("board")
async def render_board(api: ApiClient, user: dict, args: dict) -> nav.Rendered:
    mech, status, category = args.get("mech", "all"), args.get("st", "all"), args.get("cat", "all")
    unapproved, group = args.get("un", "0") == "1", args.get("g", "mechanic")
    params: dict = {}
    if mech == "none":
        params["unassigned"] = True
    elif mech != "all":
        params["mechanic_id"] = decode_id(mech)
    if status != "all":
        params["status"] = [status]
    if category != "all":
        params["category"] = [category]
    if unapproved:
        params["unapproved"] = True
    result = await api.list_work_board(**params, group=group)
    mechanics = await api.list_mechanics()
    mech_options = [("all", "Все механики"), ("none", "Без исполнителя"),
                    *[(encode_id(m["id"]), m["full_name"]) for m in mechanics]]
    rows = [
        [nav.cycle_button("👤", "mech", mech_options, mech)],
        [nav.cycle_button("🔧", "st", [("all", "Все статусы"), *WORK_ITEM_STATUS_LABELS.items()], status),
         nav.cycle_button("🏷", "cat", [("all", "Все категории"), *CATEGORY_LABELS.items()], category)],
        [InlineKeyboardButton(text=("✓ " if unapproved else "") + "Не согласованные",
                              callback_data=f"{nav.OPT}:un:{'0' if unapproved else '1'}"),
         nav.cycle_button("↕", "g", BOARD_GROUPS, group)],
    ]
    items = result["items"]
    if not items:
        return "📋 Доска работ\nРабот с этим фильтром нет.", InlineKeyboardMarkup(inline_keyboard=rows)
    lines, current = [f"📋 Доска работ ({len(items)})"], None
    for item in items[:BOARD_TEXT_LIMIT]:
        title = _board_title(item, group)
        if title != current:
            current = title
            lines += ["", title]
        lines.append(f"  {_board_line(item, group)}")
    if len(items) > BOARD_TEXT_LIMIT or result["has_more"]:
        lines += ["", f"Показаны первые {min(len(items), BOARD_TEXT_LIMIT)}. Сузьте фильтр."]
    for item in items[:BOARD_BUTTONS]:
        label = f"{work_item_icon(item['status'])} {item['name']}"
        if item.get("plate_number"):
            label += f" · {item['plate_number']}"
        rows.append([InlineKeyboardButton(text=label, callback_data=nav.go_data("work", item["visit_id"], item["id"]))])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)
