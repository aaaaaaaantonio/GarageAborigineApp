from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import UserRole
from app.modules.pay.calc import work_pay
from app.modules.users.models import User
from app.modules.visits.models import VisitWorkItem


async def snapshot_mechanic_pay(session: AsyncSession, items: list[VisitWorkItem]) -> None:
    """Fix each item's pay by its current assignee's scheme. Only mechanics are paid per work:
    an admin assignee, no assignee or no scheme leaves NULL."""
    for item in items:
        mechanic = await session.get(User, item.assigned_mechanic_id) if item.assigned_mechanic_id else None
        if mechanic is None or mechanic.role != UserRole.MECHANIC:
            item.mechanic_pay = None
        else:
            item.mechanic_pay = work_pay(item.norm_hours, item.hourly_rate, mechanic.pay_scheme, mechanic.pay_value)
