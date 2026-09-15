import uuid

from app.core.enums import UserRole
from app.modules.clients.schemas import ClientCreate
from app.modules.clients.service import ClientService
from app.modules.users.models import User


async def test_create_client_normalizes_phone_and_finds_by_any_format(session):
    admin = User(role=UserRole.ADMIN, full_name="Админ", branch_id=uuid.uuid4())
    session.add(admin)
    await session.flush()

    service = ClientService(session)
    await service.create_client(
        ClientCreate(full_name="Иван Иванов", phone="+7 (999) 123-45-67"), admin
    )

    found = await service.get_by_phone("89991234567")
    assert found is not None
    assert found.full_name == "Иван Иванов"
