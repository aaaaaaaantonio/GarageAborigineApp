import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.enums import UserRole
from app.core.exceptions import ClientPhoneTaken
from app.modules.clients.schemas import ClientCreate, ClientOut
from app.modules.clients.service import ClientService
from app.modules.users.auth import require_role
from app.modules.users.models import User
from app.modules.vehicles.schemas import VehicleOut
from app.modules.vehicles.service import VehicleService

router = APIRouter(prefix="/clients", tags=["clients"])


@router.post("", response_model=ClientOut, status_code=201)
async def create_client(
    data: ClientCreate,
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MASTER)),
):
    service = ClientService(session)
    try:
        client = await service.create_client(data, acting_user)
    except ClientPhoneTaken:
        raise HTTPException(409, "Клиент с таким телефоном уже есть")
    await session.commit()
    return client


@router.get("/{client_id}", response_model=ClientOut)
async def get_client(
    client_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MASTER)),
):
    service = ClientService(session)
    client = await service.get(client_id)
    if client is None:
        raise HTTPException(404, "Client not found")
    return client


@router.get("/{client_id}/vehicles", response_model=list[VehicleOut])
async def list_client_vehicles(
    client_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MASTER)),
):
    if await ClientService(session).get(client_id) is None:
        raise HTTPException(404, "Client not found")
    return await VehicleService(session).list_current_for_client(client_id)
