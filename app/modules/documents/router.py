import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.enums import UserRole
from app.modules.documents.service import DocumentService
from app.modules.users.auth import require_role
from app.modules.users.models import User

router = APIRouter(prefix="/visits/{visit_id}/document", tags=["documents"])


@router.post("")
async def generate_document(
    visit_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MASTER)),
):
    service = DocumentService(session)
    url = await service.generate_visit_document(visit_id)
    await session.commit()
    return {"document_url": url}
