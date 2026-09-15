import uuid
from collections.abc import Callable

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.enums import UserRole
from app.modules.users.models import User


async def get_current_user(
    x_user_id: uuid.UUID = Header(..., alias="X-User-Id"),
    session: AsyncSession = Depends(get_session),
) -> User:
    user = await session.get(User, x_user_id)
    if user is None or user.deleted_at is not None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown user")
    return user


def require_role(*roles: UserRole) -> Callable:
    async def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Role not permitted")
        return user

    return dependency
