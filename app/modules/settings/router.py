import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.enums import UserRole
from app.modules.settings.schemas import MechanicPayOut, PayPatch, VisibilityOut, VisibilityPatch
from app.modules.settings.service import NotAMechanic, SettingsService
from app.modules.users.auth import require_role
from app.modules.users.models import User

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=VisibilityOut)
async def get_settings(
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MASTER, UserRole.MECHANIC)),
):
    return await SettingsService(session).visibility()


@router.patch("", response_model=VisibilityOut)
async def update_settings(
    data: VisibilityPatch,
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_role(UserRole.ADMIN)),
):
    out = await SettingsService(session).update_visibility(data, acting_user)
    await session.commit()
    return out


@router.get("/pay", response_model=list[MechanicPayOut])
async def list_mechanic_pay(
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_role(UserRole.ADMIN)),
):
    return await SettingsService(session).mechanic_pay()


@router.patch("/pay/{user_id}", response_model=MechanicPayOut)
async def set_mechanic_pay(
    user_id: uuid.UUID,
    data: PayPatch,
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_role(UserRole.ADMIN)),
):
    try:
        out = await SettingsService(session).set_pay(user_id, data, acting_user)
    except NotAMechanic:
        raise HTTPException(422, "Схему оплаты можно задать только активному механику")
    await session.commit()
    return out
