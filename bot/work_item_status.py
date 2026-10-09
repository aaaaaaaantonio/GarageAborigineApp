"""Work-item status labels, icons and the MVP next-status flow.

Backend publishes no transition graph for work items (any status may be
PATCHed), so the bot offers the next steps of the MVP flow
not_ready → in_progress → waiting_parts/ready; `ready` is terminal.
"""

NEXT_WORK_ITEM_STATUSES: dict[str, list[str]] = {
    "not_ready": ["in_progress"],
    "in_progress": ["waiting_parts", "ready"],
    "waiting_parts": ["in_progress", "ready"],
}

WORK_ITEM_STATUS_LABELS: dict[str, str] = {
    "not_ready": "Не начата",
    "in_progress": "В работе",
    "waiting_parts": "Ждёт запчасти",
    "ready": "Готово",
}

WORK_ITEM_STATUS_ICONS: dict[str, str] = {
    "not_ready": "⏳",
    "in_progress": "🔧",
    "waiting_parts": "📦",
    "ready": "✅",
}


def work_item_icon(code: str) -> str:
    return WORK_ITEM_STATUS_ICONS.get(code, "•")


def work_item_status_label(code: str) -> str:
    return WORK_ITEM_STATUS_LABELS.get(code, code)
