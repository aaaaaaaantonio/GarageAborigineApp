import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import UserRole
from app.modules.settings.models import AppSetting
from app.modules.settings.schemas import MechanicPayOut, PayPatch, VisibilityOut, VisibilityPatch
from app.modules.users.audit import record_audit
from app.modules.users.models import User

VISIBILITY_DEFAULTS = {
    "mechanic_sees_prices": False,
    "mechanic_sees_client_name": False,
    "mechanic_sees_client_phone": False,
    "mechanic_sees_vin": False,
}
# Settings are not an entity with an id; the audit log needs one.
SETTINGS_AUDIT_ID = uuid.UUID(int=0)


class NotAMechanic(Exception):
    pass


def _pay_out(user: User) -> MechanicPayOut:
    return MechanicPayOut(
        user_id=user.id, full_name=user.full_name, pay_scheme=user.pay_scheme,
        pay_value=None if user.pay_value is None else float(user.pay_value),
    )


class SettingsService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def visibility(self) -> VisibilityOut:
        rows = await self.session.execute(select(AppSetting).where(AppSetting.key.in_(VISIBILITY_DEFAULTS)))
        stored = {row.key: bool(row.value) for row in rows.scalars()}
        return VisibilityOut(**(VISIBILITY_DEFAULTS | stored))

    async def update_visibility(self, patch: VisibilityPatch, acting_user: User) -> VisibilityOut:
        old = await self.visibility()
        changes = patch.model_dump(exclude_none=True)
        for key, value in changes.items():
            await self.session.merge(AppSetting(key=key, value=value, updated_by_user_id=acting_user.id))
        await self.session.flush()
        new = await self.visibility()
        await record_audit(
            self.session, user=acting_user, entity_type="settings", entity_id=SETTINGS_AUDIT_ID, action="update",
            old_value=old.model_dump(), new_value=new.model_dump(),
        )
        return new

    async def mechanic_pay(self) -> list[MechanicPayOut]:
        result = await self.session.execute(
            select(User).where(User.role == UserRole.MECHANIC, User.deleted_at.is_(None)).order_by(User.full_name, User.id)
        )
        return [_pay_out(user) for user in result.scalars()]

    async def set_pay(self, user_id: uuid.UUID, patch: PayPatch, acting_user: User) -> MechanicPayOut:
        user = await self.session.get(User, user_id)
        if user is None or user.role != UserRole.MECHANIC or user.deleted_at is not None:
            raise NotAMechanic()
        old = _pay_out(user)
        user.pay_scheme, user.pay_value = patch.pay_scheme, patch.pay_value
        await self.session.flush()
        await record_audit(
            self.session, user=acting_user, entity_type="user", entity_id=user.id, action="pay_changed",
            old_value=old.model_dump(mode="json", include={"pay_scheme", "pay_value"}),
            new_value=patch.model_dump(mode="json"),
        )
        return _pay_out(user)
