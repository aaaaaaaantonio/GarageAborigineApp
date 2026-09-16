from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.enums import UserRole
from app.modules.users.auth import require_role
from app.modules.users.models import User
from app.modules.visits.part_items_schemas import PartItemCreate, PartItemOut
from app.modules.visits.part_items_service import PartItemService

router = APIRouter(prefix="/visits/{visit_id}/part-items", tags=["visit-part-items"])


@router.post("", response_model=PartItemOut, status_code=201)
async def add_part_item(
    visit_id,
    data: PartItemCreate,
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MASTER)),
):
    service = PartItemService(session)
    item = await service.add_item(visit_id, data, acting_user)
    await session.commit()
    return item
