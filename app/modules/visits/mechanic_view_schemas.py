import uuid
from datetime import datetime

from pydantic import BaseModel

from app.core.enums import PartAvailability, VisitStatus, WorkCategory, WorkItemStatus


class MechanicPartOut(BaseModel):
    name: str
    article_number: str | None
    quantity: int
    availability_status: PartAvailability
    unit_price: float | None
    amount: float | None


class MechanicWorkOut(BaseModel):
    id: uuid.UUID
    name: str
    category: WorkCategory
    status: WorkItemStatus
    mechanic_name: str | None
    is_mine: bool
    norm_hours: float
    hourly_rate: float | None
    amount: float | None
    my_pay: float | None
    parts: list[MechanicPartOut]


class MechanicVisitOut(BaseModel):
    """The visit card for a mechanic. Fields the admin's settings hide are None."""

    id: uuid.UUID
    status: VisitStatus
    created_at: datetime
    mileage_at_intake: int
    plate_number: str
    make_model: str
    master_name: str
    client_name: str | None
    client_phone: str | None
    client_telegram_username: str | None
    vin: str | None
    discount: float | None
    total_amount: float | None
    my_pay_total: float | None
    works: list[MechanicWorkOut]
