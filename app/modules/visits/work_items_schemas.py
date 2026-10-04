import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, model_validator

from app.core.enums import WorkCategory, WorkItemStatus


class WorkItemCreate(BaseModel):
    catalog_item_id: uuid.UUID | None = None
    free_text_name: str | None = None
    category: WorkCategory
    norm_hours: float
    hourly_rate: float
    assigned_mechanic_id: uuid.UUID | None = None
    is_extra_work: bool = False
    comment: str | None = None

    @model_validator(mode="after")
    def check_name_source(self):
        if bool(self.catalog_item_id) == bool(self.free_text_name):
            raise ValueError("Укажите ровно одно: catalog_item_id или free_text_name")
        return self


class WorkItemStatusChange(BaseModel):
    new_status: WorkItemStatus


class WorkItemOut(BaseModel):
    id: uuid.UUID
    visit_id: uuid.UUID
    name: str
    status: WorkItemStatus
    approved_by_client: bool
    free_text_name: str | None
    catalog_item_id: uuid.UUID | None

    model_config = ConfigDict(from_attributes=True)


class WorkItemMineOut(BaseModel):
    id: uuid.UUID
    visit_id: uuid.UUID
    name: str
    status: WorkItemStatus
    free_text_name: str | None
    catalog_item_id: uuid.UUID | None

    model_config = ConfigDict(from_attributes=True)


class VehicleWorkHistoryItemOut(BaseModel):
    """Deliberately no prices, hours or client data: mechanics read this."""

    visit_id: uuid.UUID
    visit_at: datetime
    mileage: int
    name: str
    status: WorkItemStatus


class VehicleWorkHistoryOut(BaseModel):
    items: list[VehicleWorkHistoryItemOut]
    has_more: bool
