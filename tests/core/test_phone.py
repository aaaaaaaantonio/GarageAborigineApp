import pytest

from app.core.phone import normalize_phone


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("+7 (999) 123-45-67", "79991234567"),
        ("89991234567", "79991234567"),
        ("9991234567", "79991234567"),
        ("7 999 123 45 67", "79991234567"),
    ],
)
def test_normalize_phone_variants_match(raw, expected):
    assert normalize_phone(raw) == expected
