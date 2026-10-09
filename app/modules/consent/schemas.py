import uuid

from pydantic import BaseModel, field_validator

from app.core.enums import ClientType
from app.modules.clients.schemas import check_phone


class ConsentDraftOut(BaseModel):
    token: str
    expires_at: object


class ConsentConfirm(BaseModel):
    full_name: str
    phone: str
    client_type: ClientType = ClientType.INDIVIDUAL


class ConsentPaperRegister(BaseModel):
    full_name: str
    phone: str
    client_type: ClientType = ClientType.INDIVIDUAL
    verification_ref: str | None = None

    _check_phone = field_validator("phone")(check_phone)
