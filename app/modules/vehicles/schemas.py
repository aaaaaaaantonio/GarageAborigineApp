import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict


class VehicleCreate(BaseModel):
    vin: str
    plate_number: str
    make: str
    model: str
    modification: str | None = None
    year: int | None = None
    color: str | None = None


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
