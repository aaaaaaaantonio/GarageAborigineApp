import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.enums import UserRole, WorkCategory, WorkItemStatus
from app.modules.users.auth import require_role
from app.modules.users.models import User
from app.modules.visits.work_items_schemas import WorkItemBoardListOut
from app.modules.visits.work_items_service import BoardGroup, WorkItemService

router = APIRouter(prefix="/work-items", tags=["work-items-board"])


@router.get("/board", response_model=WorkItemBoardListOut)
async def work_board(
    mechanic_id: uuid.UUID | None = None,
    unassigned: bool = False,
    status: list[WorkItemStatus] = Query(default=[]),
    category: list[WorkCategory] = Query(default=[]),
    unapproved: bool = False,
    group: BoardGroup = "mechanic",
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MASTER)),
):
    items, has_more = await WorkItemService(session).list_board(
        mechanic_id=mechanic_id, unassigned=unassigned, statuses=status, categories=category,
        unapproved=unapproved, group=group,
    )
    return WorkItemBoardListOut(items=items, has_more=has_more)
