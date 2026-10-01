import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.vehicles.models import Vehicle, VehicleOwnership


class VehicleRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, vehicle: Vehicle) -> Vehicle:
        self.session.add(vehicle)
        await self.session.flush()
        return vehicle

    async def get(self, vehicle_id: uuid.UUID) -> Vehicle | None:
        return await self.session.get(Vehicle, vehicle_id)

    async def get_by_vin(self, vin: str) -> Vehicle | None:
        result = await self.session.execute(
            select(Vehicle).where(Vehicle.vin == vin, Vehicle.deleted_at.is_(None))
        )
        return result.scalars().first()

    async def add_ownership(self, ownership: VehicleOwnership) -> VehicleOwnership:
        self.session.add(ownership)
        await self.session.flush()
        return ownership

    async def list_owners(self, vehicle_id: uuid.UUID) -> list[VehicleOwnership]:
        result = await self.session.execute(
            select(VehicleOwnership).where(VehicleOwnership.vehicle_id == vehicle_id)
        )
        return list(result.scalars())
