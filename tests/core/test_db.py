from sqlalchemy import text


async def test_pg_trgm_extension_available(session):
    result = await session.execute(
        text("SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm'")
    )
    assert result.scalar() == 1
