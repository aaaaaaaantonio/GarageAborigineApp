import uuid
from collections import defaultdict
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import VisitNotFound
from app.modules.clients.models import Client
from app.modules.pay.calc import line_pay
from app.modules.settings.service import SettingsService
from app.modules.users.models import User
from app.modules.vehicles.models import Vehicle
from app.modules.visits.mechanic_view_schemas import MechanicPartOut, MechanicVisitOut, MechanicWorkOut
from app.modules.visits.models import Visit, VisitPartItem
from app.modules.visits.work_items_service import WorkItemService


class NotYourVisit(Exception):
    pass


def _money(value) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.01")))


class MechanicViewService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, visit_id: uuid.UUID, mechanic: User) -> MechanicVisitOut:
        visit = await self.session.get(Visit, visit_id)
        if visit is None or visit.deleted_at is not None:
            raise VisitNotFound()
        works = await WorkItemService(self.session).list_for_visit(visit_id)
        if not any(w.assigned_mechanic_id == mechanic.id for w in works):
            raise NotYourVisit()
        seen = await SettingsService(self.session).visibility()
        prices = seen.mechanic_sees_prices
        client = await self.session.get(Client, visit.client_id)
        vehicle = await self.session.get(Vehicle, visit.vehicle_id)
        master = await self.session.get(User, visit.assigned_master_id)

        result = await self.session.execute(
            select(VisitPartItem).where(VisitPartItem.visit_id == visit_id).order_by(VisitPartItem.name, VisitPartItem.id)
        )
        parts: dict[uuid.UUID, list[MechanicPartOut]] = defaultdict(list)
        for p in result.scalars():
            parts[p.work_item_id].append(MechanicPartOut(
                name=p.name, article_number=p.article_number, quantity=p.quantity,
                availability_status=p.availability_status,
                unit_price=_money(p.unit_price) if prices else None,
                amount=_money(Decimal(p.quantity) * Decimal(str(p.unit_price))) if prices else None,
            ))

        out_works: list[MechanicWorkOut] = []
        my_pays: list[Decimal] = []
        for w in works:
            mine = w.assigned_mechanic_id == mechanic.id
            pay = None
            if mine and prices:
                pay = line_pay(w.mechanic_pay, w.norm_hours, w.hourly_rate, mechanic.pay_scheme, mechanic.pay_value)
                if pay is not None:
                    my_pays.append(pay)
            out_works.append(MechanicWorkOut(
                id=w.id, name=w.name, category=w.category, status=w.status,
                mechanic_name=w.assigned_mechanic_name, is_mine=mine, norm_hours=float(w.norm_hours),
                hourly_rate=_money(w.hourly_rate) if prices else None,
                amount=_money(Decimal(str(w.norm_hours)) * Decimal(str(w.hourly_rate))) if prices else None,
                my_pay=float(pay) if pay is not None else None,
                parts=parts.get(w.id, []),
            ))

        return MechanicVisitOut(
            id=visit.id, status=visit.status, created_at=visit.created_at, mileage_at_intake=visit.mileage_at_intake,
            plate_number=vehicle.plate_number, make_model=f"{vehicle.make} {vehicle.model}".strip(),
            master_name=master.full_name,
            client_name=client.full_name if seen.mechanic_sees_client_name else None,
            client_phone=client.phone_display if seen.mechanic_sees_client_phone else None,
            client_telegram_username=client.telegram_username if seen.mechanic_sees_client_phone else None,
            vin=vehicle.vin if seen.mechanic_sees_vin else None,
            discount=_money(visit.discount) if prices else None,
            total_amount=_money(visit.total_amount) if prices else None,
            my_pay_total=float(sum(my_pays)) if my_pays else None,
            works=out_works,
        )
