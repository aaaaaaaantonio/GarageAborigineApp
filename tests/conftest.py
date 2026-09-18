import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.models import Base
import app.modules.users.models  # noqa
import app.modules.users.audit  # noqa
import app.modules.clients.models  # noqa
import app.modules.vehicles.models  # noqa
import app.modules.catalog.models  # noqa
import app.modules.visits.models  # noqa
import app.modules.consent.models  # noqa
import app.modules.search.models  # noqa


@pytest_asyncio.fixture(scope="session")
async def engine():
    eng = create_async_engine(settings.test_database_url)
    async with eng.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine) -> AsyncSession:
    connection = await engine.connect()
    trans = await connection.begin()
    session_factory = async_sessionmaker(
        bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )
    async with session_factory() as s:
        yield s
    await trans.rollback()
    await connection.close()
