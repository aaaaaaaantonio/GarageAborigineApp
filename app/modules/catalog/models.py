import uuid

from sqlalchemy import Index, String, ForeignKey, Numeric
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import WorkCategory
from app.core.models import Base, SoftDeleteMixin, TimestampMixin, UUIDPkMixin


class WorkCatalog(Base, UUIDPkMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "work_catalog"
    __table_args__ = (
        Index(
            "ix_work_catalog_name_trgm",
            "name",
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops"},
        ),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[WorkCategory] = mapped_column(nullable=False)
    default_norm_hours: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
