import uuid

from pydantic import BaseModel, ConfigDict, field_validator

from app.core.enums import ClientType
from app.core.phone import is_valid_phone

PHONE_FORMAT_ERROR = "Неверный формат телефона: нужен российский номер, например +7 900 123-45-67"


def check_phone(value: str) -> str:
    if not is_valid_phone(value):
        raise ValueError(PHONE_FORMAT_ERROR)
    return value


class ClientCreate(BaseModel):
    full_name: str
    phone: str  # сырой ввод, нормализуется в сервисе
    client_type: ClientType = ClientType.INDIVIDUAL
    legal_details: dict | None = None
    telegram_id: int | None = None
    telegram_username: str | None = None

    _check_phone = field_validator("phone")(check_phone)


class ClientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str
    phone_display: str
    client_type: ClientType
