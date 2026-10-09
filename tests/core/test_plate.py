from app.core.plate import normalize_plate


def test_normalize_plate_strips_spaces_and_uppercases():
    assert normalize_plate("а 123 вс 77") == "А123ВС77"
    assert normalize_plate("а-123-вс-77") == "А123ВС77"


def test_normalize_plate_maps_latin_lookalikes_to_cyrillic():
    assert normalize_plate("A123BC77") == "А123ВС77"
    assert normalize_plate("x 000 xx 799") == "Х000ХХ799"
    assert normalize_plate("A123ВС77") == normalize_plate("А123BC77")  # mixed input
