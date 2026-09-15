import uuid

from app.modules.users.audit import record_audit, AuditLog
from app.modules.users.models import User
from app.core.enums import UserRole
from sqlalchemy import select


async def test_record_audit_writes_row(session):
    user = User(role=UserRole.ADMIN, full_name="Admin", branch_id=uuid.uuid4())
    session.add(user)
    await session.flush()

    entity_id = uuid.uuid4()
    await record_audit(
        session,
        user=user,
        entity_type="client",
        entity_id=entity_id,
        action="create",
        new_value={"full_name": "Иван"},
    )

    row = (await session.execute(select(AuditLog).where(AuditLog.entity_id == entity_id))).scalar_one()
    assert row.action == "create"
    assert row.new_value == {"full_name": "Иван"}
