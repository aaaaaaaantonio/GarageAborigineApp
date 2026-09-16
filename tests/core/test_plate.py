from app.core.plate import normalize_plate


def test_normalize_plate_strips_spaces_and_uppercases():
    assert normalize_plate("а 123 вс 77") == "А123ВС77"
    assert normalize_plate("а-123-вс-77") == "А123ВС77"
