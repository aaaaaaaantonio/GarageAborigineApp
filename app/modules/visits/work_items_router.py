from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.enums import UserRole
from app.core.exceptions import NotAssignedMechanic
from app.modules.users.auth import require_role
from app.modules.users.models import User
from app.modules.visits.work_items_schemas import WorkItemCreate, WorkItemOut, WorkItemStatusChange
from app.modules.visits.work_items_service import WorkItemService

router = APIRouter(prefix="/visits/{visit_id}/work-items", tags=["visit-work-items"])


@router.post("", response_model=WorkItemOut, status_code=201)
async def add_work_item(
    visit_id,
    data: WorkItemCreate,
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MASTER)),
):
    service = WorkItemService(session)
    item = await service.add_item(visit_id, data, acting_user)
    await session.commit()
    return item


@router.patch("/{item_id}/status", response_model=WorkItemOut)
async def change_work_item_status(
    visit_id,
    item_id,
    data: WorkItemStatusChange,
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MASTER, UserRole.MECHANIC)),
):
    service = WorkItemService(session)
    try:
        item = await service.update_status(item_id, data.new_status, acting_user)
    except NotAssignedMechanic:
        raise HTTPException(403, "Можно менять статус только своих назначенных работ")
    await session.commit()
    return item


@router.post("/{item_id}/approve", response_model=WorkItemOut)
async def approve_work_item(
    visit_id,
    item_id,
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MASTER)),
):
    service = WorkItemService(session)
    item = await service.approve(item_id, acting_user)
    await session.commit()
    return item
