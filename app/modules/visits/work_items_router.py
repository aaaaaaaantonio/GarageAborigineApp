import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.enums import UserRole
from app.core.exceptions import InvalidAssignedMechanic, NotAssignedMechanic, VisitNotFound, WorkItemNotFound
from app.modules.users.auth import require_role
from app.modules.users.models import User
from app.modules.visits.work_items_schemas import WorkItemCreate, WorkItemOut, WorkItemStatusChange
from app.modules.visits.work_items_service import WorkItemService

router = APIRouter(prefix="/visits/{visit_id}/work-items", tags=["visit-work-items"])


@router.post("", response_model=WorkItemOut, status_code=201)
async def add_work_item(
    visit_id: uuid.UUID,
    data: WorkItemCreate,
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MASTER)),
):
    service = WorkItemService(session)
    try:
        item = await service.add_item(visit_id, data, acting_user)
    except VisitNotFound:
        raise HTTPException(404, "Visit not found")
    except InvalidAssignedMechanic:
        raise HTTPException(422, "assigned_mechanic_id должен ссылаться на активного пользователя с ролью MECHANIC")
    await session.commit()
    return item


@router.get("", response_model=list[WorkItemOut])
async def list_work_items(
    visit_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MASTER, UserRole.MECHANIC)),
):
    service = WorkItemService(session)
    try:
        return await service.list_for_visit(visit_id)
    except VisitNotFound:
        raise HTTPException(404, "Visit not found")


@router.patch("/{item_id}/status", response_model=WorkItemOut)
async def change_work_item_status(
    visit_id: uuid.UUID,
    item_id: uuid.UUID,
    data: WorkItemStatusChange,
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MASTER, UserRole.MECHANIC)),
):
    service = WorkItemService(session)
    try:
        item = await service.update_status(item_id, data.new_status, acting_user)
    except WorkItemNotFound:
        raise HTTPException(404, "Work item not found")
    except NotAssignedMechanic:
        raise HTTPException(403, "Можно менять статус только своих назначенных работ")
    await session.commit()
    return item


@router.post("/{item_id}/approve", response_model=WorkItemOut)
async def approve_work_item(
    visit_id: uuid.UUID,
    item_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MASTER)),
):
    service = WorkItemService(session)
    try:
        item = await service.approve(item_id, acting_user)
    except WorkItemNotFound:
        raise HTTPException(404, "Work item not found")
    await session.commit()
    return item
