from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.enums import UserRole
from app.modules.users.auth import require_role
from app.modules.users.models import User
from app.modules.visits.work_items_schemas import WorkItemMineOut
from app.modules.visits.work_items_service import WorkItemService

router = APIRouter(prefix="/work-items", tags=["work-items-mine"])


@router.get("/mine", response_model=list[WorkItemMineOut])
async def list_my_work_items(
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_role(UserRole.MECHANIC)),
):
    service = WorkItemService(session)
    return await service.list_mine(acting_user)
