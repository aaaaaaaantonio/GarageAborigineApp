import hmac
import uuid
from collections.abc import Callable

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import get_session
from app.core.enums import UserRole
from app.modules.auth.tokens import InvalidSessionToken, read_session_token
from app.modules.users.models import User


def _check_service_key(x_service_key: str | None) -> None:
    """With INTERNAL_API_KEY set, only the bot (holding the key) may act via X-User-Id."""
    expected = settings.internal_api_key
    if expected and not (x_service_key and hmac.compare_digest(x_service_key, expected)):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid service key")


async def require_service_key(x_service_key: str | None = Header(None, alias="X-Service-Key")) -> None:
    _check_service_key(x_service_key)


async def get_current_user(
    authorization: str | None = Header(None),
    x_user_id: uuid.UUID | None = Header(None, alias="X-User-Id"),
    x_service_key: str | None = Header(None, alias="X-Service-Key"),
    session: AsyncSession = Depends(get_session),
) -> User:
    if authorization and authorization.lower().startswith("bearer "):
        try:
            user_id = read_session_token(authorization[7:].strip())
        except InvalidSessionToken:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid session token")
    elif x_user_id is not None:
        _check_service_key(x_service_key)
        user_id = x_user_id
    else:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    user = await session.get(User, user_id)
    if user is None or user.deleted_at is not None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown user")
    return user


def require_role(*roles: UserRole) -> Callable:
    async def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Role not permitted")
        return user

    return dependency
