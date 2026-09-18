import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.core.exceptions import DraftExpired
from app.modules.consent.models import ConsentDraft
from app.modules.consent.schemas import ConsentConfirm, ConsentPaperRegister
from app.modules.consent.service import ConsentService


async def test_confirm_converts_draft_to_client_with_consent(session):
    service = ConsentService(session)
    draft = await service.create_draft()

    client = await service.confirm(
        draft.token, ConsentConfirm(full_name="Иван", phone="79991234567", ip_address="127.0.0.1")
    )
    assert client.id is not None


async def test_expired_draft_rejected(session):
    service = ConsentService(session)
    draft = ConsentDraft(token="expired-token", expires_at=datetime.now(timezone.utc) - timedelta(minutes=1))
    session.add(draft)
    await session.flush()

    with pytest.raises(DraftExpired):
        await service.confirm(draft.token, ConsentConfirm(full_name="Иван", phone="79991234567"))


async def test_paper_fallback_creates_client_without_token(session):
    from app.core.enums import UserRole
    from app.modules.users.models import User

    admin = User(role=UserRole.ADMIN, full_name="Админ", branch_id=uuid.uuid4())
    session.add(admin)
    await session.flush()

    service = ConsentService(session)
    client = await service.register_paper(
        ConsentPaperRegister(full_name="Пётр", phone="79997654321"), admin
    )
    assert client.id is not None
