import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, computed_field, model_validator

from app.core.enums import VisitStatus, WorkCategory, WorkItemStatus
from app.modules.visits.work_item_flow import WORK_ITEM_NEXT_STATUSES


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


class WorkItemMechanicChange(BaseModel):
    assigned_mechanic_id: uuid.UUID | None


class WorkItemOut(BaseModel):
    id: uuid.UUID
    visit_id: uuid.UUID
    name: str
    status: WorkItemStatus
    approved_by_client: bool
    free_text_name: str | None
    catalog_item_id: uuid.UUID | None
    assigned_mechanic_id: uuid.UUID | None
    assigned_mechanic_name: str | None = None

    @computed_field
    @property
    def allowed_next_statuses(self) -> list[WorkItemStatus]:
        return list(WORK_ITEM_NEXT_STATUSES[self.status])

    model_config = ConfigDict(from_attributes=True)


class WorkItemMineOut(BaseModel):
    id: uuid.UUID
    visit_id: uuid.UUID
    name: str
    status: WorkItemStatus
    free_text_name: str | None
    catalog_item_id: uuid.UUID | None
    plate_number: str | None = None
    make_model: str | None = None

    @computed_field
    @property
    def allowed_next_statuses(self) -> list[WorkItemStatus]:
        return list(WORK_ITEM_NEXT_STATUSES[self.status])

    model_config = ConfigDict(from_attributes=True)


class VehicleWorkHistoryItemOut(BaseModel):
    """Deliberately no prices, hours or client data: mechanics read this."""

    visit_id: uuid.UUID
    visit_at: datetime
    mileage: int
    name: str
    status: WorkItemStatus
    category: WorkCategory


class VehicleWorkHistoryOut(BaseModel):
    items: list[VehicleWorkHistoryItemOut]
    has_more: bool


class WorkItemDoneOut(BaseModel):
    """A finished work item in a closed visit — read-only history for the mechanic."""

    id: uuid.UUID
    visit_id: uuid.UUID
    name: str
    plate_number: str | None = None
    make_model: str | None = None
    visit_status: VisitStatus
    visit_date: datetime
    closed_at: datetime
    norm_hours: float

    model_config = ConfigDict(from_attributes=True)


class WorkItemDoneListOut(BaseModel):
    """No money here: the mechanic sees norm-hours only."""

    items: list[WorkItemDoneOut]
    count: int
    total_norm_hours: float
    has_more: bool

    model_config = ConfigDict(from_attributes=True)
