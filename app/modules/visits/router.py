import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.enums import UserRole
from app.core.exceptions import InvalidAssignedMaster, MileageRollbackNotConfirmed
from app.modules.users.auth import require_role
from app.modules.users.models import User
from app.modules.visits.schemas import VisitCreate, VisitOut
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
