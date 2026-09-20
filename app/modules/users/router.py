from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.enums import UserRole
from app.modules.users.auth import require_role
from app.modules.users.models import User
from app.modules.users.schemas import UserCreate, UserOut
from app.modules.users.service import UserService

router = APIRouter(prefix="/users", tags=["users"])


@router.post("", response_model=UserOut, status_code=201)
async def create_user(
    data: UserCreate,
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_role(UserRole.ADMIN)),
):
    service = UserService(session)
    user = await service.create_user(data, acting_user)
    await session.commit()
    return user


@router.get("", response_model=list[UserOut])
async def list_users(
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_role(UserRole.ADMIN)),
):
    service = UserService(session)
    return await service.list_users()


@router.get("/by-telegram/{telegram_id}", response_model=UserOut)
async def get_user_by_telegram(
    telegram_id: int,
    session: AsyncSession = Depends(get_session),
):
    service = UserService(session)
    user = await service.get_by_telegram_id(telegram_id)
    if user is None or user.deleted_at is not None:
        raise HTTPException(404, "User not found")
    return user
