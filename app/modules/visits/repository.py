import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.visits.models import Visit


class VisitRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, visit: Visit) -> Visit:
        self.session.add(visit)
        await self.session.flush()
        return visit

    async def get(self, visit_id: uuid.UUID) -> Visit | None:
        return await self.session.get(Visit, visit_id)
