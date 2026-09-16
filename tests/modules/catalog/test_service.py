import uuid

from app.core.enums import UserRole, WorkCategory
from app.modules.catalog.schemas import WorkCatalogCreate
from app.modules.catalog.service import CatalogService
from app.modules.users.models import User


async def test_suggest_finds_similar_name_despite_typo(session):
    admin = User(role=UserRole.ADMIN, full_name="Админ", branch_id=uuid.uuid4())
    session.add(admin)
    await session.flush()

    service = CatalogService(session)
    await service.create_item(
        WorkCatalogCreate(name="Замена масла", category=WorkCategory.MAINTENANCE, default_norm_hours=1.0),
        admin,
    )

    suggestions = await service.suggest("замена масло")
    assert len(suggestions) == 1
    assert suggestions[0].name == "Замена масла"


async def test_suggest_returns_empty_for_unrelated_text(session):
    admin = User(role=UserRole.ADMIN, full_name="Админ", branch_id=uuid.uuid4())
    session.add(admin)
    await session.flush()

    service = CatalogService(session)
    await service.create_item(
        WorkCatalogCreate(name="Замена масла", category=WorkCategory.MAINTENANCE, default_norm_hours=1.0),
        admin,
    )

    suggestions = await service.suggest("развал схождение")
    assert suggestions == []
