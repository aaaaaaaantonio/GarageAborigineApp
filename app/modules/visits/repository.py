import uuid

from sqlalchemy import Row, Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import VisitStatus
from app.modules.clients.models import Client
from app.modules.users.models import User
from app.modules.vehicles.models import Vehicle
from app.modules.visits.models import Visit

CLOSED_STATUSES = (VisitStatus.ISSUED, VisitStatus.CANCELLED)


def _summary_select() -> Select:
    """One row per visit with the names a list or card header needs (no N+1)."""
    return (
        select(
            Visit.id,
            Visit.status,
            Visit.mileage_at_intake,
            Visit.total_amount,
            Visit.created_at,
            Visit.client_id,
            Client.full_name.label("client_name"),
            Visit.vehicle_id,
            Vehicle.plate_number,
            Vehicle.make,
            Vehicle.model,
            Visit.assigned_master_id,
            User.full_name.label("master_name"),
        )
        .join(Client, Client.id == Visit.client_id)
        .join(Vehicle, Vehicle.id == Visit.vehicle_id)
        .join(User, User.id == Visit.assigned_master_id)
    )


class VisitRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, visit: Visit) -> Visit:
        self.session.add(visit)
        await self.session.flush()
        return visit

    async def get(self, visit_id: uuid.UUID) -> Visit | None:
        return await self.session.get(Visit, visit_id)

    async def get_summary(self, visit_id: uuid.UUID) -> Row | None:
        result = await self.session.execute(_summary_select().where(Visit.id == visit_id))
        return result.first()

    async def list_summaries(
        self,
        *,
        viewer_id: uuid.UUID,
        active: bool,
        client_id: uuid.UUID | None,
        vehicle_id: uuid.UUID | None,
        limit: int,
    ) -> list[Row]:
        stmt = _summary_select().where(
            Visit.deleted_at.is_(None), Client.deleted_at.is_(None), Vehicle.deleted_at.is_(None)
        )
        if active:
            stmt = stmt.where(Visit.status.not_in(CLOSED_STATUSES))
        if client_id is not None:
            stmt = stmt.where(Visit.client_id == client_id)
        if vehicle_id is not None:
            stmt = stmt.where(Visit.vehicle_id == vehicle_id)
        if client_id is None and vehicle_id is None:
            stmt = stmt.order_by(
                (Visit.assigned_master_id == viewer_id).desc(), Visit.created_at.desc(), Visit.id
            )
        else:
            stmt = stmt.order_by(Visit.created_at.desc(), Visit.id)
        stmt = stmt.limit(limit)
        return list((await self.session.execute(stmt)).all())
