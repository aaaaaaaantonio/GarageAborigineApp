# app/modules/stats/repository.py
"""Read-only row fetches for statistics; sums and grouping happen in the service (volumes are small)."""
import uuid
from datetime import datetime

from sqlalchemy import Row, Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.enums import VisitStatus, WorkItemStatus
from app.modules.catalog.models import WorkCatalog
from app.modules.clients.models import Client
from app.modules.stats.periods import Window
from app.modules.users.models import User
from app.modules.vehicles.models import Vehicle
from app.modules.visits.models import Visit, VisitPartItem, VisitStatusLog, VisitWorkItem
from app.modules.visits.repository import CLOSED_STATUSES


def _alive(stmt: Select) -> Select:
    """Only visits whose visit, client and vehicle are not deleted."""
    return (
        stmt.join(Client, Client.id == Visit.client_id)
        .join(Vehicle, Vehicle.id == Visit.vehicle_id)
        .where(Visit.deleted_at.is_(None), Client.deleted_at.is_(None), Vehicle.deleted_at.is_(None))
    )


class StatsRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def _rows(self, stmt) -> list[Row]:
        return list((await self.session.execute(stmt)).all())

    async def closed_visits(self, status: VisitStatus, window: Window, master_id: uuid.UUID | None = None) -> list[Row]:
        """Visits now in `status` (issued/cancelled) that entered it inside `window`.
        A visit without that log entry (old or imported data) counts as closed when created."""
        last = (
            select(VisitStatusLog.visit_id, func.max(VisitStatusLog.changed_at).label("at"))
            .where(VisitStatusLog.to_status == status)
            .group_by(VisitStatusLog.visit_id)
            .subquery()
        )
        closed_at = func.coalesce(last.c.at, Visit.created_at)
        stmt = _alive(
            select(
                Visit.id, Visit.created_at, Visit.total_amount, Visit.client_id,
                Visit.assigned_master_id.label("master_id"), User.full_name.label("master_name"),
                closed_at.label("closed_at"),
            )
            .select_from(Visit)
            .outerjoin(last, last.c.visit_id == Visit.id)
            .join(User, User.id == Visit.assigned_master_id)
        ).where(Visit.status == status, closed_at >= window.start, closed_at < window.end)
        if master_id is not None:
            stmt = stmt.where(Visit.assigned_master_id == master_id)
        return await self._rows(stmt.order_by(closed_at, Visit.id))

    async def created_visits(self, window: Window, master_id: uuid.UUID | None = None) -> list[Row]:
        stmt = _alive(select(Visit.id, Visit.created_at, Visit.client_id, Vehicle.make).select_from(Visit)).where(
            Visit.created_at >= window.start, Visit.created_at < window.end
        )
        if master_id is not None:
            stmt = stmt.where(Visit.assigned_master_id == master_id)
        return await self._rows(stmt.order_by(Visit.created_at, Visit.id))

    async def open_count(self, master_id: uuid.UUID | None = None) -> int:
        stmt = _alive(select(func.count(Visit.id)).select_from(Visit)).where(Visit.status.not_in(CLOSED_STATUSES))
        if master_id is not None:
            stmt = stmt.where(Visit.assigned_master_id == master_id)
        return (await self.session.execute(stmt)).scalar_one()

    async def work_lines(self, visit_ids: list[uuid.UUID]) -> list[Row]:
        if not visit_ids:
            return []
        mechanic = aliased(User)
        stmt = (
            select(
                VisitWorkItem.visit_id,
                func.coalesce(WorkCatalog.name, VisitWorkItem.free_text_name).label("name"),
                VisitWorkItem.category, VisitWorkItem.norm_hours, VisitWorkItem.hourly_rate, VisitWorkItem.status,
                VisitWorkItem.assigned_mechanic_id.label("mechanic_id"),
                mechanic.full_name.label("mechanic_name"), mechanic.role.label("mechanic_role"),
                VisitWorkItem.is_extra_work, VisitWorkItem.approved_by_client,
            )
            .outerjoin(WorkCatalog, WorkCatalog.id == VisitWorkItem.catalog_item_id)
            .outerjoin(mechanic, mechanic.id == VisitWorkItem.assigned_mechanic_id)
            .where(VisitWorkItem.visit_id.in_(visit_ids))
            .order_by(VisitWorkItem.created_at, VisitWorkItem.id)
        )
        return await self._rows(stmt)

    async def part_sums(self, visit_ids: list[uuid.UUID]) -> dict[uuid.UUID, float]:
        if not visit_ids:
            return {}
        stmt = (
            select(VisitPartItem.visit_id, func.sum(VisitPartItem.quantity * VisitPartItem.unit_price))
            .where(VisitPartItem.visit_id.in_(visit_ids))
            .group_by(VisitPartItem.visit_id)
        )
        return {visit_id: float(total) for visit_id, total in await self._rows(stmt)}

    async def status_logs(self, visit_ids: list[uuid.UUID]) -> list[Row]:
        if not visit_ids:
            return []
        stmt = (
            select(VisitStatusLog.visit_id, VisitStatusLog.to_status, VisitStatusLog.changed_at)
            .where(VisitStatusLog.visit_id.in_(visit_ids))
            .order_by(VisitStatusLog.changed_at)
        )
        return await self._rows(stmt)

    async def first_visit_at(self, client_ids: list[uuid.UUID]) -> dict[uuid.UUID, datetime]:
        if not client_ids:
            return {}
        stmt = (
            _alive(select(Visit.client_id, func.min(Visit.created_at)).select_from(Visit))
            .where(Visit.client_id.in_(client_ids))
            .group_by(Visit.client_id)
        )
        return dict(await self._rows(stmt))

    async def open_work_count(self, mechanic_id: uuid.UUID) -> int:
        """Not-yet-ready works assigned to `mechanic_id` in open visits."""
        stmt = _alive(
            select(func.count(VisitWorkItem.id)).select_from(VisitWorkItem).join(Visit, Visit.id == VisitWorkItem.visit_id)
        ).where(
            VisitWorkItem.assigned_mechanic_id == mechanic_id,
            VisitWorkItem.status != WorkItemStatus.READY,
            Visit.status.not_in(CLOSED_STATUSES),
        )
        return (await self.session.execute(stmt)).scalar_one()
