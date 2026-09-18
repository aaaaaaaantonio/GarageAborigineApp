import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, UUIDPkMixin


class RecentView(Base, UUIDPkMixin):
    __tablename__ = "recent_views"

    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    viewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
