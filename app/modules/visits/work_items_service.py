import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ApprovedVia, UserRole, WorkItemStatus
from app.core.exceptions import InvalidAssignedMechanic, NotAssignedMechanic, VisitNotFound, WorkItemNotFound
from app.modules.catalog.repository import CatalogRepository
from app.modules.users.audit import record_audit
from app.modules.users.models import User
from app.modules.visits.models import Visit, VisitWorkItem
from app.modules.visits.work_items_schemas import WorkItemCreate


class WorkItemService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def _with_names(self, items: list[VisitWorkItem]) -> list[VisitWorkItem]:
        """Attach a display `name` to each item: catalog name, else free-text name."""
        catalog_names = await CatalogRepository(self.session).names_by_ids(
            {i.catalog_item_id for i in items if i.catalog_item_id is not None}
        )
        for item in items:
            item.name = catalog_names.get(item.catalog_item_id) or item.free_text_name
        return items

    async def add_item(self, visit_id: uuid.UUID, data: WorkItemCreate, acting_user: User) -> VisitWorkItem:
        visit = await self.session.get(Visit, visit_id)
        if visit is None:
            raise VisitNotFound()
        if data.assigned_mechanic_id is not None:
            mechanic = await self.session.get(User, data.assigned_mechanic_id)
            if mechanic is None or mechanic.deleted_at is not None or mechanic.role != UserRole.MECHANIC:
                raise InvalidAssignedMechanic()

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

        if item.is_extra_work:
            from app.modules.notifications.factory import get_notification_sender

            await get_notification_sender(self.session).send_extra_work_approval_request(item)

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
        return await self._with_names(list(result.scalars()))

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
