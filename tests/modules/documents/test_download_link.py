import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.core.db import get_session
from app.core.enums import UserRole
from app.core.exceptions import DocumentNotFound, VisitNotFound
from app.main import app
from app.modules.auth.tokens import (
    InvalidSessionToken,
    issue_download_token,
    issue_session_token,
    read_download_token,
    read_session_token,
)
from app.modules.documents.service import DocumentService
from app.modules.users.models import User

PDF = b"%PDF-1.7 test"


@pytest.fixture
def api_app(session, monkeypatch):
    async def fake_generate(self, visit_id):
        if str(visit_id).startswith("00000000"):
            raise VisitNotFound()
        return f"visits/{visit_id}.pdf"

    async def fake_read(self, visit_id):
        if str(visit_id).startswith("ffffffff"):
            raise DocumentNotFound()
        return PDF

    monkeypatch.setattr(DocumentService, "generate_visit_document", fake_generate)
    monkeypatch.setattr(DocumentService, "get_visit_document", fake_read)

    async def override_get_session():
        yield session

    app.dependency_overrides[get_session] = override_get_session
    yield app
    app.dependency_overrides.clear()


async def _call(api_app, method, path, headers=None):
    async with AsyncClient(transport=ASGITransport(app=api_app), base_url="http://test") as client:
        return await client.request(method, path, headers=headers or {})


@pytest.fixture
async def users(session):
    master = User(role=UserRole.MASTER, full_name="Мастер", branch_id=uuid.uuid4())
    mechanic = User(role=UserRole.MECHANIC, full_name="Механик", branch_id=uuid.uuid4())
    session.add_all([master, mechanic])
    await session.flush()
    return master, mechanic


def test_download_token_round_trip_and_expiry():
    doc = uuid.uuid4()
    assert read_download_token(issue_download_token(doc)) == doc
    old = issue_download_token(doc, now=datetime.now(timezone.utc) - timedelta(seconds=301))
    with pytest.raises(InvalidSessionToken):
        read_download_token(old)


def test_tokens_are_not_interchangeable():
    doc = uuid.uuid4()
    with pytest.raises(InvalidSessionToken):
        read_session_token(issue_download_token(doc))
    with pytest.raises(InvalidSessionToken):
        read_download_token(issue_session_token(doc))


async def test_link_then_download_without_auth_header(api_app, users):
    master, _ = users
    visit_id = uuid.uuid4()
    resp = await _call(api_app, "POST", f"/visits/{visit_id}/document/link", {"X-User-Id": str(master.id)})
    assert resp.status_code == 200
    body = resp.json()
    assert body["expires_in"] == 300
    url = urlparse(body["url"])
    assert url.path == f"/documents/{visit_id}/download"
    assert parse_qs(url.query)["token"]
    file_resp = await _call(api_app, "GET", body["url"])
    assert file_resp.status_code == 200
    assert file_resp.content == PDF
    assert file_resp.headers["content-type"] == "application/pdf"
    assert file_resp.headers["content-disposition"].startswith("attachment;")


async def test_link_forbidden_for_mechanic(api_app, users):
    _, mechanic = users
    resp = await _call(api_app, "POST", f"/visits/{uuid.uuid4()}/document/link", {"X-User-Id": str(mechanic.id)})
    assert resp.status_code == 403


async def test_link_unknown_visit_404(api_app, users):
    master, _ = users
    resp = await _call(api_app, "POST", f"/visits/{uuid.UUID(int=1)}/document/link", {"X-User-Id": str(master.id)})
    assert resp.status_code == 404


async def test_link_without_secret_503(api_app, users, monkeypatch):
    master, _ = users
    monkeypatch.setattr(settings, "session_secret", None)
    resp = await _call(api_app, "POST", f"/visits/{uuid.uuid4()}/document/link", {"X-User-Id": str(master.id)})
    assert resp.status_code == 503


async def test_download_rejects_bad_tokens(api_app):
    doc = uuid.uuid4()
    other = issue_download_token(uuid.uuid4())
    expired = issue_download_token(doc, now=datetime.now(timezone.utc) - timedelta(seconds=301))
    session_token = issue_session_token(doc)
    for token in (other, expired, session_token, "garbage"):
        resp = await _call(api_app, "GET", f"/documents/{doc}/download?token={token}")
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Ссылка устарела, нажмите PDF ещё раз"


async def test_download_missing_file_404(api_app):
    doc = uuid.UUID("ffffffff-0000-0000-0000-000000000000")
    resp = await _call(api_app, "GET", f"/documents/{doc}/download?token={issue_download_token(doc)}")
    assert resp.status_code == 404
