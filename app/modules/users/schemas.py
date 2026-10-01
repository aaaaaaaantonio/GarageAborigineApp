import uuid

from pydantic import BaseModel, ConfigDict

from app.core.enums import UserRole


class UserCreate(BaseModel):
    role: UserRole
    full_name: str
    telegram_id: int | None = None
    phone: str | None = None


class UserOut(BaseModel):
    id: uuid.UUID
    role: UserRole
    full_name: str
    telegram_id: int | None
    phone: str | None
    branch_id: uuid.UUID

    model_config = ConfigDict(from_attributes=True)
