import uuid

from pydantic import BaseModel

from app.core.enums import PartAvailability


class PartItemCreate(BaseModel):
    work_item_id: uuid.UUID
    name: str
    article_number: str | None = None
    quantity: int = 1
    unit_price: float
    availability_status: PartAvailability = PartAvailability.IN_STOCK


class PartItemOut(BaseModel):
    id: uuid.UUID
    name: str
    quantity: int
    unit_price: float

    class Config:
        from_attributes = True
