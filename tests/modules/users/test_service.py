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
