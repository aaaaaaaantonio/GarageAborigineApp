import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import UserRole, VisitStatus, WorkItemStatus
from app.core.exceptions import (
    CancelReasonRequired,
    InvalidAssignedMaster,
    InvalidTransition,
    MileageRollbackNotConfirmed,
    NotAllWorkItemsReady,
)
from app.modules.notifications.interfaces import NotificationSender
from app.modules.notifications.logging_sender import LoggingNotificationSender
from app.modules.users.audit import record_audit
from app.modules.users.models import User
from app.modules.users.repository import UserRepository
from app.modules.vehicles.service import VehicleService
from app.modules.visits.fsm import ALLOWED_TRANSITIONS
from app.modules.visits.models import Visit, VisitPartItem, VisitStatusLog, VisitWorkItem
from app.modules.visits.repository import VisitRepository
from app.modules.visits.schemas import VisitCreate


class VisitService:
    def __init__(self, session: AsyncSession, notification_sender: NotificationSender | None = None):
        self.session = session
        self.repo = VisitRepository(session)
        self.vehicle_service = VehicleService(session)
        self.user_repo = UserRepository(session)
        self.notification_sender = notification_sender or LoggingNotificationSender(session)

    async def create_visit(self, data: VisitCreate, acting_user: User) -> Visit:
        vehicle = await self.vehicle_service.get(data.vehicle_id)
        assert vehicle is not None
        if data.mileage_at_intake < vehicle.mileage_current and not data.mileage_manually_confirmed:
            raise MileageRollbackNotConfirmed()

        master = await self.user_repo.get(data.assigned_master_id)
        if master is None or master.deleted_at is not None or master.role != UserRole.MASTER:
            raise InvalidAssignedMaster()

        visit = Visit(
            client_id=data.client_id,
            vehicle_id=data.vehicle_id,
            assigned_master_id=data.assigned_master_id,
            mileage_at_intake=data.mileage_at_intake,
            mileage_manually_confirmed=data.mileage_manually_confirmed,
            complaint_text=data.complaint_text,
            intake_photos=data.intake_photos,
            status=VisitStatus.RECEIVED,
        )
        await self.repo.create(visit)
        await self.vehicle_service.update_mileage(data.vehicle_id, data.mileage_at_intake)
        await record_audit(
            self.session,
            user=acting_user,
            entity_type="visit",
            entity_id=visit.id,
            action="create",
            new_value={"status": visit.status.value},
        )
        return visit

    async def get(self, visit_id) -> Visit | None:
        return await self.repo.get(visit_id)

    async def change_status(
        self, visit_id, new_status: VisitStatus, acting_user: User, reason: str | None = None
    ) -> Visit:
        visit = await self.repo.get(visit_id)
        assert visit is not None

        if new_status not in ALLOWED_TRANSITIONS[visit.status]:
            raise InvalidTransition()

        if new_status == VisitStatus.CANCELLED and not reason:
            raise CancelReasonRequired()

        if new_status == VisitStatus.READY:
            result = await self.session.execute(
                select(VisitWorkItem).where(VisitWorkItem.visit_id == visit_id)
            )
            items = list(result.scalars())
            if any(i.status != WorkItemStatus.READY for i in items):
                raise NotAllWorkItemsReady()

        old_status = visit.status
        visit.status = new_status
        if new_status == VisitStatus.CANCELLED:
            visit.cancelled_reason = reason

        self.session.add(
            VisitStatusLog(
                visit_id=visit.id,
                from_status=old_status,
                to_status=new_status,
                changed_by_user_id=acting_user.id,
                reason=reason,
            )
        )
        await self.session.flush()

        if new_status in (VisitStatus.READY, VisitStatus.WAITING_PARTS):
            await self.notification_sender.send_status_changed(visit, old_status, new_status)

        return visit

    async def recalculate_total(self, visit_id: uuid.UUID) -> Visit:
        visit = await self.repo.get(visit_id)
        assert visit is not None

        work_result = await self.session.execute(
            select(VisitWorkItem).where(VisitWorkItem.visit_id == visit_id)
        )
        work_total = sum(float(i.norm_hours) * float(i.hourly_rate) for i in work_result.scalars())

        part_result = await self.session.execute(
            select(VisitPartItem).where(VisitPartItem.visit_id == visit_id)
        )
        part_total = sum(float(p.quantity) * float(p.unit_price) for p in part_result.scalars())

        visit.total_amount = work_total + part_total - float(visit.discount)
        await self.session.flush()
        return visit
