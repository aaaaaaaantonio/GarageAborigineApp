import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.enums import UserRole
from app.core.exceptions import (
    CancelReasonRequired,
    InvalidAssignedMaster,
    InvalidTransition,
    MileageRollbackNotConfirmed,
    NotAllWorkItemsReady,
    VehicleNotFound,
    VisitNotFound,
)
from app.modules.users.auth import require_role
from app.modules.users.models import User
from app.modules.visits.schemas import VisitCreate, VisitOut, VisitStatusChange
from app.modules.visits.service import VisitService

router = APIRouter(prefix="/visits", tags=["visits"])


@router.post("", response_model=VisitOut, status_code=201)
async def create_visit(
    data: VisitCreate,
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MASTER)),
):
    service = VisitService(session)
    try:
        visit = await service.create_visit(data, acting_user)
    except MileageRollbackNotConfirmed:
        raise HTTPException(
            409, "Пробег меньше последнего зафиксированного, требуется mileage_manually_confirmed=true"
        )
    except InvalidAssignedMaster:
        raise HTTPException(422, "assigned_master_id должен ссылаться на активного пользователя с ролью MASTER")
    except VehicleNotFound:
        raise HTTPException(404, "Vehicle not found")
    await session.commit()
    return visit


@router.get("/{visit_id}", response_model=VisitOut)
async def get_visit(
    visit_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MASTER)),
):
    service = VisitService(session)
    visit = await service.get(visit_id)
    if visit is None:
        raise HTTPException(404, "Visit not found")
    return visit


@router.patch("/{visit_id}/status", response_model=VisitOut)
async def change_status(
    visit_id: uuid.UUID,
    data: VisitStatusChange,
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MASTER)),
):
    service = VisitService(session)
    try:
        visit = await service.change_status(visit_id, data.new_status, acting_user, data.reason)
    except VisitNotFound:
        raise HTTPException(404, "Visit not found")
    except InvalidTransition:
        raise HTTPException(409, "Переход между статусами не разрешён")
    except CancelReasonRequired:
        raise HTTPException(422, "Причина отмены обязательна")
    except NotAllWorkItemsReady:
        raise HTTPException(409, "Не все работы в статусе 'готово'")
    await session.commit()
    return visit
