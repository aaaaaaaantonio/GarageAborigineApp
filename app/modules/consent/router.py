from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.enums import UserRole
from app.core.exceptions import ClientPhoneTaken, DraftAlreadyUsed, DraftExpired, DraftNotFound
from app.modules.consent.schemas import ConsentConfirm, ConsentDraftOut, ConsentPaperRegister
from app.modules.consent.service import ConsentService
from app.modules.users.auth import require_role
from app.modules.users.models import User

router = APIRouter(prefix="/consent", tags=["consent"])


@router.post("/draft", response_model=ConsentDraftOut, status_code=201)
async def create_draft(
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MASTER)),
):
    service = ConsentService(session)
    draft = await service.create_draft()
    await session.commit()
    return draft


@router.get("/draft/{token}")
async def get_draft(token: str, session: AsyncSession = Depends(get_session)):
    service = ConsentService(session)
    try:
        draft = await service.get_valid_draft(token)
    except DraftNotFound:
        raise HTTPException(404, "Черновик не найден")
    except DraftExpired:
        raise HTTPException(410, "Срок действия ссылки истёк")
    return {"token": draft.token, "expires_at": draft.expires_at}


@router.post("/confirm")
async def confirm(token: str, data: ConsentConfirm, request: Request, session: AsyncSession = Depends(get_session)):
    ip_address = request.client.host if request.client else None
    service = ConsentService(session)
    try:
        client = await service.confirm(token, data, ip_address)
    except DraftNotFound:
        raise HTTPException(404, "Черновик не найден")
    except DraftExpired:
        raise HTTPException(410, "Срок действия ссылки истёк")
    except DraftAlreadyUsed:
        raise HTTPException(409, "Черновик уже был подтверждён")
    except ClientPhoneTaken:
        raise HTTPException(409, "Клиент с таким телефоном уже есть")
    await session.commit()
    return {"client_id": str(client.id)}


@router.post("/paper")
async def register_paper(
    data: ConsentPaperRegister,
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MASTER)),
):
    service = ConsentService(session)
    try:
        client = await service.register_paper(data, acting_user)
    except ClientPhoneTaken:
        raise HTTPException(409, "Клиент с таким телефоном уже есть")
    await session.commit()
    return {"client_id": str(client.id)}
