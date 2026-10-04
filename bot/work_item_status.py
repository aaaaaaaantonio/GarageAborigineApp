"""Work-item status buttons, shared by the visit card and "Мои работы".

Backend publishes no transition graph for work items (any status may be
PATCHed), so the bot offers the next steps of the MVP flow
not_ready → in_progress → waiting_parts/ready; `ready` is terminal.
"""
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.callback_ids import encode_id

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


def work_item_status_label(code: str) -> str:
    return WORK_ITEM_STATUS_LABELS.get(code, code)


# callback_data prefixes: which screen the button lives on, so the shared
# handler knows what to show after the change. Longest payload:
# "wsc:" + 22 + ":" + 22 + ":waiting_parts" = 63 bytes.
FROM_VISIT_CARD = "wsc"
FROM_MY_WORK_ITEMS = "wsm"


def add_work_status_buttons(
    builder: InlineKeyboardBuilder, visit_id: str, item: dict, origin: str, label_prefix: str = ""
) -> int:
    """Add one button per allowed next status; returns how many were added."""
    next_statuses = NEXT_WORK_ITEM_STATUSES.get(item["status"], [])
    for status in next_statuses:
        builder.button(
            text=f"{label_prefix}→ {work_item_status_label(status)}",
            callback_data=f"{origin}:{encode_id(visit_id)}:{encode_id(item['id'])}:{status}",
        )
    return len(next_statuses)
