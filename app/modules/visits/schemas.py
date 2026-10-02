import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.core.enums import VisitStatus


class VisitCreate(BaseModel):
    client_id: uuid.UUID
    vehicle_id: uuid.UUID
    assigned_master_id: uuid.UUID
    mileage_at_intake: int
    mileage_manually_confirmed: bool = False
    complaint_text: str | None = None
    intake_photos: list[str] | None = None


class VisitStatusChange(BaseModel):
    new_status: VisitStatus
    reason: str | None = None


class VisitOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: VisitStatus
    mileage_at_intake: int
    total_amount: float
    created_at: datetime
    client_id: uuid.UUID
    client_name: str
    vehicle_id: uuid.UUID
    plate_number: str
    make_model: str
    assigned_master_id: uuid.UUID
    master_name: str


class VisitListOut(BaseModel):
    items: list[VisitOut]
    has_more: bool
