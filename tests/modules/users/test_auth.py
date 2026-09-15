import uuid

import pytest
from fastapi import FastAPI, Depends
from httpx import AsyncClient, ASGITransport

from app.core.db import get_session
from app.core.enums import UserRole
from app.modules.users.auth import require_role
from app.modules.users.models import User


@pytest.fixture
def app_with_protected_route(session):
    app = FastAPI()

    async def override_get_session():
        yield session

    app.dependency_overrides[get_session] = override_get_session

    @app.get("/admin-only")
    async def admin_only(user: User = Depends(require_role(UserRole.ADMIN))):
        return {"ok": True}

    return app


async def test_require_role_blocks_wrong_role(app_with_protected_route, session):
    mechanic = User(role=UserRole.MECHANIC, full_name="Вася", branch_id=uuid.uuid4())
    session.add(mechanic)
    await session.flush()

    transport = ASGITransport(app=app_with_protected_route)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/admin-only", headers={"X-User-Id": str(mechanic.id)})
    assert resp.status_code == 403


async def test_require_role_allows_correct_role(app_with_protected_route, session):
    admin = User(role=UserRole.ADMIN, full_name="Админ", branch_id=uuid.uuid4())
    session.add(admin)
    await session.flush()

    transport = ASGITransport(app=app_with_protected_route)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/admin-only", headers={"X-User-Id": str(admin.id)})
    assert resp.status_code == 200
