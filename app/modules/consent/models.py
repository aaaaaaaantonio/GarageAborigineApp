import uuid
from datetime import datetime

from sqlalchemy import BigInteger, String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import ConsentMethod
from app.core.models import Base, TimestampMixin, UUIDPkMixin


class ConsentDraft(Base, UUIDPkMixin, TimestampMixin):
    __tablename__ = "consent_drafts"

    token: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    converted_client_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("clients.id"), nullable=True
    )


class Consent(Base, UUIDPkMixin, TimestampMixin):
    __tablename__ = "consents"

    client_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("clients.id"), nullable=True)
    draft_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("consent_drafts.id"), nullable=True)
    consent_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consent_text_version: Mapped[str] = mapped_column(String(32), nullable=False)
    consent_method: Mapped[ConsentMethod] = mapped_column(nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    verification_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
