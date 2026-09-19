import uuid
from datetime import date

import pytest

from app.core.enums import UserRole
from app.core.exceptions import InvalidAssignedMaster, MileageRollbackNotConfirmed, VehicleNotFound
from app.modules.clients.schemas import ClientCreate
from app.modules.clients.service import ClientService
from app.modules.users.models import User
from app.modules.vehicles.schemas import VehicleCreate
from app.modules.vehicles.service import VehicleService
from app.modules.visits.schemas import VisitCreate
from app.modules.visits.service import VisitService


async def _setup(session):
    admin = User(role=UserRole.ADMIN, full_name="Админ", branch_id=uuid.uuid4())
    master = User(role=UserRole.MASTER, full_name="Мастер", branch_id=uuid.uuid4())
    session.add_all([admin, master])
    await session.flush()
    client = await ClientService(session).create_client(
        ClientCreate(full_name="Иван", phone="79991234567"), admin
    )
    vehicle = await VehicleService(session).create_vehicle(
        VehicleCreate(vin="X" * 17, plate_number="А123ВС77", make="Toyota", model="Camry"),
        admin,
    )
    await VehicleService(session).update_mileage(vehicle.id, 50_000)
    return admin, master, client, vehicle


async def test_lower_mileage_without_confirmation_rejected(session):
    admin, master, client, vehicle = await _setup(session)

    with pytest.raises(MileageRollbackNotConfirmed):
        await VisitService(session).create_visit(
            VisitCreate(
                client_id=client.id,
                vehicle_id=vehicle.id,
                assigned_master_id=master.id,
                mileage_at_intake=40_000,
            ),
            admin,
        )


async def test_lower_mileage_with_confirmation_accepted(session):
    admin, master, client, vehicle = await _setup(session)

    visit = await VisitService(session).create_visit(
        VisitCreate(
            client_id=client.id,
            vehicle_id=vehicle.id,
            assigned_master_id=master.id,
            mileage_at_intake=40_000,
            mileage_manually_confirmed=True,
        ),
        admin,
    )
    assert visit.mileage_manually_confirmed is True


async def test_non_master_assigned_master_rejected(session):
    admin, master, client, vehicle = await _setup(session)

    with pytest.raises(InvalidAssignedMaster):
        await VisitService(session).create_visit(
            VisitCreate(
                client_id=client.id,
                vehicle_id=vehicle.id,
                assigned_master_id=admin.id,
                mileage_at_intake=55_000,
            ),
            admin,
        )


async def test_nonexistent_assigned_master_rejected(session):
    admin, master, client, vehicle = await _setup(session)

    with pytest.raises(InvalidAssignedMaster):
        await VisitService(session).create_visit(
            VisitCreate(
                client_id=client.id,
                vehicle_id=vehicle.id,
                assigned_master_id=uuid.uuid4(),
                mileage_at_intake=55_000,
            ),
            admin,
        )


async def test_nonexistent_vehicle_raises_not_found(session):
    admin, master, client, vehicle = await _setup(session)

    with pytest.raises(VehicleNotFound):
        await VisitService(session).create_visit(
            VisitCreate(
                client_id=client.id,
                vehicle_id=uuid.uuid4(),
                assigned_master_id=master.id,
                mileage_at_intake=55_000,
            ),
            admin,
        )
