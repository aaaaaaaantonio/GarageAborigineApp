from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.modules.catalog.models import WorkCatalog
from app.modules.catalog.repository import CatalogRepository
from app.modules.catalog.schemas import WorkCatalogCreate
from app.modules.users.audit import record_audit
from app.modules.users.models import User


class CatalogService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = CatalogRepository(session)

    async def create_item(self, data: WorkCatalogCreate, acting_user: User) -> WorkCatalog:
        item = WorkCatalog(
            name=data.name,
            category=data.category,
            default_norm_hours=data.default_norm_hours,
            created_by_user_id=acting_user.id,
        )
        await self.repo.create(item)
        await record_audit(
            self.session,
            user=acting_user,
            entity_type="work_catalog",
            entity_id=item.id,
            action="create",
            new_value={"name": item.name},
        )
        return item

    async def suggest(self, query: str) -> list[WorkCatalog]:
        return await self.repo.suggest(query, settings.catalog_fuzzy_threshold)
