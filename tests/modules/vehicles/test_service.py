import uuid
from datetime import date, datetime, timezone

import pytest

from app.core.enums import UserRole
from app.core.exceptions import VehicleNotFound
from app.modules.clients.schemas import ClientCreate
from app.modules.clients.service import ClientService
from app.modules.users.models import User
from app.modules.vehicles.schemas import OwnershipCreate, VehicleCreate
from app.modules.vehicles.repository import VehicleRepository
from app.modules.vehicles.service import VehicleService


async def test_attach_owner_and_list_owners(session):
    admin = User(role=UserRole.ADMIN, full_name="Админ", branch_id=uuid.uuid4())
    session.add(admin)
    await session.flush()

    client = await ClientService(session).create_client(
        ClientCreate(full_name="Иван", phone="79991234567"), admin
    )
    vehicle_service = VehicleService(session)
    vehicle = await vehicle_service.create_vehicle(
        VehicleCreate(vin="X" * 17, plate_number="А123ВС77", make="Toyota", model="Camry"),
        admin,
    )

    await vehicle_service.attach_owner(
        vehicle.id, OwnershipCreate(client_id=client.id, date_from=date(2024, 1, 1)), admin
    )

    owners = await vehicle_service.get_owners(vehicle.id)
    assert len(owners) == 1
    assert owners[0].client_id == client.id


async def test_attach_owner_unknown_vehicle_raises_not_found(session):
    admin = User(role=UserRole.ADMIN, full_name="Админ", branch_id=uuid.uuid4())
    session.add(admin)
    await session.flush()
    client = await ClientService(session).create_client(ClientCreate(full_name="Иван", phone="79991234567"), admin)

    with pytest.raises(VehicleNotFound):
        await VehicleService(session).attach_owner(
            uuid.uuid4(), OwnershipCreate(client_id=client.id, date_from=date(2024, 1, 1)), admin
        )


async def test_update_mileage_unknown_vehicle_raises_not_found(session):
    with pytest.raises(VehicleNotFound):
        await VehicleService(session).update_mileage(uuid.uuid4(), 1000)


async def test_get_by_vin_ignores_soft_deleted_vehicle(session):
    admin = User(role=UserRole.ADMIN, full_name="Админ", branch_id=uuid.uuid4())
    session.add(admin)
    await session.flush()
    vehicle = await VehicleService(session).create_vehicle(
        VehicleCreate(vin="Y" * 17, plate_number="В456ОР77", make="Lada", model="Vesta"), admin
    )
    vehicle.deleted_at = datetime.now(timezone.utc)
    await session.flush()

    assert await VehicleRepository(session).get_by_vin("Y" * 17) is None
