import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.catalog.models import WorkCatalog


class CatalogRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, item: WorkCatalog) -> WorkCatalog:
        self.session.add(item)
        await self.session.flush()
        return item

    async def suggest(self, query: str, threshold: float, limit: int = 3) -> list[WorkCatalog]:
        result = await self.session.execute(
            select(WorkCatalog)
            .where(
                WorkCatalog.deleted_at.is_(None),
                text("similarity(name, :q) > :threshold"),
            )
            .params(q=query, threshold=threshold)
            .order_by(text("similarity(name, :q) DESC"))
            .params(q=query)
            .limit(limit)
        )
        return list(result.scalars())

    async def names_by_ids(self, ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
        if not ids:
            return {}
        result = await self.session.execute(select(WorkCatalog.id, WorkCatalog.name).where(WorkCatalog.id.in_(ids)))
        return {row.id: row.name for row in result}
