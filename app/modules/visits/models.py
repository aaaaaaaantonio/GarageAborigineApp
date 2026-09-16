import uuid
from datetime import datetime

from sqlalchemy import String, ForeignKey, Numeric, Boolean, JSON, DateTime, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import settings
from app.core.enums import ApprovedVia, VisitStatus, WorkCategory, WorkItemStatus
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


class VisitWorkItem(Base, UUIDPkMixin):
    __tablename__ = "visit_work_items"

    visit_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("visits.id"), nullable=False)
    catalog_item_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("work_catalog.id"), nullable=True
    )
    free_text_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    category: Mapped[WorkCategory] = mapped_column(nullable=False)
    norm_hours: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    hourly_rate: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    status: Mapped[WorkItemStatus] = mapped_column(nullable=False)
    assigned_mechanic_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    comment: Mapped[str | None] = mapped_column(String, nullable=True)
    is_extra_work: Mapped[bool] = mapped_column(Boolean, default=False)
    approved_by_client: Mapped[bool] = mapped_column(Boolean, default=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_via: Mapped[ApprovedVia | None] = mapped_column(nullable=True)
    progress_photos: Mapped[list | None] = mapped_column(JSON, nullable=True)


class VisitStatusLog(Base, UUIDPkMixin):
    __tablename__ = "visit_status_log"

    visit_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("visits.id"), nullable=False)
    from_status: Mapped[VisitStatus | None] = mapped_column(nullable=True)
    to_status: Mapped[VisitStatus] = mapped_column(nullable=False)
    changed_by_user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    reason: Mapped[str | None] = mapped_column(String, nullable=True)
