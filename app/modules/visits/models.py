import uuid
from datetime import datetime

from sqlalchemy import String, ForeignKey, Numeric, Boolean, JSON, DateTime
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import settings
from app.core.enums import VisitStatus
from app.core.models import Base, SoftDeleteMixin, TimestampMixin, UUIDPkMixin


class Visit(Base, UUIDPkMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "visits"

    branch_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False, default=lambda: settings.default_branch_id
    )
    client_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    vehicle_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("vehicles.id"), nullable=False)
    planned_ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    mileage_at_intake: Mapped[int] = mapped_column(nullable=False)
    mileage_manually_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[VisitStatus] = mapped_column(nullable=False, default=VisitStatus.RECEIVED)
    assigned_master_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    complaint_text: Mapped[str | None] = mapped_column(String, nullable=True)
    intake_photos: Mapped[list | None] = mapped_column(JSON, nullable=True)
    total_amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    discount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    cancelled_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    document_url: Mapped[str | None] = mapped_column(String, nullable=True)
