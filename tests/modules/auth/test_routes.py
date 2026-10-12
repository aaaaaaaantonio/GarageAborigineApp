import uuid
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.core.db import get_session
from app.core.enums import UserRole
from app.main import app
from app.modules.auth.tokens import read_session_token
from app.modules.users.models import User
from tests.modules.auth.test_telegram import BOT_TOKEN, make_init_data


@pytest.fixture
def api_app(session, monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", BOT_TOKEN)

    async def override_get_session():
        yield session

    app.dependency_overrides[get_session] = override_get_session
    yield app
    app.dependency_overrides.clear()


@pytest.fixture
async def staff(session):
    master = User(role=UserRole.MASTER, full_name="Мастер Орлов", branch_id=uuid.uuid4(), telegram_id=555)
    fired = User(role=UserRole.MECHANIC, full_name="Уволенный", branch_id=uuid.uuid4(), telegram_id=666,
                 deleted_at=datetime.now(timezone.utc))
    session.add_all([master, fired])
    await session.flush()
    return master, fired


async def _call(api_app, method, path, **kwargs):
    async with AsyncClient(transport=ASGITransport(app=api_app), base_url="http://test") as client:
        return await client.request(method, path, **kwargs)


async def test_telegram_login_issues_token(api_app, staff):
    master, _ = staff
    resp = await _call(api_app, "POST", "/auth/telegram", json={"init_data": make_init_data(user_id=555)})
    assert resp.status_code == 200
    body = resp.json()
    assert body["user"]["full_name"] == "Мастер Орлов"
    assert read_session_token(body["token"]) == master.id


async def test_telegram_login_bad_signature_401(api_app, staff):
    resp = await _call(api_app, "POST", "/auth/telegram", json={"init_data": make_init_data(bot_token="1:X", user_id=555)})
    assert resp.status_code == 401


async def test_telegram_login_not_staff_403(api_app, staff):
    resp = await _call(api_app, "POST", "/auth/telegram", json={"init_data": make_init_data(user_id=999)})
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Вы не сотрудник сервиса"


async def test_telegram_login_deleted_staff_403(api_app, staff):
    resp = await _call(api_app, "POST", "/auth/telegram", json={"init_data": make_init_data(user_id=666)})
    assert resp.status_code == 403


async def test_telegram_login_unconfigured_503(api_app, staff, monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", None)
    resp = await _call(api_app, "POST", "/auth/telegram", json={"init_data": make_init_data(user_id=555)})
    assert resp.status_code == 503


async def test_dev_endpoints_404_when_disabled(api_app, staff):
    assert (await _call(api_app, "GET", "/auth/dev-users")).status_code == 404
    master, _ = staff
    assert (await _call(api_app, "POST", "/auth/dev-login", json={"user_id": str(master.id)})).status_code == 404


async def test_dev_users_lists_active_staff(api_app, staff, monkeypatch):
    monkeypatch.setattr(settings, "dev_login", True)
    resp = await _call(api_app, "GET", "/auth/dev-users")
    assert resp.status_code == 200
    names = [u["full_name"] for u in resp.json()]
    assert "Мастер Орлов" in names and "Уволенный" not in names


async def test_dev_login_issues_token(api_app, staff, monkeypatch):
    monkeypatch.setattr(settings, "dev_login", True)
    master, fired = staff
    resp = await _call(api_app, "POST", "/auth/dev-login", json={"user_id": str(master.id)})
    assert resp.status_code == 200
    assert read_session_token(resp.json()["token"]) == master.id
    assert (await _call(api_app, "POST", "/auth/dev-login", json={"user_id": str(fired.id)})).status_code == 404


async def test_me_returns_current_user(api_app, staff, monkeypatch):
    monkeypatch.setattr(settings, "dev_login", True)
    master, _ = staff
    token = (await _call(api_app, "POST", "/auth/dev-login", json={"user_id": str(master.id)})).json()["token"]
    resp = await _call(api_app, "GET", "/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["role"] == "master"


async def test_me_without_token_401(api_app):
    assert (await _call(api_app, "GET", "/auth/me")).status_code == 401
