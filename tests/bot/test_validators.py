import pytest

from bot.validators import is_valid_phone, is_valid_vin, looks_like_plate, normalize_plate, normalize_vin


@pytest.mark.parametrize("raw", ["+7 (999) 123-45-67", "89991234567", "9991234567"])
def test_valid_phones(raw):
    assert is_valid_phone(raw)


@pytest.mark.parametrize("raw", ["", "123", "+380 99 123 45 67", "799912345678", "Иванов"])
def test_invalid_phones(raw):
    assert not is_valid_phone(raw)


@pytest.mark.parametrize("raw", ["JTDBR32E720012345", "jtdbr32e 720012345", "GX110-6012345"])
def test_valid_vins(raw):
    assert is_valid_vin(raw)


@pytest.mark.parametrize("raw", ["", "ABC12", "JTDBR32E72001234O", "А123ВС77", "ABCDEFG"])
def test_invalid_vins(raw):
    assert not is_valid_vin(raw)


def test_normalize_vin():
    assert normalize_vin(" gx110-6012345 ") == "GX110-6012345"


@pytest.mark.parametrize("raw", ["А123ВС77", "а 123 вс 777", "A123BC77", "Х000ХХ-99"])
def test_plates(raw):
    assert looks_like_plate(raw)


@pytest.mark.parametrize("raw", ["JTDBR32E720012345", "GX110-6012345", "А123", "Иванов"])
def test_not_plates(raw):
    assert not looks_like_plate(raw)


def test_normalize_plate():
    assert normalize_plate("а 123 вс-77") == "А123ВС77"
