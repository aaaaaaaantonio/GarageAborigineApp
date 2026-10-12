import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.core.config import settings
from app.modules.auth.tokens import (
    InvalidSessionToken,
    SessionNotConfigured,
    issue_session_token,
    read_session_token,
)


def test_round_trip_returns_user_id():
    user_id = uuid.uuid4()
    assert read_session_token(issue_session_token(user_id)) == user_id


def test_expired_token_rejected():
    token = issue_session_token(uuid.uuid4(), now=datetime.now(timezone.utc) - timedelta(hours=13))
    with pytest.raises(InvalidSessionToken):
        read_session_token(token)


def test_token_signed_with_other_key_rejected():
    token = jwt.encode({"sub": str(uuid.uuid4()), "exp": 9999999999}, "other-key-0123456789abcdef-0123456789", algorithm="HS256")
    with pytest.raises(InvalidSessionToken):
        read_session_token(token)


def test_garbage_rejected():
    with pytest.raises(InvalidSessionToken):
        read_session_token("not-a-jwt")


def test_non_uuid_subject_rejected():
    token = jwt.encode({"sub": "42", "exp": 9999999999}, settings.session_secret, algorithm="HS256")
    with pytest.raises(InvalidSessionToken):
        read_session_token(token)


def test_issue_without_secret_raises(monkeypatch):
    monkeypatch.setattr(settings, "session_secret", None)
    with pytest.raises(SessionNotConfigured):
        issue_session_token(uuid.uuid4())
