import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Literal

from sqlalchemy import Row, Select, case, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import VisitStatus
from app.modules.clients.models import Client
from app.modules.users.models import User
from app.modules.vehicles.models import Vehicle
from app.modules.visits.models import Visit, VisitStatusLog, VisitWorkItem

CLOSED_STATUSES = (VisitStatus.ISSUED, VisitStatus.CANCELLED)
# An open visit whose status hasn't changed for this long counts as stuck.
STALE_DAYS = 3
FUNNEL = list(VisitStatus)  # enum order is the visit funnel, closed statuses last

VisitSort = Literal["date", "stale", "status", "amount"]


def status_changed_at_expr():
    """When the visit got its current status: the last status-log entry, else creation."""
    last_change = (
        select(func.max(VisitStatusLog.changed_at))
        .where(VisitStatusLog.visit_id == Visit.id)
        .correlate(Visit)
        .scalar_subquery()
    )
    return func.coalesce(last_change, Visit.created_at)


@dataclass
class VisitFilters:
    active: bool = False
    closed: bool = False
    statuses: list[VisitStatus] = field(default_factory=list)
    client_id: uuid.UUID | None = None
    vehicle_id: uuid.UUID | None = None
    master_id: uuid.UUID | None = None
    unassigned_work: bool = False
    stale: bool = False
    since: datetime | None = None
    sort: VisitSort = "date"


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
            status_changed_at_expr().label("status_changed_at"),
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

    def _filtered(self, stmt: Select, f: VisitFilters) -> Select:
        stmt = stmt.where(Visit.deleted_at.is_(None), Client.deleted_at.is_(None), Vehicle.deleted_at.is_(None))
        changed_at = status_changed_at_expr()
        if f.active or f.stale:
            stmt = stmt.where(Visit.status.not_in(CLOSED_STATUSES))
        if f.closed:
            stmt = stmt.where(Visit.status.in_(CLOSED_STATUSES))
        if f.statuses:
            stmt = stmt.where(Visit.status.in_(f.statuses))
        if f.client_id is not None:
            stmt = stmt.where(Visit.client_id == f.client_id)
        if f.vehicle_id is not None:
            stmt = stmt.where(Visit.vehicle_id == f.vehicle_id)
        if f.master_id is not None:
            stmt = stmt.where(Visit.assigned_master_id == f.master_id)
        if f.unassigned_work:
            stmt = stmt.where(
                exists().where(VisitWorkItem.visit_id == Visit.id, VisitWorkItem.assigned_mechanic_id.is_(None))
            )
        if f.stale:
            stmt = stmt.where(changed_at <= datetime.now(timezone.utc) - timedelta(days=STALE_DAYS))
        if f.since is not None:
            stmt = stmt.where(changed_at >= f.since)
        return stmt

    async def list_summaries(self, f: VisitFilters, *, viewer_id: uuid.UUID, limit: int, offset: int = 0) -> list[Row]:
        stmt = self._filtered(_summary_select(), f)
        if f.sort == "stale":
            order = [status_changed_at_expr().asc()]
        elif f.sort == "status":
            funnel = case(*[(Visit.status == s, i) for i, s in enumerate(FUNNEL)])
            order = [funnel, Visit.created_at.desc()]
        elif f.sort == "amount":
            order = [Visit.total_amount.desc(), Visit.created_at.desc()]
        elif f.client_id is None and f.vehicle_id is None:
            order = [(Visit.assigned_master_id == viewer_id).desc(), Visit.created_at.desc()]
        else:
            order = [Visit.created_at.desc()]
        stmt = stmt.order_by(*order, Visit.id).offset(offset).limit(limit)
        return list((await self.session.execute(stmt)).all())

    async def count_and_issued_amount(self, f: VisitFilters) -> tuple[int, float]:
        """Totals over the whole filter, not just the page."""
        stmt = select(
            func.count(Visit.id),
            func.coalesce(func.sum(case((Visit.status == VisitStatus.ISSUED, Visit.total_amount), else_=0)), 0),
        ).select_from(Visit).join(Client, Client.id == Visit.client_id).join(Vehicle, Vehicle.id == Visit.vehicle_id)
        count, amount = (await self.session.execute(self._filtered(stmt, f))).one()
        return count, float(amount)
