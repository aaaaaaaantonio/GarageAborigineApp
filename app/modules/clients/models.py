import uuid

from sqlalchemy import Index, String, JSON, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import ClientType
from app.core.config import settings
from app.core.models import Base, SoftDeleteMixin, TimestampMixin, UUIDPkMixin


class Client(Base, UUIDPkMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "clients"
    __table_args__ = (
        # Один активный клиент на телефон; удалённые (анонимизированные) не мешают
        # повторной регистрации того же номера.
        Index(
            "uq_clients_phone_normalized_active",
            "phone_normalized",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone_normalized: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    phone_display: Mapped[str] = mapped_column(String(32), nullable=False)
    telegram_id: Mapped[int | None] = mapped_column(nullable=True)
    telegram_username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    client_type: Mapped[ClientType] = mapped_column(nullable=False, default=ClientType.INDIVIDUAL)
    legal_details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False, default=lambda: settings.default_branch_id
    )
