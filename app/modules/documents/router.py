import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.enums import UserRole
from app.core.exceptions import DocumentNotFound, VisitNotFound
from app.modules.documents.service import DocumentService
from app.modules.users.auth import require_role
from app.modules.users.models import User

router = APIRouter(prefix="/visits/{visit_id}/document", tags=["documents"])
files_router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("")
async def generate_document(
    visit_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MASTER)),
):
    service = DocumentService(session)
    try:
        url = await service.generate_visit_document(visit_id)
    except VisitNotFound:
        raise HTTPException(404, "Visit not found")
    await session.commit()
    # The document is one-per-visit, so its id is the visit id.
    return {"document_id": str(visit_id), "document_url": url}


@files_router.get("/{document_id}/file")
async def get_document_file(
    document_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MASTER)),
):
    service = DocumentService(session)
    try:
        content = await service.get_visit_document(document_id)
    except DocumentNotFound:
        raise HTTPException(404, "Документ не найден")
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="visit-{document_id}.pdf"'},
    )
