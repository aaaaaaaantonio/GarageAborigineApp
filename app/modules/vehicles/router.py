import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.enums import UserRole
from app.core.exceptions import VehicleNotFound
from app.modules.users.auth import require_role
from app.modules.users.models import User
from app.modules.vehicles.schemas import OwnershipCreate, VehicleCreate, VehicleOut
from app.modules.vehicles.service import VehicleService

router = APIRouter(prefix="/vehicles", tags=["vehicles"])


@router.post("", response_model=VehicleOut, status_code=201)
async def create_vehicle(
    data: VehicleCreate,
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MASTER)),
):
    service = VehicleService(session)
    vehicle = await service.create_vehicle(data, acting_user)
    await session.commit()
    return vehicle


@router.get("/{vehicle_id}", response_model=VehicleOut)
async def get_vehicle(
    vehicle_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MASTER)),
):
    service = VehicleService(session)
    vehicle = await service.get(vehicle_id)
    if vehicle is None:
        raise HTTPException(404, "Vehicle not found")
    return vehicle


@router.post("/{vehicle_id}/owners", status_code=201)
async def attach_owner(
    vehicle_id: uuid.UUID,
    data: OwnershipCreate,
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MASTER)),
):
    service = VehicleService(session)
    try:
        ownership = await service.attach_owner(vehicle_id, data, acting_user)
    except VehicleNotFound:
        raise HTTPException(404, "Vehicle not found")
    await session.commit()
    return {"id": str(ownership.id)}
