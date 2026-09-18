import uuid

from app.core.enums import UserRole
from app.modules.clients.schemas import ClientCreate
from app.modules.clients.service import ClientService
from app.modules.search.service import SearchService
from app.modules.users.models import User
from app.modules.vehicles.schemas import VehicleCreate
from app.modules.vehicles.service import VehicleService


async def test_search_by_phone_any_format(session):
    admin = User(role=UserRole.ADMIN, full_name="Админ", branch_id=uuid.uuid4())
    session.add(admin)
    await session.flush()
    await ClientService(session).create_client(
        ClientCreate(full_name="Иван", phone="+7 (999) 123-45-67"), admin
    )

    results = await SearchService(session).search("89991234567")
    assert any(r["entity"] == "client" for r in results)


async def test_search_by_vin_suffix(session):
    admin = User(role=UserRole.ADMIN, full_name="Админ", branch_id=uuid.uuid4())
    session.add(admin)
    await session.flush()
    await VehicleService(session).create_vehicle(
        VehicleCreate(vin="JTDBR32E720012345", plate_number="А123", make="Toyota", model="Camry"), admin
    )

    results = await SearchService(session).search("2345")
    assert any(r["entity"] == "vehicle" for r in results)


async def test_search_by_name_typo_fuzzy(session):
    admin = User(role=UserRole.ADMIN, full_name="Админ", branch_id=uuid.uuid4())
    session.add(admin)
    await session.flush()
    await ClientService(session).create_client(ClientCreate(full_name="Иванов Пётр", phone="79991234567"), admin)

    results = await SearchService(session).search("Иванов Петр")
    assert any(r["entity"] == "client" for r in results)


async def test_recent_views_returns_last_n_for_user(session):
    admin = User(role=UserRole.ADMIN, full_name="Админ", branch_id=uuid.uuid4())
    session.add(admin)
    await session.flush()

    entity_id = uuid.uuid4()
    await SearchService(session).record_view(admin.id, "client", entity_id)

    recent = await SearchService(session).recent(admin.id)
    assert len(recent) == 1
    assert recent[0].entity_id == entity_id
