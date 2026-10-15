import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.enums import UserRole, VisitStatus
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
from app.modules.visits.lines_schemas import VisitLinesOut
from app.modules.visits.lines_service import VisitLinesService
from app.modules.visits.mechanic_view_schemas import MechanicVisitOut
from app.modules.visits.mechanic_view_service import MechanicViewService, NotYourVisit
from app.modules.visits.schemas import VisitCreate, VisitListOut, VisitOut, VisitStatusChange
from app.modules.visits.repository import VisitFilters, VisitSort
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
    return await service.get_summary(visit.id)


@router.get("", response_model=VisitListOut)
async def list_visits(
    active: bool = False,
    closed: bool = False,
    status: list[VisitStatus] = Query(default=[]),
    client_id: uuid.UUID | None = None,
    vehicle_id: uuid.UUID | None = None,
    master_id: uuid.UUID | None = None,
    unassigned_work: bool = False,
    stale: bool = False,
    since: datetime | None = None,
    sort: VisitSort = "date",
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MASTER)),
):
    filters = VisitFilters(
        active=active, closed=closed, statuses=status, client_id=client_id, vehicle_id=vehicle_id,
        master_id=master_id, unassigned_work=unassigned_work, stale=stale, since=since, sort=sort,
    )
    return await VisitService(session).list_visits(acting_user, filters, offset)


@router.get("/{visit_id}", response_model=VisitOut)
async def get_visit(
    visit_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MASTER)),
):
    service = VisitService(session)
    visit = await service.get_summary(visit_id)
    if visit is None:
        raise HTTPException(404, "Visit not found")
    return visit


@router.get("/{visit_id}/lines", response_model=VisitLinesOut)
async def get_visit_lines(
    visit_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MASTER)),
):
    try:
        return await VisitLinesService(session).get_lines(visit_id)
    except VisitNotFound:
        raise HTTPException(404, "Visit not found")


@router.get("/{visit_id}/mechanic-view", response_model=MechanicVisitOut)
async def get_mechanic_view(
    visit_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_role(UserRole.MECHANIC)),
):
    try:
        return await MechanicViewService(session).get(visit_id, acting_user)
    except VisitNotFound:
        raise HTTPException(404, "Visit not found")
    except NotYourVisit:
        raise HTTPException(403, "В этом заезде нет ваших работ")


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
    return await service.get_summary(visit.id)
