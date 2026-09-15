import uuid

from pydantic import BaseModel, ConfigDict

from app.core.enums import ClientType


class ClientCreate(BaseModel):
    full_name: str
    phone: str  # сырой ввод, нормализуется в сервисе
    client_type: ClientType = ClientType.INDIVIDUAL
    legal_details: dict | None = None
    telegram_id: int | None = None
    telegram_username: str | None = None


class ClientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str
    phone_display: str
    client_type: ClientType
