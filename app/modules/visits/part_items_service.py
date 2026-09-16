import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.users.audit import record_audit
from app.modules.users.models import User
from app.modules.visits.models import VisitPartItem
from app.modules.visits.part_items_schemas import PartItemCreate
from app.modules.visits.service import VisitService


class PartItemService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.visit_service = VisitService(session)

    async def add_item(self, visit_id: uuid.UUID, data: PartItemCreate, acting_user: User) -> VisitPartItem:
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
