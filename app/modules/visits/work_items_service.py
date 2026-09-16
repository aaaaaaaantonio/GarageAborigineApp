import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ApprovedVia, WorkItemStatus
from app.core.exceptions import NotAssignedMechanic
from app.modules.users.audit import record_audit
from app.modules.users.models import User
from app.modules.visits.models import VisitWorkItem
from app.modules.visits.work_items_schemas import WorkItemCreate


class WorkItemService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add_item(self, visit_id: uuid.UUID, data: WorkItemCreate, acting_user: User) -> VisitWorkItem:
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
        await record_audit(
            self.session,
            user=acting_user,
            entity_type="visit_work_item",
            entity_id=item.id,
            action="create",
            new_value={"visit_id": str(visit_id)},
        )
        return item

    async def update_status(
        self, item_id: uuid.UUID, new_status: WorkItemStatus, acting_user: User
    ) -> VisitWorkItem:
        item = await self.session.get(VisitWorkItem, item_id)
        assert item is not None
        if acting_user.role.value == "mechanic" and item.assigned_mechanic_id != acting_user.id:
            raise NotAssignedMechanic()
        item.status = new_status
        await self.session.flush()
        return item

    async def approve(self, item_id: uuid.UUID, acting_user: User) -> VisitWorkItem:
        item = await self.session.get(VisitWorkItem, item_id)
        assert item is not None
        item.approved_by_client = True
        item.approved_at = datetime.now(timezone.utc)
        item.approved_via = ApprovedVia.CRM_STATUS
        await self.session.flush()
        return item
