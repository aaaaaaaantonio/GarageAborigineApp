"""Russian labels for visit statuses (API codes stay in callback_data)."""

VISIT_STATUS_LABELS: dict[str, str] = {
    "received": "Принят",
    "diagnostics": "Диагностика",
    "approval": "Согласование",
    "in_progress": "Ремонт",
    "waiting_parts": "Ждём запчасти",
    "ready": "Готов",
    "issued": "Выдан",
    "cancelled": "Отменён",
}


def visit_status_label(code: str) -> str:
    return VISIT_STATUS_LABELS.get(code, code)
