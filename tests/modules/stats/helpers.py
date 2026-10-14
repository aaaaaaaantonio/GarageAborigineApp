# tests/modules/stats/helpers.py
"""A small service with known numbers; dates are Moscow time around a fixed NOW."""
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

from app.core.enums import PartAvailability, UserRole, VisitStatus, WorkCategory, WorkItemStatus
from app.modules.clients.schemas import ClientCreate
from app.modules.clients.service import ClientService
from app.modules.stats.periods import MSK
from app.modules.users.models import User
from app.modules.vehicles.schemas import VehicleCreate
from app.modules.vehicles.service import VehicleService
from app.modules.visits.models import Visit, VisitPartItem, VisitStatusLog, VisitWorkItem

NOW = datetime(2026, 10, 14, 9, 0, tzinfo=timezone.utc)  # 12:00 МСК; month window = 15.09–14.10


def msk(month: int, day: int, hour: int = 12, minute: int = 0) -> datetime:
    return datetime(2026, month, day, hour, minute, tzinfo=MSK)


async def world(session) -> SimpleNamespace:
    def user(role, name):
        return User(role=role, full_name=name, branch_id=uuid.uuid4())

    w = SimpleNamespace(
        admin=user(UserRole.ADMIN, "Иванов"),
        master_a=user(UserRole.MASTER, "Кузнецов"),
        master_b=user(UserRole.MASTER, "Белова"),
        mech_a=user(UserRole.MECHANIC, "Морозов"),
        mech_b=user(UserRole.MECHANIC, "Соколов"),
    )
    session.add_all([w.admin, w.master_a, w.master_b, w.mech_a, w.mech_b])
    await session.flush()
    w.client = await ClientService(session).create_client(ClientCreate(full_name="Петров Иван", phone="79990000001"), w.admin)
    w.client2 = await ClientService(session).create_client(ClientCreate(full_name="Сидоров Пётр", phone="79990000002"), w.admin)
    w.vehicle = await VehicleService(session).create_vehicle(
        VehicleCreate(vin="A" * 17, plate_number="А123ВС77", make="Toyota", model="Camry"), w.admin
    )
    return w


async def visit(session, w, *, master, created, status=VisitStatus.ISSUED, closed=None, total=0, client=None, history=()):
    """A visit created at `created`; `history` = [(to_status, at)]; `closed` adds the final log entry to `status`."""
    v = Visit(
        client_id=(client or w.client).id, vehicle_id=w.vehicle.id, assigned_master_id=master.id,
        mileage_at_intake=1000, mileage_manually_confirmed=True, status=status, total_amount=total,
    )
    session.add(v)
    await session.flush()
    v.created_at = created
    entries = [*history, *([(status, closed)] if closed is not None else [])]
    for to_status, at in entries:
        session.add(VisitStatusLog(visit_id=v.id, to_status=to_status, changed_by_user_id=master.id, changed_at=at))
    await session.flush()
    return v


async def work(session, v, *, name, hours, rate, mechanic=None, category=WorkCategory.MAINTENANCE,
               extra=False, approved=False, status=WorkItemStatus.READY):
    item = VisitWorkItem(
        visit_id=v.id, free_text_name=name, category=category, norm_hours=hours, hourly_rate=rate, status=status,
        assigned_mechanic_id=mechanic.id if mechanic else None, is_extra_work=extra, approved_by_client=approved,
    )
    session.add(item)
    await session.flush()
    return item


async def part(session, v, item, *, qty, price):
    session.add(VisitPartItem(visit_id=v.id, work_item_id=item.id, name="Запчасть", quantity=qty, unit_price=price,
                              availability_status=PartAvailability.IN_STOCK))
    await session.flush()
