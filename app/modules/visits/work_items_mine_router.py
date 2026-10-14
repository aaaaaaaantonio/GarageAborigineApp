from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.enums import UserRole, VisitStatus, WorkItemStatus
from app.modules.users.auth import require_role
from app.modules.users.models import User
from app.modules.visits.work_items_schemas import WorkItemDoneListOut, WorkItemMineOut
from app.modules.visits.work_items_service import MineSort, WorkItemService

router = APIRouter(prefix="/work-items", tags=["work-items-mine"])


@router.get("/mine", response_model=list[WorkItemMineOut])
async def list_my_work_items(
    status: list[WorkItemStatus] = Query(default=[]),
    sort: MineSort = "urgency",
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_role(UserRole.MECHANIC, UserRole.ADMIN)),
):
    return await WorkItemService(session).list_mine(acting_user, statuses=status, sort=sort)


@router.get("/mine/done", response_model=WorkItemDoneListOut)
async def list_my_done_work_items(
    since: datetime | None = None,
    outcome: Literal["issued", "cancelled"] | None = None,
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_role(UserRole.MECHANIC, UserRole.ADMIN)),
):
    return await WorkItemService(session).list_done(
        acting_user, since=since, outcome=VisitStatus(outcome) if outcome else None
    )
