import uuid

from sqlalchemy import event, text

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


async def test_suggest_query_can_use_trigram_index(session):
    admin = User(role=UserRole.ADMIN, full_name="Админ", branch_id=uuid.uuid4())
    session.add(admin)
    await session.flush()
    await CatalogService(session).create_item(
        WorkCatalogCreate(name="Замена масла", category=WorkCategory.MAINTENANCE, default_norm_hours=1.0),
        admin,
    )

    captured = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        if "FROM work_catalog" in statement:
            captured.append((statement, parameters))

    sync_conn = (await session.connection()).sync_connection
    event.listen(sync_conn, "before_cursor_execute", capture)
    try:
        await CatalogService(session).suggest("замена масло")
    finally:
        event.remove(sync_conn, "before_cursor_execute", capture)

    statement, parameters = captured[-1]
    await session.execute(text("SET LOCAL enable_seqscan = off"))
    conn = await session.connection()
    rows = await conn.exec_driver_sql("EXPLAIN " + statement, parameters)
    plan_text = "\n".join(r[0] for r in rows)
    assert "ix_work_catalog_name_trgm" in plan_text
