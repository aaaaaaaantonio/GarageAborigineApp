import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.clients.models import Client


class ClientRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, client: Client) -> Client:
        self.session.add(client)
        await self.session.flush()
        return client

    async def get(self, client_id: uuid.UUID) -> Client | None:
        return await self.session.get(Client, client_id)

    async def get_by_phone_normalized(self, phone_normalized: str) -> Client | None:
        result = await self.session.execute(
            select(Client).where(
                Client.phone_normalized == phone_normalized, Client.deleted_at.is_(None)
            )
        )
        return result.scalars().first()
