import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ApprovedVia, UserRole, VisitStatus, WorkItemStatus
from app.core.exceptions import InvalidAssignedMechanic, NotAssignedMechanic, VisitNotFound, WorkItemNotFound
from app.modules.catalog.models import WorkCatalog
from app.modules.catalog.repository import CatalogRepository
from app.modules.users.audit import record_audit
from app.modules.users.models import User
from app.modules.vehicles.models import Vehicle
from app.modules.visits.models import Visit, VisitWorkItem
from app.modules.visits.work_items_schemas import (
    VehicleWorkHistoryItemOut,
    VehicleWorkHistoryOut,
    WorkItemCreate,
)

WORK_HISTORY_LIMIT = 30


class WorkItemService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def _with_names(self, items: list[VisitWorkItem]) -> list[VisitWorkItem]:
        """Attach display names to each item: `name` (catalog name, else
        free-text name) and `assigned_mechanic_name`."""
        catalog_names = await CatalogRepository(self.session).names_by_ids(
            {i.catalog_item_id for i in items if i.catalog_item_id is not None}
        )
        mechanic_ids = {i.assigned_mechanic_id for i in items if i.assigned_mechanic_id is not None}
        mechanic_names = (
            dict((await self.session.execute(select(User.id, User.full_name).where(User.id.in_(mechanic_ids)))).all())
            if mechanic_ids
            else {}
        )
        for item in items:
            item.name = catalog_names.get(item.catalog_item_id) or item.free_text_name
            item.assigned_mechanic_name = mechanic_names.get(item.assigned_mechanic_id)
        return items

    async def _check_mechanic(self, mechanic_id: uuid.UUID) -> None:
        mechanic = await self.session.get(User, mechanic_id)
        if mechanic is None or mechanic.deleted_at is not None or mechanic.role != UserRole.MECHANIC:
            raise InvalidAssignedMechanic()

    async def add_item(self, visit_id: uuid.UUID, data: WorkItemCreate, acting_user: User) -> VisitWorkItem:
        visit = await self.session.get(Visit, visit_id)
        if visit is None:
            raise VisitNotFound()
        if data.assigned_mechanic_id is not None:
            await self._check_mechanic(data.assigned_mechanic_id)

        item = VisitWorkItem(
            visit_id=visit_id,
            catalog_item_id=data.catalog_item_id,
            free_text_name=data.free_text_name,
            category=data.category,
            norm_hours=data.norm_hours,
            hourly_rate=data.hourly_rate,
            assigned_mechanic_id=data.assigned_mechanic_id,
            is_extra_work=data.is_extra_work,
            comment=data.comment,
            status=WorkItemStatus.NOT_READY,
        )
        self.session.add(item)
        await self.session.flush()

        from app.modules.visits.service import VisitService

        await VisitService(self.session).recalculate_total(visit_id)

        from app.modules.notifications.factory import get_notification_sender

        notifier = get_notification_sender(self.session)
        if item.is_extra_work:
            await notifier.send_extra_work_approval_request(item)
        if item.assigned_mechanic_id is not None:
            await notifier.send_work_assigned(item, item.assigned_mechanic_id)

        await record_audit(
            self.session,
            user=acting_user,
            entity_type="visit_work_item",
            entity_id=item.id,
            action="create",
            new_value={"visit_id": str(visit_id)},
        )
        return (await self._with_names([item]))[0]

    async def update_status(
        self, item_id: uuid.UUID, new_status: WorkItemStatus, acting_user: User
    ) -> VisitWorkItem:
        item = await self.session.get(VisitWorkItem, item_id)
        if item is None:
            raise WorkItemNotFound()
        if acting_user.role == UserRole.MECHANIC and item.assigned_mechanic_id != acting_user.id:
            raise NotAssignedMechanic()
        old_status = item.status
        item.status = new_status
        await self.session.flush()
        await record_audit(
            self.session,
            user=acting_user,
            entity_type="visit_work_item",
            entity_id=item.id,
            action="status_change",
            old_value={"status": old_status.value},
            new_value={"status": new_status.value},
        )
        return (await self._with_names([item]))[0]

    async def assign_mechanic(
        self, visit_id: uuid.UUID, item_id: uuid.UUID, mechanic_id: uuid.UUID | None, acting_user: User
    ) -> VisitWorkItem:
        """Reassign (or unassign, with None) the item's mechanic; notifies both
        the new and the previous mechanic. Assigning the current one is a no-op."""
        item = await self.session.get(VisitWorkItem, item_id)
        if item is None or item.visit_id != visit_id:
            raise WorkItemNotFound()
        old_mechanic_id = item.assigned_mechanic_id
        if mechanic_id == old_mechanic_id:
            return (await self._with_names([item]))[0]
        if mechanic_id is not None:
            await self._check_mechanic(mechanic_id)

        item.assigned_mechanic_id = mechanic_id
        await self.session.flush()

        from app.modules.notifications.factory import get_notification_sender

        notifier = get_notification_sender(self.session)
        if mechanic_id is not None:
            await notifier.send_work_assigned(item, mechanic_id)
        if old_mechanic_id is not None:
            await notifier.send_work_unassigned(item, old_mechanic_id)

        await record_audit(
            self.session,
            user=acting_user,
            entity_type="visit_work_item",
            entity_id=item.id,
            action="assign_mechanic",
            old_value={"assigned_mechanic_id": str(old_mechanic_id) if old_mechanic_id else None},
            new_value={"assigned_mechanic_id": str(mechanic_id) if mechanic_id else None},
        )
        return (await self._with_names([item]))[0]

    async def approve(self, item_id: uuid.UUID, acting_user: User) -> VisitWorkItem:
        item = await self.session.get(VisitWorkItem, item_id)
        if item is None:
            raise WorkItemNotFound()
        item.approved_by_client = True
        item.approved_at = datetime.now(timezone.utc)
        item.approved_via = ApprovedVia.CRM_STATUS
        await self.session.flush()
        await record_audit(
            self.session,
            user=acting_user,
            entity_type="visit_work_item",
            entity_id=item.id,
            action="approve",
            new_value={"approved_via": item.approved_via.value},
        )
        return (await self._with_names([item]))[0]

    async def list_mine(self, acting_user: User) -> list[VisitWorkItem]:
        result = await self.session.execute(
            select(VisitWorkItem)
            .where(VisitWorkItem.assigned_mechanic_id == acting_user.id)
            .order_by(VisitWorkItem.created_at, VisitWorkItem.id)
        )
        items = await self._with_names(list(result.scalars()))
        # The mechanic can't read GET /visits/{id}; the bot labels work items by car.
        visit_ids = {i.visit_id for i in items}
        vehicles = {}
        if visit_ids:
            rows = await self.session.execute(
                select(Visit.id, Vehicle.plate_number, Vehicle.make, Vehicle.model)
                .join(Vehicle, Vehicle.id == Visit.vehicle_id)
                .where(Visit.id.in_(visit_ids))
            )
            vehicles = {visit_id: (plate, f"{make} {model}") for visit_id, plate, make, model in rows.all()}
        for item in items:
            item.plate_number, item.make_model = vehicles.get(item.visit_id, (None, None))
        return items

    async def list_for_visit(self, visit_id: uuid.UUID) -> list[VisitWorkItem]:
        visit = await self.session.get(Visit, visit_id)
        if visit is None:
            raise VisitNotFound()
        result = await self.session.execute(
            select(VisitWorkItem)
            .where(VisitWorkItem.visit_id == visit_id)
            .order_by(VisitWorkItem.created_at, VisitWorkItem.id)
        )
        return await self._with_names(list(result.scalars()))

    async def list_vehicle_history(self, vehicle_id: uuid.UUID) -> VehicleWorkHistoryOut:
        stmt = (
            select(
                Visit.id.label("visit_id"),
                Visit.created_at.label("visit_at"),
                Visit.mileage_at_intake.label("mileage"),
                func.coalesce(WorkCatalog.name, VisitWorkItem.free_text_name).label("name"),
                VisitWorkItem.status,
            )
            .join(Visit, Visit.id == VisitWorkItem.visit_id)
            .outerjoin(WorkCatalog, WorkCatalog.id == VisitWorkItem.catalog_item_id)
            .where(
                Visit.vehicle_id == vehicle_id,
                Visit.deleted_at.is_(None),
                Visit.status != VisitStatus.CANCELLED,
            )
            .order_by(Visit.created_at.desc(), Visit.id, VisitWorkItem.created_at, VisitWorkItem.id)
            .limit(WORK_HISTORY_LIMIT + 1)
        )
        rows = (await self.session.execute(stmt)).all()
        return VehicleWorkHistoryOut(
            items=[
                VehicleWorkHistoryItemOut(
                    visit_id=r.visit_id, visit_at=r.visit_at, mileage=r.mileage, name=r.name or "—", status=r.status
                )
                for r in rows[:WORK_HISTORY_LIMIT]
            ],
            has_more=len(rows) > WORK_HISTORY_LIMIT,
        )
