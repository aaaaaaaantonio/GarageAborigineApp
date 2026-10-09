import re

# Латинские буквы, совпадающие по виду с буквами российских номеров.
# Номер хранится и ищется кириллицей, так что A123BC77 == А123ВС77.
_LATIN_TO_CYRILLIC = str.maketrans("ABEKMHOPCTYX", "АВЕКМНОРСТУХ")


def normalize_plate(raw: str) -> str:
    """Верхний регистр, без пробелов/дефисов, латиница-двойники → кириллица."""
    return re.sub(r"[\s-]", "", raw).upper().translate(_LATIN_TO_CYRILLIC)
