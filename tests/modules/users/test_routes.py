import uuid
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.db import get_session
from app.core.enums import UserRole
from app.main import app
from app.modules.users.models import User


@pytest.fixture
def api_app(session):
    async def override_get_session():
        yield session

    app.dependency_overrides[get_session] = override_get_session
    yield app
    app.dependency_overrides.clear()


def _user(role, name):
    return User(role=role, full_name=name, branch_id=uuid.uuid4())


async def test_list_mechanics_returns_active_mechanics_sorted_by_name(api_app, session):
    master = _user(UserRole.MASTER, "Мастер")
    boris = _user(UserRole.MECHANIC, "Борис")
    anna = _user(UserRole.MECHANIC, "Анна")
    fired = _user(UserRole.MECHANIC, "Уволенный")
    fired.deleted_at = datetime.now(timezone.utc)
    session.add_all([master, boris, anna, fired, _user(UserRole.ADMIN, "Админ")])
    await session.flush()

    transport = ASGITransport(app=api_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/users/mechanics", headers={"X-User-Id": str(master.id)})

    assert resp.status_code == 200
    assert [u["full_name"] for u in resp.json()] == ["Анна", "Борис"]


async def test_list_mechanics_forbidden_for_mechanic(api_app, session):
    mechanic = _user(UserRole.MECHANIC, "Механик")
    session.add(mechanic)
    await session.flush()

    transport = ASGITransport(app=api_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/users/mechanics", headers={"X-User-Id": str(mechanic.id)})

    assert resp.status_code == 403


async def test_get_user_by_telegram_supports_ids_above_int32(api_app, session):
    # Newer Telegram accounts have IDs beyond 2**31 - 1.
    big_id = 8_123_456_789
    user = _user(UserRole.ADMIN, "Админ")
    user.telegram_id = big_id
    session.add(user)
    await session.flush()

    transport = ASGITransport(app=api_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"/users/by-telegram/{big_id}")

    assert resp.status_code == 200
    assert resp.json()["id"] == str(user.id)
