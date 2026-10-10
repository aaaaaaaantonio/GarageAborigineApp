"""Session tokens for the web / Mini App channel (JWT HS256)."""
import uuid
from datetime import datetime, timedelta, timezone

import jwt

from app.core.config import settings


class SessionNotConfigured(Exception):
    """SESSION_SECRET is not set: tokens cannot be issued."""


class InvalidSessionToken(Exception):
    """Bad signature, expired, malformed or missing subject."""


def issue_session_token(user_id: uuid.UUID, now: datetime | None = None) -> str:
    if not settings.session_secret:
        raise SessionNotConfigured
    now = now or datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=settings.session_ttl_hours)).timestamp()),
    }
    return jwt.encode(payload, settings.session_secret, algorithm="HS256")


def read_session_token(token: str) -> uuid.UUID:
    if not settings.session_secret:
        raise InvalidSessionToken
    try:
        payload = jwt.decode(
            token, settings.session_secret, algorithms=["HS256"], options={"require": ["exp", "sub"]}
        )
        if "purpose" in payload:
            raise InvalidSessionToken
        return uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, ValueError, KeyError) as e:
        raise InvalidSessionToken from e


DOWNLOAD_TTL_S = 300


def issue_download_token(document_id: uuid.UUID, now: datetime | None = None) -> str:
    """Signed link token for one document; used where no Authorization header can be sent
    (Telegram WebApp.downloadFile / openLink)."""
    if not settings.session_secret:
        raise SessionNotConfigured
    now = now or datetime.now(timezone.utc)
    payload = {
        "doc": str(document_id),
        "purpose": "download",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=DOWNLOAD_TTL_S)).timestamp()),
    }
    return jwt.encode(payload, settings.session_secret, algorithm="HS256")


def read_download_token(token: str) -> uuid.UUID:
    if not settings.session_secret:
        raise InvalidSessionToken
    try:
        payload = jwt.decode(
            token, settings.session_secret, algorithms=["HS256"], options={"require": ["exp", "doc", "purpose"]}
        )
        if payload["purpose"] != "download":
            raise InvalidSessionToken
        return uuid.UUID(payload["doc"])
    except (jwt.PyJWTError, ValueError, KeyError) as e:
        raise InvalidSessionToken from e
