import uuid

from pydantic import BaseModel

from app.core.enums import ClientType


class ConsentDraftOut(BaseModel):
    token: str
    expires_at: object


class ConsentConfirm(BaseModel):
    full_name: str
    phone: str
    client_type: ClientType = ClientType.INDIVIDUAL
    ip_address: str | None = None


class ConsentPaperRegister(BaseModel):
    full_name: str
    phone: str
    client_type: ClientType = ClientType.INDIVIDUAL
    verification_ref: str | None = None
