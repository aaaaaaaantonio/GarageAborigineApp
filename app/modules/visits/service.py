import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import UserRole, VisitStatus, WorkItemStatus
from app.core.exceptions import (
    CancelReasonRequired,
    InvalidAssignedMaster,
    InvalidTransition,
    MileageRollbackNotConfirmed,
    NotAllWorkItemsReady,
    VehicleNotFound,
    VisitNotFound,
)
from app.modules.notifications.factory import get_notification_sender
from app.modules.notifications.interfaces import NotificationSender
from app.modules.users.audit import record_audit
from app.modules.users.models import User
from app.modules.users.repository import UserRepository
from app.modules.vehicles.service import VehicleService
from app.modules.visits.fsm import ALLOWED_TRANSITIONS
from app.modules.visits.models import Visit, VisitPartItem, VisitStatusLog, VisitWorkItem
from app.modules.visits.repository import VisitRepository
from app.modules.visits.schemas import VisitCreate, VisitListOut, VisitOut


VISIT_LIST_LIMIT = 30


def _summary_out(row) -> VisitOut:
    return VisitOut(
        id=row.id,
        status=row.status,
        mileage_at_intake=row.mileage_at_intake,
        total_amount=row.total_amount,
        created_at=row.created_at,
        client_id=row.client_id,
        client_name=row.client_name,
        vehicle_id=row.vehicle_id,
        plate_number=row.plate_number,
        make_model=f"{row.make} {row.model}",
        assigned_master_id=row.assigned_master_id,
        master_name=row.master_name,
    )


class VisitService:
    def __init__(self, session: AsyncSession, notification_sender: NotificationSender | None = None):
        self.session = session
        self.repo = VisitRepository(session)
        self.vehicle_service = VehicleService(session)
        self.user_repo = UserRepository(session)
        self.notification_sender = notification_sender or get_notification_sender(session)

    async def create_visit(self, data: VisitCreate, acting_user: User) -> Visit:
        vehicle = await self.vehicle_service.get(data.vehicle_id)
        if vehicle is None:
            raise VehicleNotFound()
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

    async def get_summary(self, visit_id) -> VisitOut | None:
        row = await self.repo.get_summary(visit_id)
        return None if row is None else _summary_out(row)

    async def list_visits(
        self,
        acting_user: User,
        *,
        active: bool = False,
        client_id: uuid.UUID | None = None,
        vehicle_id: uuid.UUID | None = None,
    ) -> VisitListOut:
        rows = await self.repo.list_summaries(
            viewer_id=acting_user.id,
            active=active,
            client_id=client_id,
            vehicle_id=vehicle_id,
            limit=VISIT_LIST_LIMIT + 1,
        )
        return VisitListOut(
            items=[_summary_out(r) for r in rows[:VISIT_LIST_LIMIT]],
            has_more=len(rows) > VISIT_LIST_LIMIT,
        )

    async def change_status(
        self, visit_id, new_status: VisitStatus, acting_user: User, reason: str | None = None
    ) -> Visit:
        visit = await self.repo.get(visit_id)
        if visit is None:
            raise VisitNotFound()

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
        if visit is None:
            raise VisitNotFound()

        work_result = await self.session.execute(
            select(VisitWorkItem).where(VisitWorkItem.visit_id == visit_id)
        )
        work_total = sum(
            (Decimal(str(i.norm_hours)) * Decimal(str(i.hourly_rate)) for i in work_result.scalars()),
            Decimal("0"),
        )

        part_result = await self.session.execute(
            select(VisitPartItem).where(VisitPartItem.visit_id == visit_id)
        )
        part_total = sum(
            (Decimal(str(p.quantity)) * Decimal(str(p.unit_price)) for p in part_result.scalars()),
            Decimal("0"),
        )

        visit.total_amount = work_total + part_total - Decimal(str(visit.discount))
        await self.session.flush()
        return visit
