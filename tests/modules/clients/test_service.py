import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.enums import UserRole
from app.core.exceptions import ClientPhoneTaken
from app.modules.clients.models import Client
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


async def test_get_ignores_soft_deleted_client(session):
    admin = User(role=UserRole.ADMIN, full_name="Админ", branch_id=uuid.uuid4())
    session.add(admin)
    await session.flush()

    service = ClientService(session)
    client = await service.create_client(ClientCreate(full_name="Иван", phone="79991234567"), admin)
    client.deleted_at = datetime.now(timezone.utc)
    await session.flush()

    assert await service.get(client.id) is None


async def test_create_client_rejects_phone_of_active_client(session):
    admin = User(role=UserRole.ADMIN, full_name="Админ", branch_id=uuid.uuid4())
    session.add(admin)
    await session.flush()

    service = ClientService(session)
    await service.create_client(ClientCreate(full_name="Иван", phone="79991234567"), admin)

    with pytest.raises(ClientPhoneTaken):
        await service.create_client(ClientCreate(full_name="Пётр", phone="+7 999 123-45-67"), admin)


async def test_create_client_reuses_phone_of_soft_deleted_client(session):
    admin = User(role=UserRole.ADMIN, full_name="Админ", branch_id=uuid.uuid4())
    session.add(admin)
    await session.flush()

    service = ClientService(session)
    old = await service.create_client(ClientCreate(full_name="Иван", phone="79991234567"), admin)
    old.deleted_at = datetime.now(timezone.utc)
    await session.flush()

    new = await service.create_client(ClientCreate(full_name="Пётр", phone="79991234567"), admin)
    assert new.id != old.id


async def test_db_rejects_duplicate_phone_of_active_clients(session):
    session.add_all([
        Client(full_name="Иван", phone_normalized="79991234567", phone_display="79991234567"),
        Client(full_name="Пётр", phone_normalized="79991234567", phone_display="79991234567"),
    ])
    with pytest.raises(IntegrityError):
        await session.flush()
