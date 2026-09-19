from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.consent.models import Consent, ConsentDraft


class ConsentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_draft(self, draft: ConsentDraft) -> ConsentDraft:
        self.session.add(draft)
        await self.session.flush()
        return draft

    async def get_draft_by_token(self, token: str, for_update: bool = False) -> ConsentDraft | None:
        stmt = select(ConsentDraft).where(ConsentDraft.token == token)
        if for_update:
            stmt = stmt.with_for_update()
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def create_consent(self, consent: Consent) -> Consent:
        self.session.add(consent)
        await self.session.flush()
        return consent
