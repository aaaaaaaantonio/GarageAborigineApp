import uuid

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import UserRole
from app.core.models import Base, SoftDeleteMixin, UUIDPkMixin
from app.core.config import settings


class User(Base, UUIDPkMixin, SoftDeleteMixin):
    __tablename__ = "users"

    role: Mapped[UserRole] = mapped_column(nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    telegram_id: Mapped[int | None] = mapped_column(nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False, default=lambda: settings.default_branch_id
    )
