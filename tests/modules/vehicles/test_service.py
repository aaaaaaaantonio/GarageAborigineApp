import uuid
from datetime import date

from app.core.enums import UserRole
from app.modules.clients.schemas import ClientCreate
from app.modules.clients.service import ClientService
from app.modules.users.models import User
from app.modules.vehicles.schemas import OwnershipCreate, VehicleCreate
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
