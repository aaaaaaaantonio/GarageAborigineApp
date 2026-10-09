import re

# 17-значный VIN: латиница и цифры без I, O, Q.
_VIN_RE = re.compile(r"[A-HJ-NPR-Z0-9]{17}")
# Номер кузова (японские авто без VIN), например GX110-6012345.
_FRAME_RE = re.compile(r"(?=.*\d)[A-Z0-9]+(-[A-Z0-9]+)*")


def normalize_vin(raw: str) -> str:
    """Верхний регистр, без пробелов."""
    return re.sub(r"\s", "", raw).upper()


def is_valid_vin(raw: str) -> bool:
    """VIN или номер кузова. 17 символов без дефиса — только строгий VIN."""
    vin = normalize_vin(raw)
    if len(vin) == 17 and "-" not in vin:
        return bool(_VIN_RE.fullmatch(vin))
    return 6 <= len(vin) <= 17 and bool(_FRAME_RE.fullmatch(vin))
