from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from app.core.phone import normalize_phone
from app.core.plate import normalize_plate


class MatchType(str, Enum):
    EXACT = "exact"
    NORMALIZED = "normalized"
    EXACT_OR_SUFFIX = "exact_or_suffix"
    FUZZY = "fuzzy"


@dataclass(frozen=True)
class SearchField:
    entity: str  # "client" | "vehicle"
    field: str  # имя колонки в ORM-модели
    match_type: MatchType
    normalizer: Callable[[str], str] | None = None  # обязателен при match_type=NORMALIZED


SEARCH_FIELDS: list[SearchField] = [
    SearchField(entity="client", field="phone_normalized", match_type=MatchType.NORMALIZED, normalizer=normalize_phone),
    SearchField(entity="client", field="full_name", match_type=MatchType.FUZZY),
    SearchField(entity="vehicle", field="vin", match_type=MatchType.EXACT_OR_SUFFIX),
    SearchField(entity="vehicle", field="plate_number", match_type=MatchType.NORMALIZED, normalizer=normalize_plate),
    SearchField(entity="vehicle", field="make", match_type=MatchType.FUZZY),
    SearchField(entity="vehicle", field="model", match_type=MatchType.FUZZY),
]
