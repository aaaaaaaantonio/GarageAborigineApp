import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, String, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import VisitStatus
from app.core.models import Base, UUIDPkMixin
from app.modules.visits.models import Visit, VisitWorkItem


class NotificationOutbox(Base, UUIDPkMixin):
    """MVP-заглушка доставки: реальная отправка через Telegram Bot API
    подключается в следующем цикле (бот), подменяя NotificationSender —
    вызывающий код (visits.service) не меняется."""

    __tablename__ = "notifications_outbox"

    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LoggingNotificationSender:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def send_status_changed(self, visit: Visit, old_status: VisitStatus, new_status: VisitStatus) -> None:
        self.session.add(
            NotificationOutbox(
                kind="status_changed",
                payload={"visit_id": str(visit.id), "old_status": old_status.value, "new_status": new_status.value},
            )
        )
        await self.session.flush()

    async def send_extra_work_approval_request(self, work_item: VisitWorkItem) -> None:
        self.session.add(
            NotificationOutbox(
                kind="extra_work_approval_request",
                payload={"work_item_id": str(work_item.id), "visit_id": str(work_item.visit_id)},
            )
        )
        await self.session.flush()

    async def send_document(self, visit: Visit, url: str) -> None:
        self.session.add(
            NotificationOutbox(kind="document_ready", payload={"visit_id": str(visit.id), "url": url})
        )
        await self.session.flush()

    async def send_work_assigned(self, work_item: VisitWorkItem, mechanic_id: uuid.UUID) -> None:
        await self._add_work_assignment("work_assigned", work_item, mechanic_id)

    async def send_work_unassigned(self, work_item: VisitWorkItem, mechanic_id: uuid.UUID) -> None:
        await self._add_work_assignment("work_unassigned", work_item, mechanic_id)

    async def _add_work_assignment(self, kind: str, work_item: VisitWorkItem, mechanic_id: uuid.UUID) -> None:
        self.session.add(
            NotificationOutbox(
                kind=kind,
                payload={
                    "work_item_id": str(work_item.id),
                    "visit_id": str(work_item.visit_id),
                    "mechanic_id": str(mechanic_id),
                },
            )
        )
        await self.session.flush()
