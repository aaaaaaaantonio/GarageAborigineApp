# app/modules/stats/router.py
import uuid
from typing import Literal

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.enums import UserRole
from app.modules.stats.periods import Period
from app.modules.stats.schemas import StatsOut
from app.modules.stats.service import StatsService
from app.modules.users.auth import require_role
from app.modules.users.models import User

router = APIRouter(prefix="/stats", tags=["stats"])

Section = Literal["money", "flow", "staff", "works"]


@router.get("/mine", response_model=StatsOut)
async def my_stats(
    period: Period = "month",
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_role(UserRole.MASTER, UserRole.MECHANIC)),
):
    return await StatsService(session).mine(acting_user, period)


@router.get("/{section}", response_model=StatsOut)
async def section_stats(
    section: Section,
    period: Period = "month",
    master_id: uuid.UUID | None = None,
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_role(UserRole.ADMIN)),
):
    service = StatsService(session)
    return await getattr(service, section)(period, master_id)
