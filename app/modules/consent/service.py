from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.enums import ConsentMethod
from app.core.exceptions import DraftExpired, DraftNotFound
from app.modules.clients.models import Client
from app.modules.clients.service import ClientService
from app.modules.consent.models import Consent, ConsentDraft
from app.modules.consent.repository import ConsentRepository
from app.modules.consent.schemas import ConsentConfirm, ConsentPaperRegister
from app.modules.consent.tokens import generate_token
from app.modules.clients.schemas import ClientCreate
from app.modules.users.models import User


CONSENT_TEXT_VERSION = "v1"


class ConsentService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = ConsentRepository(session)
        self.client_service = ClientService(session)

    async def create_draft(self) -> ConsentDraft:
        draft = ConsentDraft(
            token=generate_token(),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=settings.consent_token_ttl_minutes),
        )
        return await self.repo.create_draft(draft)

    async def get_valid_draft(self, token: str) -> ConsentDraft:
        draft = await self.repo.get_draft_by_token(token)
        if draft is None:
            raise DraftNotFound()
        if draft.expires_at < datetime.now(timezone.utc):
            raise DraftExpired()
        return draft

    async def confirm(self, token: str, data: ConsentConfirm) -> Client:
        draft = await self.get_valid_draft(token)

        client = await self.client_service.create_client(
            ClientCreate(full_name=data.full_name, phone=data.phone, client_type=data.client_type),
            acting_user=None,  # клиент сам себя регистрирует, без acting_user из CRM
        )
        draft.converted_client_id = client.id

        await self.repo.create_consent(
            Consent(
                client_id=client.id,
                draft_id=draft.id,
                consent_date=datetime.now(timezone.utc),
                consent_text_version=CONSENT_TEXT_VERSION,
                consent_method=ConsentMethod.QR_ONSITE,
                ip_address=data.ip_address,
            )
        )
        return client

    async def register_paper(self, data: ConsentPaperRegister, acting_user: User) -> Client:
        client = await self.client_service.create_client(
            ClientCreate(full_name=data.full_name, phone=data.phone, client_type=data.client_type),
            acting_user=acting_user,
        )
        await self.repo.create_consent(
            Consent(
                client_id=client.id,
                consent_date=datetime.now(timezone.utc),
                consent_text_version=CONSENT_TEXT_VERSION,
                consent_method=ConsentMethod.PAPER,
                verification_ref=data.verification_ref,
            )
        )
        return client
