import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import VehicleNotFound, VehicleVinTaken
from app.core.plate import normalize_plate
from app.modules.clients.models import Client
from app.modules.users.audit import record_audit
from app.modules.users.models import User
from app.modules.vehicles.models import Vehicle, VehicleOwnership
from app.modules.vehicles.repository import VehicleRepository
from app.modules.vehicles.schemas import OwnershipCreate, VehicleCreate


class VehicleService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = VehicleRepository(session)

    async def create_vehicle(self, data: VehicleCreate, acting_user: User) -> Vehicle:
        if await self.repo.get_by_vin(data.vin) is not None:
            raise VehicleVinTaken()
        payload = data.model_dump()
        payload["plate_number"] = normalize_plate(payload["plate_number"])
        vehicle = Vehicle(**payload)
        await self.repo.create(vehicle)
        await record_audit(
            self.session,
            user=acting_user,
            entity_type="vehicle",
            entity_id=vehicle.id,
            action="create",
            new_value={"vin": vehicle.vin},
        )
        return vehicle

    async def get(self, vehicle_id: uuid.UUID) -> Vehicle | None:
        return await self.repo.get(vehicle_id)

    async def attach_owner(
        self, vehicle_id: uuid.UUID, data: OwnershipCreate, acting_user: User
    ) -> VehicleOwnership:
        vehicle = await self.repo.get(vehicle_id)
        if vehicle is None:
            raise VehicleNotFound()
        ownership = VehicleOwnership(vehicle_id=vehicle_id, **data.model_dump())
        await self.repo.add_ownership(ownership)
        await record_audit(
            self.session,
            user=acting_user,
            entity_type="vehicle_ownership",
            entity_id=ownership.id,
            action="create",
            new_value={"vehicle_id": str(vehicle_id), "client_id": str(data.client_id)},
        )
        return ownership

    async def get_owners(self, vehicle_id: uuid.UUID) -> list[VehicleOwnership]:
        return await self.repo.list_owners(vehicle_id)

    async def update_mileage(self, vehicle_id: uuid.UUID, mileage: int) -> Vehicle:
        vehicle = await self.repo.get(vehicle_id)
        if vehicle is None:
            raise VehicleNotFound()
        vehicle.mileage_current = mileage
        await self.session.flush()
        return vehicle

    async def list_current_for_client(self, client_id: uuid.UUID) -> list[Vehicle]:
        return await self.repo.list_current_for_client(client_id)

    async def get_current_owner(self, vehicle_id: uuid.UUID) -> Client | None:
        return await self.repo.get_current_owner(vehicle_id)
