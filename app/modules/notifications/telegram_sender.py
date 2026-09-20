import uuid

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import VisitStatus
from app.modules.notifications.logging_sender import LoggingNotificationSender
from app.modules.users.models import User
from app.modules.visits.models import Visit, VisitWorkItem


class TelegramNotificationSender:
    def __init__(self, session: AsyncSession, bot: Bot):
        self.session = session
        self.bot = bot
        self._log = LoggingNotificationSender(session)

    async def _master_chat_id(self, master_id: uuid.UUID) -> int | None:
        master = await self.session.get(User, master_id)
        return master.telegram_id if master else None

    async def _send(self, chat_id: int | None, text: str) -> None:
        if chat_id is None:
            return
        await self.bot.send_message(chat_id=chat_id, text=text)

    async def send_status_changed(self, visit: Visit, old_status: VisitStatus, new_status: VisitStatus) -> None:
        await self._log.send_status_changed(visit, old_status, new_status)
        chat_id = await self._master_chat_id(visit.assigned_master_id)
        await self._send(chat_id, f"Заезд {visit.id}: статус изменён {old_status.value} → {new_status.value}")

    async def send_extra_work_approval_request(self, work_item: VisitWorkItem) -> None:
        await self._log.send_extra_work_approval_request(work_item)
        visit = await self.session.get(Visit, work_item.visit_id)
        chat_id = await self._master_chat_id(visit.assigned_master_id) if visit else None
        await self._send(chat_id, f"Требуется согласование доп.работы по заезду {work_item.visit_id}")

    async def send_document(self, visit: Visit, url: str) -> None:
        await self._log.send_document(visit, url)
        chat_id = await self._master_chat_id(visit.assigned_master_id)
        await self._send(chat_id, f"Документ по заезду {visit.id} готов: {url}")
