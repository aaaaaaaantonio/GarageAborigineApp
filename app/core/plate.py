import re


def normalize_plate(raw: str) -> str:
    """Верхний регистр, без пробелов/дефисов — для гос.номера."""
    return re.sub(r"[\s-]", "", raw).upper()
