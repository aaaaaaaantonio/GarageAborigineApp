from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import UserRole, VisitStatus
from app.core.exceptions import InvalidAssignedMaster, MileageRollbackNotConfirmed
from app.modules.users.audit import record_audit
from app.modules.users.models import User
from app.modules.users.repository import UserRepository
from app.modules.vehicles.service import VehicleService
from app.modules.visits.models import Visit
from app.modules.visits.repository import VisitRepository
from app.modules.visits.schemas import VisitCreate


class VisitService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = VisitRepository(session)
        self.vehicle_service = VehicleService(session)
        self.user_repo = UserRepository(session)

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
