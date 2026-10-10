import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import get_session
from app.modules.auth.telegram import InitDataInvalid, verify_init_data
from app.modules.auth.tokens import SessionNotConfigured, issue_session_token
from app.modules.users.auth import get_current_user
from app.modules.users.models import User
from app.modules.users.schemas import UserOut
from app.modules.users.service import UserService

router = APIRouter(prefix="/auth", tags=["auth"])


class TelegramLogin(BaseModel):
    init_data: str


class DevLogin(BaseModel):
    user_id: uuid.UUID


class AuthOut(BaseModel):
    token: str
    user: UserOut


def _issue(user: User) -> AuthOut:
    try:
        token = issue_session_token(user.id)
    except SessionNotConfigured:
        raise HTTPException(503, "SESSION_SECRET не задан")
    return AuthOut(token=token, user=UserOut.model_validate(user))


def _require_dev_login() -> None:
    if not settings.dev_login:
        raise HTTPException(404, "Not Found")


@router.post("/telegram", response_model=AuthOut)
async def telegram_login(data: TelegramLogin, session: AsyncSession = Depends(get_session)):
    if not settings.telegram_bot_token or not settings.session_secret:
        raise HTTPException(503, "Вход через Telegram не настроен")
    try:
        telegram_id = verify_init_data(
            data.init_data, settings.telegram_bot_token, settings.telegram_init_data_max_age_s
        )
    except InitDataInvalid:
        raise HTTPException(401, "Неверные данные Telegram")
    user = await UserService(session).get_by_telegram_id(telegram_id)
    if user is None:
        raise HTTPException(403, "Вы не сотрудник сервиса")
    return _issue(user)


@router.get("/dev-users", response_model=list[UserOut], dependencies=[Depends(_require_dev_login)])
async def dev_users(session: AsyncSession = Depends(get_session)):
    return await UserService(session).list_users()


@router.post("/dev-login", response_model=AuthOut, dependencies=[Depends(_require_dev_login)])
async def dev_login(data: DevLogin, session: AsyncSession = Depends(get_session)):
    user = await session.get(User, data.user_id)
    if user is None or user.deleted_at is not None:
        raise HTTPException(404, "User not found")
    return _issue(user)


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return user
