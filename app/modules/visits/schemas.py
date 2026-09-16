import uuid

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


class VisitOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: VisitStatus
    mileage_at_intake: int
    total_amount: float
