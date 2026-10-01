import uuid

from sqlalchemy import select

from app.modules.users.audit import AuditLog
from app.modules.users.models import User
from app.core.enums import UserRole
from app.modules.users.schemas import UserCreate
from app.modules.users.service import UserService


async def test_create_user_writes_audit_row(session):
    admin = User(role=UserRole.ADMIN, full_name="Админ", branch_id=uuid.uuid4())
    session.add(admin)
    await session.flush()

    service = UserService(session)
    created = await service.create_user(
        UserCreate(role=UserRole.MECHANIC, full_name="Механик Петя"), acting_user=admin
    )

    assert created.id is not None
    assert created.role == UserRole.MECHANIC

    row = (
        await session.execute(select(AuditLog).where(AuditLog.entity_id == created.id))
    ).scalar_one()
    assert row.action == "create"
    assert row.entity_type == "user"


async def test_get_by_telegram_id_finds_active_user(session):
    user = User(role=UserRole.MASTER, full_name="Мастер", telegram_id=555111, branch_id=uuid.uuid4())
    session.add(user)
    await session.flush()

    found = await UserService(session).get_by_telegram_id(555111)
    assert found is not None
    assert found.id == user.id


async def test_get_by_telegram_id_returns_none_when_unknown(session):
    found = await UserService(session).get_by_telegram_id(999999)
    assert found is None


async def test_get_by_telegram_id_ignores_soft_deleted_user(session):
    from datetime import datetime, timezone

    user = User(role=UserRole.MASTER, full_name="Уволенный", telegram_id=555222, branch_id=uuid.uuid4())
    session.add(user)
    await session.flush()
    user.deleted_at = datetime.now(timezone.utc)
    await session.flush()

    assert await UserService(session).get_by_telegram_id(555222) is None
