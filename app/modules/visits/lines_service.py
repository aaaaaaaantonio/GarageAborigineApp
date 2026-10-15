import uuid
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.pay.calc import CENT
from app.modules.visits.lines_schemas import PartLineOut, VisitLinesOut, WorkLineOut
from app.modules.visits.models import Visit, VisitPartItem
from app.modules.visits.work_items_service import WorkItemService


def _money(value: Decimal) -> float:
    return float(value.quantize(CENT, rounding=ROUND_HALF_UP))


def _dec(value) -> Decimal:
    return Decimal(str(value))


class VisitLinesService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_lines(self, visit_id: uuid.UUID) -> VisitLinesOut:
        works = await WorkItemService(self.session).list_for_visit(visit_id)  # raises VisitNotFound
        visit = await self.session.get(Visit, visit_id)
        result = await self.session.execute(
            select(VisitPartItem).where(VisitPartItem.visit_id == visit_id).order_by(VisitPartItem.name, VisitPartItem.id)
        )
        parts_by_work: dict[uuid.UUID, list[PartLineOut]] = defaultdict(list)
        parts_total = Decimal("0")
        for p in result.scalars():
            amount = _dec(p.quantity) * _dec(p.unit_price)
            parts_total += amount
            parts_by_work[p.work_item_id].append(
                PartLineOut(id=p.id, work_item_id=p.work_item_id, name=p.name, quantity=p.quantity,
                            unit_price=_money(_dec(p.unit_price)), amount=_money(amount))
            )
        lines: list[WorkLineOut] = []
        works_total = Decimal("0")
        for w in works:
            amount = _dec(w.norm_hours) * _dec(w.hourly_rate)
            works_total += amount
            lines.append(
                WorkLineOut(
                    id=w.id, name=w.name, status=w.status, assigned_mechanic_name=w.assigned_mechanic_name,
                    approved_by_client=w.approved_by_client, norm_hours=float(w.norm_hours),
                    hourly_rate=_money(_dec(w.hourly_rate)), amount=_money(amount),
                    parts=parts_by_work.get(w.id, []),
                )
            )
        discount = _dec(visit.discount)
        return VisitLinesOut(
            works=lines,
            works_total=_money(works_total),
            parts_total=_money(parts_total),
            discount=_money(discount),
            total=_money(works_total + parts_total - discount),
        )
