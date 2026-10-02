import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.clients.models import Client
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

    async def list_current_for_client(self, client_id: uuid.UUID) -> list[Vehicle]:
        result = await self.session.execute(
            select(Vehicle)
            .join(VehicleOwnership, VehicleOwnership.vehicle_id == Vehicle.id)
            .where(
                VehicleOwnership.client_id == client_id,
                VehicleOwnership.date_to.is_(None),
                Vehicle.deleted_at.is_(None),
            )
            .order_by(Vehicle.plate_number)
        )
        return list(result.scalars().unique())

    async def get_current_owner(self, vehicle_id: uuid.UUID) -> Client | None:
        result = await self.session.execute(
            select(Client)
            .join(VehicleOwnership, VehicleOwnership.client_id == Client.id)
            .where(
                VehicleOwnership.vehicle_id == vehicle_id,
                VehicleOwnership.date_to.is_(None),
                Client.deleted_at.is_(None),
            )
            .order_by(VehicleOwnership.date_from.desc())
        )
        return result.scalars().first()
