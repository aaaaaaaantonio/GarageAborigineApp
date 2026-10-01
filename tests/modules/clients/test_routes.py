import uuid

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


@pytest.mark.parametrize("path", ["/clients", "/consent/paper"])
async def test_duplicate_phone_returns_409(api_app, session, path):
    admin = User(role=UserRole.ADMIN, full_name="Админ", branch_id=uuid.uuid4())
    session.add(admin)
    await session.flush()
    headers = {"X-User-Id": str(admin.id)}

    transport = ASGITransport(app=api_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post(path, json={"full_name": "Иван", "phone": "79991234567"}, headers=headers)
        second = await client.post(path, json={"full_name": "Пётр", "phone": "89991234567"}, headers=headers)

    assert first.status_code in (200, 201)
    assert second.status_code == 409
    assert "телефон" in second.json()["detail"].lower()
