from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.enums import UserRole
from app.modules.search.service import SearchService
from app.modules.users.auth import require_role
from app.modules.users.models import User

router = APIRouter(prefix="/search", tags=["search"])


@router.get("")
async def search(
    q: str = Query(..., min_length=1),
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MASTER, UserRole.MECHANIC)),
):
    service = SearchService(session)
    return await service.search(q)


@router.get("/recent")
async def recent(
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MASTER, UserRole.MECHANIC)),
):
    service = SearchService(session)
    views = await service.recent(acting_user.id)
    return [{"entity_type": v.entity_type, "entity_id": str(v.entity_id)} for v in views]
