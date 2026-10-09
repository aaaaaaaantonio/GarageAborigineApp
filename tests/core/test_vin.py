import pytest

from app.core.vin import is_valid_vin, normalize_vin


def test_normalize_vin_uppercases_and_drops_spaces():
    assert normalize_vin(" jtdbr32e 720012345 ") == "JTDBR32E720012345"


@pytest.mark.parametrize("raw", ["JTDBR32E720012345", "GX110-6012345", "JZX100-0123456", "AE1110012345"])
def test_valid_vins_and_frame_numbers(raw):
    assert is_valid_vin(raw)


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "ABC12",  # too short
        "JTDBR32E7200123456",  # 18 chars
        "JTDBR32E72001234O",  # O is not allowed in a 17-char VIN
        "А123ВС77",  # Cyrillic: a plate, not a VIN
        "GX110_6012345",
        "ABCDEFG",  # frame number needs a digit
    ],
)
def test_invalid_vins(raw):
    assert not is_valid_vin(raw)
