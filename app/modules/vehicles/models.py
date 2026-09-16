import uuid
from datetime import date

from sqlalchemy import String, ForeignKey, Boolean, Date
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, SoftDeleteMixin, TimestampMixin, UUIDPkMixin


class Vehicle(Base, UUIDPkMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "vehicles"

    vin: Mapped[str] = mapped_column(String(17), nullable=False, unique=True, index=True)
    plate_number: Mapped[str] = mapped_column(String(16), nullable=False)
    make: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    modification: Mapped[str | None] = mapped_column(String(128), nullable=True)
    year: Mapped[int | None] = mapped_column(nullable=True)
    color: Mapped[str | None] = mapped_column(String(32), nullable=True)
    mileage_current: Mapped[int] = mapped_column(nullable=False, default=0)


class VehicleOwnership(Base, UUIDPkMixin):
    __tablename__ = "vehicle_ownership"

    vehicle_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("vehicles.id"), nullable=False
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("clients.id"), nullable=False
    )
    date_from: Mapped[date] = mapped_column(Date, nullable=False)
    date_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    show_history_before_ownership: Mapped[bool] = mapped_column(Boolean, default=False)
