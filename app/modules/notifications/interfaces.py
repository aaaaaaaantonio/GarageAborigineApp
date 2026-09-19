from typing import Protocol

from app.core.enums import VisitStatus
from app.modules.visits.models import Visit, VisitWorkItem


class NotificationSender(Protocol):
    async def send_status_changed(self, visit: Visit, old_status: VisitStatus, new_status: VisitStatus) -> None: ...
    async def send_extra_work_approval_request(self, work_item: VisitWorkItem) -> None: ...
    async def send_document(self, visit: Visit, url: str) -> None: ...
