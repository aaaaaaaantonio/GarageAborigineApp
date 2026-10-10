import uuid

from pydantic import BaseModel

from app.core.enums import WorkItemStatus


class PartLineOut(BaseModel):
    id: uuid.UUID
    work_item_id: uuid.UUID
    name: str
    quantity: int
    unit_price: float
    amount: float


class WorkLineOut(BaseModel):
    id: uuid.UUID
    name: str
    status: WorkItemStatus
    assigned_mechanic_name: str | None
    approved_by_client: bool
    norm_hours: float
    hourly_rate: float
    amount: float
    parts: list[PartLineOut]


class VisitLinesOut(BaseModel):
    """Priced lines of a visit — staff only (mechanics never see prices)."""

    works: list[WorkLineOut]
    works_total: float
    parts_total: float
    discount: float
    total: float
