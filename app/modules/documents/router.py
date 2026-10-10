import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.enums import UserRole
from app.core.exceptions import DocumentNotFound, VisitNotFound
from app.modules.auth.tokens import (
    DOWNLOAD_TTL_S,
    InvalidSessionToken,
    SessionNotConfigured,
    issue_download_token,
    read_download_token,
)
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


@router.post("/link")
async def create_download_link(
    visit_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MASTER)),
):
    try:
        token = issue_download_token(visit_id)
    except SessionNotConfigured:
        raise HTTPException(503, "SESSION_SECRET не задан")
    try:
        await DocumentService(session).generate_visit_document(visit_id)
    except VisitNotFound:
        raise HTTPException(404, "Visit not found")
    await session.commit()
    return {"url": f"/documents/{visit_id}/download?token={token}", "expires_in": DOWNLOAD_TTL_S}


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


@files_router.get("/{document_id}/download")
async def download_document(
    document_id: uuid.UUID,
    token: str = Query(...),
    session: AsyncSession = Depends(get_session),
):
    """No Authorization header here: the signed token is the permission (one document, 5 minutes)."""
    try:
        allowed = read_download_token(token)
    except InvalidSessionToken:
        allowed = None
    if allowed != document_id:
        raise HTTPException(403, "Ссылка устарела, нажмите PDF ещё раз")
    try:
        content = await DocumentService(session).get_visit_document(document_id)
    except DocumentNotFound:
        raise HTTPException(404, "Документ не найден")
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="visit-{document_id}.pdf"'},
    )
