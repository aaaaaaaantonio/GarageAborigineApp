import uuid

from pydantic import BaseModel, ConfigDict

from app.core.enums import WorkCategory


class WorkCatalogCreate(BaseModel):
    name: str
    category: WorkCategory
    default_norm_hours: float


class WorkCatalogOut(BaseModel):
    id: uuid.UUID
    name: str
    category: WorkCategory
    default_norm_hours: float

    model_config = ConfigDict(from_attributes=True)
