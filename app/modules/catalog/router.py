from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.enums import UserRole
from app.modules.catalog.schemas import WorkCatalogCreate, WorkCatalogOut
from app.modules.catalog.service import CatalogService
from app.modules.users.auth import require_role
from app.modules.users.models import User

router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.post("", response_model=WorkCatalogOut, status_code=201)
async def create_item(
    data: WorkCatalogCreate,
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MASTER)),
):
    service = CatalogService(session)
    item = await service.create_item(data, acting_user)
    await session.commit()
    return item


@router.get("/suggest", response_model=list[WorkCatalogOut])
async def suggest(
    text: str,
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MASTER)),
):
    service = CatalogService(session)
    return await service.suggest(text)
