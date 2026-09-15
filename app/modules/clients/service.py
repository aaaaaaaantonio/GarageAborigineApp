from sqlalchemy.ext.asyncio import AsyncSession

from app.core.phone import normalize_phone
from app.modules.clients.models import Client
from app.modules.clients.repository import ClientRepository
from app.modules.clients.schemas import ClientCreate
from app.modules.users.audit import record_audit
from app.modules.users.models import User


class ClientService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = ClientRepository(session)

    async def create_client(self, data: ClientCreate, acting_user: User) -> Client:
        client = Client(
            full_name=data.full_name,
            phone_normalized=normalize_phone(data.phone),
            phone_display=data.phone,
            client_type=data.client_type,
            legal_details=data.legal_details,
            telegram_id=data.telegram_id,
            telegram_username=data.telegram_username,
        )
        await self.repo.create(client)
        await record_audit(
            self.session,
            user=acting_user,
            entity_type="client",
            entity_id=client.id,
            action="create",
            new_value={"full_name": client.full_name},
        )
        return client

    async def get(self, client_id) -> Client | None:
        return await self.repo.get(client_id)

    async def get_by_phone(self, phone_raw: str) -> Client | None:
        return await self.repo.get_by_phone_normalized(normalize_phone(phone_raw))
