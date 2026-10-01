from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.enums import UserRole
from app.modules.users.audit import record_audit
from app.modules.users.models import User
from app.modules.users.repository import UserRepository
from app.modules.users.schemas import UserCreate


class UserService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = UserRepository(session)

    async def create_user(self, data: UserCreate, acting_user: User) -> User:
        user = User(
            role=data.role,
            full_name=data.full_name,
            telegram_id=data.telegram_id,
            phone=data.phone,
            branch_id=settings.default_branch_id,
        )
        await self.repo.create(user)
        await record_audit(
            self.session,
            user=acting_user,
            entity_type="user",
            entity_id=user.id,
            action="create",
            new_value={"role": user.role.value, "full_name": user.full_name},
        )
        return user

    async def list_users(self) -> list[User]:
        return await self.repo.list_active()

    async def list_mechanics(self) -> list[User]:
        return await self.repo.list_active_by_role(UserRole.MECHANIC)

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        return await self.repo.get_by_telegram_id(telegram_id)
