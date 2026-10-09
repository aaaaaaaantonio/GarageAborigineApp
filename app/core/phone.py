import re


def normalize_phone(raw: str) -> str:
    """Приводит телефон к формату '7XXXXXXXXXX' (11 цифр, без +).
    '+7', '8', скобки/дефисы/пробелы — всё игнорируется, кроме цифр."""
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 11 and digits[0] == "8":
        digits = "7" + digits[1:]
    if len(digits) == 10:
        digits = "7" + digits
    return digits


def is_valid_phone(raw: str) -> bool:
    """Российский номер: после нормализации — 11 цифр, начиная с 7."""
    digits = normalize_phone(raw)
    return len(digits) == 11 and digits[0] == "7"
