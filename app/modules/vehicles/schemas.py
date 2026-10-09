import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict, field_validator

from app.core.vin import is_valid_vin, normalize_vin


class VehicleCreate(BaseModel):
    vin: str
    plate_number: str
    make: str
    model: str
    modification: str | None = None
    year: int | None = None
    color: str | None = None

    @field_validator("vin")
    @classmethod
    def check_vin(cls, value: str) -> str:
        if not is_valid_vin(value):
            raise ValueError("Неверный формат VIN: 17 символов (латиница и цифры без I, O, Q) или номер кузова")
        return normalize_vin(value)


class VehicleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    vin: str
    plate_number: str
    make: str
    model: str
    mileage_current: int


class OwnershipCreate(BaseModel):
    client_id: uuid.UUID
    date_from: date
    show_history_before_ownership: bool = False
