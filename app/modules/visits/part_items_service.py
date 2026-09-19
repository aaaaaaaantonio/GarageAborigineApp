import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import VisitNotFound, WorkItemNotFound
from app.modules.users.audit import record_audit
from app.modules.users.models import User
from app.modules.visits.models import Visit, VisitPartItem, VisitWorkItem
from app.modules.visits.part_items_schemas import PartItemCreate
from app.modules.visits.service import VisitService


class PartItemService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.visit_service = VisitService(session)

    async def add_item(self, visit_id: uuid.UUID, data: PartItemCreate, acting_user: User) -> VisitPartItem:
        visit = await self.session.get(Visit, visit_id)
        if visit is None:
            raise VisitNotFound()

        work_item = await self.session.get(VisitWorkItem, data.work_item_id)
        if work_item is None or work_item.visit_id != visit_id:
            raise WorkItemNotFound()

        item = VisitPartItem(visit_id=visit_id, **data.model_dump())
        self.session.add(item)
        await self.session.flush()
        await self.visit_service.recalculate_total(visit_id)
        await record_audit(
            self.session,
            user=acting_user,
            entity_type="visit_part_item",
            entity_id=item.id,
            action="create",
            new_value={"name": item.name},
        )
        return item
