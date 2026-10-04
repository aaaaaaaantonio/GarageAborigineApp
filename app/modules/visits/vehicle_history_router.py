import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.enums import UserRole
from app.modules.users.auth import require_role
from app.modules.users.models import User
from app.modules.vehicles.service import VehicleService
from app.modules.visits.work_items_schemas import VehicleWorkHistoryOut
from app.modules.visits.work_items_service import WorkItemService

router = APIRouter(prefix="/vehicles/{vehicle_id}/work-history", tags=["vehicle-work-history"])


@router.get("", response_model=VehicleWorkHistoryOut)
async def get_vehicle_work_history(
    vehicle_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MASTER, UserRole.MECHANIC)),
):
    if await VehicleService(session).get(vehicle_id) is None:
        raise HTTPException(404, "Vehicle not found")
    return await WorkItemService(session).list_vehicle_history(vehicle_id)
