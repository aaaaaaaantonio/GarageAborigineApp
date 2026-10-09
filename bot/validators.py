"""Input format checks for wizards. Same rules as the API (app/core/phone.py,
app/core/vin.py): the bot re-asks the step instead of getting a 422."""
import re

PHONE_FORMAT_ERROR = "Неверный формат телефона. Пример: +7 900 123-45-67"
VIN_FORMAT_ERROR = (
    "Неверный формат VIN: 17 символов (латиница и цифры без I, O, Q) "
    "или номер кузова, например GX110-6012345."
)

_VIN_RE = re.compile(r"[A-HJ-NPR-Z0-9]{17}")
_FRAME_RE = re.compile(r"(?=.*\d)[A-Z0-9]+(-[A-Z0-9]+)*")
# Russian plate: letter, 3 digits, 2 letters, region. Latin look-alikes allowed.
_PLATE_LETTERS = "АВЕКМНОРСТУХABEKMHOPCTYX"
_PLATE_RE = re.compile(rf"[{_PLATE_LETTERS}]\d{{3}}[{_PLATE_LETTERS}]{{2}}\d{{2,3}}")


def normalize_phone(raw: str) -> str:
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 11 and digits[0] == "8":
        digits = "7" + digits[1:]
    if len(digits) == 10:
        digits = "7" + digits
    return digits


def is_valid_phone(raw: str) -> bool:
    digits = normalize_phone(raw)
    return len(digits) == 11 and digits[0] == "7"


def normalize_vin(raw: str) -> str:
    return re.sub(r"\s", "", raw).upper()


def is_valid_vin(raw: str) -> bool:
    """17-char VIN, or a frame number for Japanese cars without one."""
    vin = normalize_vin(raw)
    if len(vin) == 17 and "-" not in vin:
        return bool(_VIN_RE.fullmatch(vin))
    return 6 <= len(vin) <= 17 and bool(_FRAME_RE.fullmatch(vin))


def normalize_plate(raw: str) -> str:
    return re.sub(r"[\s-]", "", raw).upper()


def looks_like_plate(raw: str) -> bool:
    return bool(_PLATE_RE.fullmatch(normalize_plate(raw)))
