import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.core.db import get_session
from app.core.enums import UserRole
from app.main import app
from app.modules.auth.tokens import issue_session_token
from app.modules.users.models import User


@pytest.fixture
def api_app(session):
    async def override_get_session():
        yield session

    app.dependency_overrides[get_session] = override_get_session
    yield app
    app.dependency_overrides.clear()


@pytest.fixture
async def master(session):
    user = User(role=UserRole.MASTER, full_name="Мастер", branch_id=uuid.uuid4(), telegram_id=777)
    session.add(user)
    await session.flush()
    return user


async def _get(api_app, path, headers):
    async with AsyncClient(transport=ASGITransport(app=api_app), base_url="http://test") as client:
        return await client.get(path, headers=headers)


async def test_bearer_token_authenticates(api_app, master):
    resp = await _get(api_app, "/users/mechanics", {"Authorization": f"Bearer {issue_session_token(master.id)}"})
    assert resp.status_code == 200


async def test_bad_bearer_token_is_401(api_app, master):
    resp = await _get(api_app, "/users/mechanics", {"Authorization": "Bearer nope"})
    assert resp.status_code == 401


async def test_bearer_for_unknown_user_is_401(api_app):
    resp = await _get(api_app, "/users/mechanics", {"Authorization": f"Bearer {issue_session_token(uuid.uuid4())}"})
    assert resp.status_code == 401


async def test_no_credentials_is_401(api_app):
    resp = await _get(api_app, "/users/mechanics", {})
    assert resp.status_code == 401


async def test_x_user_id_without_configured_key_still_works(api_app, master):
    resp = await _get(api_app, "/users/mechanics", {"X-User-Id": str(master.id)})
    assert resp.status_code == 200


async def test_x_user_id_requires_service_key_when_configured(api_app, master, monkeypatch):
    monkeypatch.setattr(settings, "internal_api_key", "bot-key")
    assert (await _get(api_app, "/users/mechanics", {"X-User-Id": str(master.id)})).status_code == 401
    wrong = {"X-User-Id": str(master.id), "X-Service-Key": "nope"}
    assert (await _get(api_app, "/users/mechanics", wrong)).status_code == 401
    right = {"X-User-Id": str(master.id), "X-Service-Key": "bot-key"}
    assert (await _get(api_app, "/users/mechanics", right)).status_code == 200


async def test_by_telegram_requires_service_key_when_configured(api_app, master, monkeypatch):
    monkeypatch.setattr(settings, "internal_api_key", "bot-key")
    assert (await _get(api_app, "/users/by-telegram/777", {})).status_code == 401
    assert (await _get(api_app, "/users/by-telegram/777", {"X-Service-Key": "bot-key"})).status_code == 200


async def test_by_telegram_open_without_configured_key(api_app, master):
    assert (await _get(api_app, "/users/by-telegram/777", {})).status_code == 200
