# CRM Backend (Этап 1) — план реализации

> **Для агентов-исполнителей:** ОБЯЗАТЕЛЬНЫЙ САБ-СКИЛЛ: используй superpowers:subagent-driven-development (рекомендуется) или superpowers:executing-plans для выполнения плана по задачам. Шаги отмечены чекбоксами (`- [ ]`) для отслеживания прогресса.

**Цель:** реализовать backend CRM автосервиса (модульный монолит на FastAPI) — модель данных, статусная FSM заезда, consent-сервис, поиск, генерация PDF заказ-наряда, уведомления, роли/аудит — так, чтобы Telegram-бот (следующий цикл) мог быть тонким HTTP-клиентом без собственной бизнес-логики.

**Архитектура:** модульный монолит, один процесс FastAPI. Каждый модуль в `app/modules/<name>/` содержит `models.py`, `schemas.py`, `repository.py`, `service.py`, `router.py`. Между модулями — только вызовы `service.py` друг друга, никогда `repository.py` напрямую. Роутеры не содержат бизнес-логики.

**Стек:** Python 3.12, FastAPI, SQLAlchemy 2.0 (async, `asyncpg`), Alembic, PostgreSQL 15+ с расширением `pg_trgm`, Pydantic v2 / `pydantic-settings`, Jinja2 + WeasyPrint (PDF), pytest + `pytest-asyncio` + `httpx.AsyncClient`.

**Спек:** `docs/superpowers/specs/2026-09-15-crm-backend-design.md` — план реализует этот документ целиком; при расхождении исполнитель ориентируется на спек, этот план — раскладка на задачи.

## Общие ограничения (из спека)

- Soft delete везде через `deleted_at` — физический `DELETE` запрещён во всех модулях.
- `branch_id` присутствует в `clients`, `visits`, `users` (не в `vehicles`/`work_catalog` — они не привязаны к филиалу). UI филиалов не делаем, поле просто заполняется текущим единственным branch на MVP.
- Бизнес-логика только в `service.py`. Роутер — валидация запроса (через Pydantic) + вызов сервиса + маппинг исключений в HTTP-коды.
- Никакой Telegram-специфики в backend-коде — бот в этом плане не участвует.
- PK — `UUID` (генерируется в приложении через `uuid4()`), чтобы не переделывать при переходе на мультифилиальность/распределённые сценарии.
- Авторизация на MVP: доверенный внутренний API, вызывающий сервис передаёт заголовок `X-User-Id` (UUID пользователя), backend подгружает `User` и проверяет роль через FastAPI-зависимость `require_role(*roles)`. Полноценный OAuth/JWT — вне рамок MVP, помечено как упрощение в Task 2.

---

## Файловая структура (итог после всех задач)

```
app/
  main.py
  core/
    config.py
    db.py
    models.py        # Base, TimestampMixin, SoftDeleteMixin, UUIDPkMixin
    enums.py          # все enum'ы модели данных
    phone.py           # нормализация телефона
    exceptions.py       # доменные исключения → HTTP-коды
  modules/
    users/{models,schemas,repository,service,router,auth,audit}.py
    clients/{models,schemas,repository,service,router}.py
    vehicles/{models,schemas,repository,service,router}.py
    catalog/{models,schemas,repository,service,router}.py
    visits/{models,schemas,repository,service,router,fsm}.py
    consent/{models,schemas,repository,service,router,tokens}.py
    search/{config,strategies,models,service,router}.py
    documents/{service,storage}.py
      templates/visit_order.html
    notifications/{interfaces,logging_sender}.py
alembic/
  env.py, versions/...
tests/
  conftest.py
  core/test_phone.py
  modules/<name>/test_*.py
docker-compose.yml       # postgres:15 с pg_trgm
pyproject.toml
.env.example
```

---

### Task 1: Каркас проекта — конфиг, БД, миксины, enum'ы, тестовая инфраструктура

**Files:**
- Create: `pyproject.toml`
- Create: `.env.example`
- Create: `docker-compose.yml`
- Create: `app/__init__.py`, `app/main.py`
- Create: `app/core/__init__.py`
- Create: `app/core/config.py`
- Create: `app/core/db.py`
- Create: `app/core/models.py`
- Create: `app/core/enums.py`
- Create: `alembic.ini`, `alembic/env.py`
- Test: `tests/conftest.py`
- Test: `tests/core/test_db.py`

**Interfaces:**
- Produces: `settings: Settings` (из `app.core.config`), `get_session() -> AsyncGenerator[AsyncSession, None]` (FastAPI-зависимость, `app.core.db`), `Base` (декларативная база), `TimestampMixin`, `SoftDeleteMixin`, `UUIDPkMixin` (из `app.core.models`), все enum'ы из `app.core.enums`: `ClientType`, `UserRole`, `VisitStatus`, `WorkItemStatus`, `PartAvailability`, `WorkCategory`, `ConsentMethod`, `ApprovedVia`.

- [ ] **Шаг 1: `docker-compose.yml` с Postgres**

```yaml
services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_USER: crm
      POSTGRES_PASSWORD: crm
      POSTGRES_DB: crm
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
volumes:
  pgdata:
```

Запусти: `docker compose up -d`. Затем создай тестовую БД:
`docker compose exec postgres psql -U crm -c "CREATE DATABASE crm_test;"`

- [ ] **Шаг 2: `pyproject.toml`**

```toml
[project]
name = "crm-backend"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "sqlalchemy>=2.0.35",
    "asyncpg>=0.30",
    "alembic>=1.13",
    "pydantic>=2.9",
    "pydantic-settings>=2.5",
    "jinja2>=3.1",
    "weasyprint>=62.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.3",
    "pytest-asyncio>=0.24",
    "httpx>=0.27",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
```

- [ ] **Шаг 3: `.env.example`**

```
DATABASE_URL=postgresql+asyncpg://crm:crm@localhost:5432/crm
TEST_DATABASE_URL=postgresql+asyncpg://crm:crm@localhost:5432/crm_test
SQL_ECHO=false
CONSENT_TOKEN_TTL_MINUTES=15
SEARCH_FUZZY_THRESHOLD=0.3
CATALOG_FUZZY_THRESHOLD=0.3
RECENT_VIEWS_LIMIT=10
FILE_STORAGE_ROOT=./storage
DEFAULT_BRANCH_ID=00000000-0000-0000-0000-000000000001
```

- [ ] **Шаг 4: `app/core/config.py`**

```python
from pydantic_settings import BaseSettings, SettingsConfigDict
from uuid import UUID


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://crm:crm@localhost:5432/crm"
    test_database_url: str = "postgresql+asyncpg://crm:crm@localhost:5432/crm_test"
    sql_echo: bool = False
    consent_token_ttl_minutes: int = 15
    search_fuzzy_threshold: float = 0.3
    catalog_fuzzy_threshold: float = 0.3
    recent_views_limit: int = 10
    file_storage_root: str = "./storage"
    default_branch_id: UUID = UUID("00000000-0000-0000-0000-000000000001")


settings = Settings()
```

- [ ] **Шаг 5: `app/core/models.py`**

```python
import uuid
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class UUIDPkMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SoftDeleteMixin:
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
```

- [ ] **Шаг 6: `app/core/enums.py`**

```python
import enum


class ClientType(str, enum.Enum):
    INDIVIDUAL = "individual"
    LEGAL = "legal"


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    MASTER = "master"
    MECHANIC = "mechanic"


class VisitStatus(str, enum.Enum):
    RECEIVED = "received"
    DIAGNOSTICS = "diagnostics"
    APPROVAL = "approval"
    IN_PROGRESS = "in_progress"
    WAITING_PARTS = "waiting_parts"
    READY = "ready"
    ISSUED = "issued"
    CANCELLED = "cancelled"


class WorkItemStatus(str, enum.Enum):
    NOT_READY = "not_ready"
    IN_PROGRESS = "in_progress"
    WAITING_PARTS = "waiting_parts"
    READY = "ready"


class WorkCategory(str, enum.Enum):
    DIAGNOSTICS = "diagnostics"
    MAINTENANCE = "maintenance"
    BODY = "body"
    ELECTRICAL = "electrical"
    CHASSIS = "chassis"
    OTHER = "other"


class PartAvailability(str, enum.Enum):
    IN_STOCK = "in_stock"
    ORDERED = "ordered"
    PENDING = "pending"


class ConsentMethod(str, enum.Enum):
    QR_ONSITE = "qr_onsite"
    PAPER = "paper"
    TELEGRAM_BOT_START = "telegram_bot_start"
    EMAIL_CONFIRMATION = "email_confirmation"
    SMS_OTP = "sms_otp"


class ApprovedVia(str, enum.Enum):
    CRM_STATUS = "crm_status"
    BOT = "bot"
```

- [ ] **Шаг 7: `app/core/db.py`**

```python
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

engine = create_async_engine(settings.database_url, echo=settings.sql_echo)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session
```

- [ ] **Шаг 8: `app/main.py` (минимальный каркас)**

```python
from fastapi import FastAPI

app = FastAPI(title="CRM Backend")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Шаг 9: Alembic init**

Run: `alembic init alembic`

В `alembic.ini` укажи `sqlalchemy.url` через env-переменную (заменить строку `sqlalchemy.url =` на пустую и читать в `env.py`). В `alembic/env.py` добавь:

```python
import asyncio
from app.core.config import settings
from app.core.models import Base
# ВАЖНО: импортировать все модели модулей здесь по мере их появления (Task 2+),
# иначе Alembic autogenerate их не увидит.

target_metadata = Base.metadata
config.set_main_option("sqlalchemy.url", settings.database_url)
```

(Остальной boilerplate `env.py` — стандартный async-шаблон Alembic, `run_migrations_online` через `asyncio.run`.)

- [ ] **Шаг 10: `tests/conftest.py` — тестовая БД + транзакционный rollback на тест**

```python
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.models import Base


@pytest_asyncio.fixture(scope="session")
async def engine():
    eng = create_async_engine(settings.test_database_url)
    async with eng.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine) -> AsyncSession:
    connection = await engine.connect()
    trans = await connection.begin()
    session_factory = async_sessionmaker(
        bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )
    async with session_factory() as s:
        yield s
    await trans.rollback()
    await connection.close()
```

- [ ] **Шаг 11: `tests/core/test_db.py` — проверка подключения и расширения**

```python
from sqlalchemy import text


async def test_pg_trgm_extension_available(session):
    result = await session.execute(
        text("SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm'")
    )
    assert result.scalar() == 1
```

- [ ] **Шаг 12: Запустить тест**

Run: `pytest tests/core/test_db.py -v`
Expected: PASS (требует поднятого `docker compose up -d` и созданной `crm_test`).

- [ ] **Шаг 13: Commit**

```bash
git add pyproject.toml .env.example docker-compose.yml alembic.ini alembic/ app/ tests/
git commit -m "chore: scaffold FastAPI backend, db session, core mixins and enums"
```

---

### Task 2: Пользователи, роли, RBAC-зависимость, audit_log

**Files:**
- Create: `app/modules/users/__init__.py`
- Create: `app/modules/users/models.py`
- Create: `app/modules/users/schemas.py`
- Create: `app/modules/users/repository.py`
- Create: `app/modules/users/service.py`
- Create: `app/modules/users/router.py`
- Create: `app/modules/users/auth.py`
- Create: `app/modules/users/audit.py`
- Test: `tests/modules/users/test_auth.py`
- Test: `tests/modules/users/test_audit.py`
- Test: `tests/modules/users/test_service.py`

**Interfaces:**
- Consumes: `Base`, `UUIDPkMixin`, `SoftDeleteMixin`, `TimestampMixin` (Task 1), `UserRole` (Task 1), `get_session` (Task 1).
- Produces: `User` ORM-модель (`id, role, full_name, telegram_id, phone, branch_id, deleted_at`); `get_current_user(x_user_id: UUID = Header(...), session: AsyncSession = Depends(get_session)) -> User`; `require_role(*roles: UserRole) -> Callable` (FastAPI-зависимость, райзит `403`); `record_audit(session, *, user: User, entity_type: str, entity_id: UUID, action: str, old_value: dict | None, new_value: dict | None) -> None`.

- [ ] **Шаг 1: `app/modules/users/models.py`**

```python
import uuid

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import UserRole
from app.core.models import Base, SoftDeleteMixin, UUIDPkMixin
from app.core.config import settings


class User(Base, UUIDPkMixin, SoftDeleteMixin):
    __tablename__ = "users"

    role: Mapped[UserRole] = mapped_column(nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    telegram_id: Mapped[int | None] = mapped_column(nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False, default=lambda: settings.default_branch_id
    )
```

- [ ] **Шаг 2: `app/modules/users/audit.py`**

```python
import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import String, JSON, DateTime, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, UUIDPkMixin
from app.modules.users.models import User


class AuditLog(Base, UUIDPkMixin):
    __tablename__ = "audit_log"

    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    old_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    new_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


async def record_audit(
    session: AsyncSession,
    *,
    user: User,
    entity_type: str,
    entity_id: uuid.UUID,
    action: str,
    old_value: dict | None = None,
    new_value: dict | None = None,
) -> None:
    session.add(
        AuditLog(
            user_id=user.id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            old_value=old_value,
            new_value=new_value,
        )
    )
    await session.flush()
```

- [ ] **Шаг 3: тест на audit — падает**

`tests/modules/users/test_audit.py`:

```python
import uuid

from app.modules.users.audit import record_audit, AuditLog
from app.modules.users.models import User
from app.core.enums import UserRole
from sqlalchemy import select


async def test_record_audit_writes_row(session):
    user = User(role=UserRole.ADMIN, full_name="Admin", branch_id=uuid.uuid4())
    session.add(user)
    await session.flush()

    entity_id = uuid.uuid4()
    await record_audit(
        session,
        user=user,
        entity_type="client",
        entity_id=entity_id,
        action="create",
        new_value={"full_name": "Иван"},
    )

    row = (await session.execute(select(AuditLog).where(AuditLog.entity_id == entity_id))).scalar_one()
    assert row.action == "create"
    assert row.new_value == {"full_name": "Иван"}
```

Run: `pytest tests/modules/users/test_audit.py -v`
Expected: FAIL (модуля ещё нет / таблицы нет в metadata до импорта — убедись, что `tests/conftest.py` импортирует `app.modules.users.models` и `app.modules.users.audit`, чтобы `Base.metadata` их видел; добавь `import app.modules.users.models  # noqa` и `import app.modules.users.audit  # noqa` в начало `tests/conftest.py`).

- [ ] **Шаг 4: Прогнать после реализации шагов 1–2**

Run: `pytest tests/modules/users/test_audit.py -v`
Expected: PASS

- [ ] **Шаг 5: `app/modules/users/auth.py` — RBAC-зависимость**

```python
import uuid
from collections.abc import Callable

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.enums import UserRole
from app.modules.users.models import User


async def get_current_user(
    x_user_id: uuid.UUID = Header(..., alias="X-User-Id"),
    session: AsyncSession = Depends(get_session),
) -> User:
    user = await session.get(User, x_user_id)
    if user is None or user.deleted_at is not None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown user")
    return user


def require_role(*roles: UserRole) -> Callable:
    async def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Role not permitted")
        return user

    return dependency
```

- [ ] **Шаг 6: тест RBAC — падает, затем проходит**

`tests/modules/users/test_auth.py`:

```python
import uuid

import pytest
from fastapi import FastAPI, Depends
from httpx import AsyncClient, ASGITransport

from app.core.db import get_session
from app.core.enums import UserRole
from app.modules.users.auth import require_role
from app.modules.users.models import User


@pytest.fixture
def app_with_protected_route(session):
    app = FastAPI()

    async def override_get_session():
        yield session

    app.dependency_overrides[get_session] = override_get_session

    @app.get("/admin-only")
    async def admin_only(user: User = Depends(require_role(UserRole.ADMIN))):
        return {"ok": True}

    return app


async def test_require_role_blocks_wrong_role(app_with_protected_route, session):
    mechanic = User(role=UserRole.MECHANIC, full_name="Вася", branch_id=uuid.uuid4())
    session.add(mechanic)
    await session.flush()

    transport = ASGITransport(app=app_with_protected_route)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/admin-only", headers={"X-User-Id": str(mechanic.id)})
    assert resp.status_code == 403


async def test_require_role_allows_correct_role(app_with_protected_route, session):
    admin = User(role=UserRole.ADMIN, full_name="Админ", branch_id=uuid.uuid4())
    session.add(admin)
    await session.flush()

    transport = ASGITransport(app=app_with_protected_route)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/admin-only", headers={"X-User-Id": str(admin.id)})
    assert resp.status_code == 200
```

Run: `pytest tests/modules/users/test_auth.py -v`
Expected: сначала FAIL (нет `auth.py`), после шага 5 — PASS.

- [ ] **Шаг 7: `app/modules/users/schemas.py`, `repository.py`, `service.py`, `router.py` — CRUD пользователей (только admin)**

`schemas.py`:

```python
import uuid

from pydantic import BaseModel

from app.core.enums import UserRole


class UserCreate(BaseModel):
    role: UserRole
    full_name: str
    telegram_id: int | None = None
    phone: str | None = None


class UserOut(BaseModel):
    id: uuid.UUID
    role: UserRole
    full_name: str
    telegram_id: int | None
    phone: str | None
    branch_id: uuid.UUID

    class Config:
        from_attributes = True
```

`repository.py`:

```python
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.users.models import User


class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, user: User) -> User:
        self.session.add(user)
        await self.session.flush()
        return user

    async def get(self, user_id: uuid.UUID) -> User | None:
        return await self.session.get(User, user_id)

    async def list_active(self) -> list[User]:
        result = await self.session.execute(select(User).where(User.deleted_at.is_(None)))
        return list(result.scalars())
```

`service.py`:

```python
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
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
```

`router.py`:

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.enums import UserRole
from app.modules.users.auth import require_role
from app.modules.users.models import User
from app.modules.users.schemas import UserCreate, UserOut
from app.modules.users.service import UserService

router = APIRouter(prefix="/users", tags=["users"])


@router.post("", response_model=UserOut, status_code=201)
async def create_user(
    data: UserCreate,
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_role(UserRole.ADMIN)),
):
    service = UserService(session)
    user = await service.create_user(data, acting_user)
    await session.commit()
    return user


@router.get("", response_model=list[UserOut])
async def list_users(
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_role(UserRole.ADMIN)),
):
    service = UserService(session)
    return await service.list_users()
```

- [ ] **Шаг 8: тест сервиса — падает, затем проходит**

`tests/modules/users/test_service.py`:

```python
import uuid

from app.modules.users.models import User
from app.core.enums import UserRole
from app.modules.users.schemas import UserCreate
from app.modules.users.service import UserService


async def test_create_user_writes_audit_row(session):
    admin = User(role=UserRole.ADMIN, full_name="Админ", branch_id=uuid.uuid4())
    session.add(admin)
    await session.flush()

    service = UserService(session)
    created = await service.create_user(
        UserCreate(role=UserRole.MECHANIC, full_name="Механик Петя"), acting_user=admin
    )

    assert created.id is not None
    assert created.role == UserRole.MECHANIC
```

Run: `pytest tests/modules/users/test_service.py -v`
Expected: FAIL до реализации шага 7, PASS после.

- [ ] **Шаг 9: подключить роутер в `app/main.py`**

```python
from app.modules.users.router import router as users_router

app.include_router(users_router)
```

- [ ] **Шаг 10: Alembic-миграция**

Run: `alembic revision --autogenerate -m "users and audit_log tables"`
Run: `alembic upgrade head`

- [ ] **Шаг 11: Commit**

```bash
git add app/modules/users tests/modules/users app/main.py alembic/versions
git commit -m "feat: users module with RBAC dependency and audit log"
```

---

### Task 3: Справочник клиентов — нормализация телефона, CRUD, история владения (модель, без vehicles)

**Files:**
- Create: `app/core/phone.py`
- Create: `app/modules/clients/{__init__.py,models.py,schemas.py,repository.py,service.py,router.py}`
- Test: `tests/core/test_phone.py`
- Test: `tests/modules/clients/test_service.py`

**Interfaces:**
- Consumes: `Base`, `UUIDPkMixin`, `TimestampMixin`, `SoftDeleteMixin` (Task 1), `ClientType` (Task 1), `require_role`, `get_current_user`, `record_audit` (Task 2).
- Produces: `normalize_phone(raw: str) -> str` (`app.core.phone`); `Client` ORM-модель; `ClientService.create_client(data, acting_user) -> Client`, `ClientService.get_by_phone(phone_raw) -> Client | None`, `ClientService.get(client_id) -> Client | None`.

- [ ] **Шаг 1: `app/core/phone.py`**

```python
import re


def normalize_phone(raw: str) -> str:
    """Приводит телефон к формату '7XXXXXXXXXX' (11 цифр, без +).
    '+7', '8', скобки/дефисы/пробелы — всё игнорируется, кроме цифр."""
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 11 and digits[0] == "8":
        digits = "7" + digits[1:]
    if len(digits) == 10:
        digits = "7" + digits
    return digits
```

- [ ] **Шаг 2: тест нормализации — падает**

`tests/core/test_phone.py`:

```python
import pytest

from app.core.phone import normalize_phone


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("+7 (999) 123-45-67", "79991234567"),
        ("89991234567", "79991234567"),
        ("9991234567", "79991234567"),
        ("7 999 123 45 67", "79991234567"),
    ],
)
def test_normalize_phone_variants_match(raw, expected):
    assert normalize_phone(raw) == expected
```

Run: `pytest tests/core/test_phone.py -v`
Expected: FAIL (файла нет), затем PASS после шага 1.

- [ ] **Шаг 3: `app/modules/clients/models.py`**

```python
import uuid

from sqlalchemy import String, JSON
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import ClientType
from app.core.config import settings
from app.core.models import Base, SoftDeleteMixin, TimestampMixin, UUIDPkMixin


class Client(Base, UUIDPkMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "clients"

    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone_normalized: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    phone_display: Mapped[str] = mapped_column(String(32), nullable=False)
    telegram_id: Mapped[int | None] = mapped_column(nullable=True)
    telegram_username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    client_type: Mapped[ClientType] = mapped_column(nullable=False, default=ClientType.INDIVIDUAL)
    legal_details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    branch_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False, default=lambda: settings.default_branch_id
    )
```

- [ ] **Шаг 4: `schemas.py`**

```python
import uuid

from pydantic import BaseModel

from app.core.enums import ClientType


class ClientCreate(BaseModel):
    full_name: str
    phone: str  # сырой ввод, нормализуется в сервисе
    client_type: ClientType = ClientType.INDIVIDUAL
    legal_details: dict | None = None
    telegram_id: int | None = None
    telegram_username: str | None = None


class ClientOut(BaseModel):
    id: uuid.UUID
    full_name: str
    phone_display: str
    client_type: ClientType

    class Config:
        from_attributes = True
```

- [ ] **Шаг 5: `repository.py`**

```python
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.clients.models import Client


class ClientRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, client: Client) -> Client:
        self.session.add(client)
        await self.session.flush()
        return client

    async def get(self, client_id: uuid.UUID) -> Client | None:
        return await self.session.get(Client, client_id)

    async def get_by_phone_normalized(self, phone_normalized: str) -> Client | None:
        result = await self.session.execute(
            select(Client).where(
                Client.phone_normalized == phone_normalized, Client.deleted_at.is_(None)
            )
        )
        return result.scalars().first()
```

- [ ] **Шаг 6: `service.py`**

```python
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.phone import normalize_phone
from app.modules.clients.models import Client
from app.modules.clients.repository import ClientRepository
from app.modules.clients.schemas import ClientCreate
from app.modules.users.audit import record_audit
from app.modules.users.models import User


class ClientService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = ClientRepository(session)

    async def create_client(self, data: ClientCreate, acting_user: User) -> Client:
        client = Client(
            full_name=data.full_name,
            phone_normalized=normalize_phone(data.phone),
            phone_display=data.phone,
            client_type=data.client_type,
            legal_details=data.legal_details,
            telegram_id=data.telegram_id,
            telegram_username=data.telegram_username,
        )
        await self.repo.create(client)
        await record_audit(
            self.session,
            user=acting_user,
            entity_type="client",
            entity_id=client.id,
            action="create",
            new_value={"full_name": client.full_name},
        )
        return client

    async def get(self, client_id) -> Client | None:
        return await self.repo.get(client_id)

    async def get_by_phone(self, phone_raw: str) -> Client | None:
        return await self.repo.get_by_phone_normalized(normalize_phone(phone_raw))
```

- [ ] **Шаг 7: `router.py`**

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.enums import UserRole
from app.modules.clients.schemas import ClientCreate, ClientOut
from app.modules.clients.service import ClientService
from app.modules.users.auth import require_role
from app.modules.users.models import User

router = APIRouter(prefix="/clients", tags=["clients"])


@router.post("", response_model=ClientOut, status_code=201)
async def create_client(
    data: ClientCreate,
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MASTER)),
):
    service = ClientService(session)
    client = await service.create_client(data, acting_user)
    await session.commit()
    return client


@router.get("/{client_id}", response_model=ClientOut)
async def get_client(
    client_id,
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MASTER)),
):
    service = ClientService(session)
    client = await service.get(client_id)
    if client is None:
        raise HTTPException(404, "Client not found")
    return client
```

- [ ] **Шаг 8: тест сервиса — падает, затем проходит**

`tests/modules/clients/test_service.py`:

```python
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
```

Run: `pytest tests/modules/clients/test_service.py -v`
Expected: FAIL до реализации шагов 3–6, PASS после.

- [ ] **Шаг 9: подключить роутер, добавить импорт моделей в `alembic/env.py` и `tests/conftest.py`, миграция**

```python
# app/main.py
from app.modules.clients.router import router as clients_router
app.include_router(clients_router)
```

Run: `alembic revision --autogenerate -m "clients table"`
Run: `alembic upgrade head`

- [ ] **Шаг 10: Commit**

```bash
git add app/core/phone.py app/modules/clients tests/core/test_phone.py tests/modules/clients app/main.py alembic/versions
git commit -m "feat: clients module with phone normalization"
```

---

### Task 4: Автомобили и история владения

**Files:**
- Create: `app/core/plate.py`
- Create: `app/modules/vehicles/{__init__.py,models.py,schemas.py,repository.py,service.py,router.py}`
- Test: `tests/core/test_plate.py`
- Test: `tests/modules/vehicles/test_service.py`

**Interfaces:**
- Consumes: `Client` (Task 3, для FK владельца), `record_audit`, `require_role` (Task 2).
- Produces: `normalize_plate(raw: str) -> str` (`app.core.plate` — верхний регистр, без пробелов/дефисов; переиспользуется модулем `search` в Task 11); `Vehicle`, `VehicleOwnership` ORM-модели; `VehicleService.create_vehicle(data, acting_user) -> Vehicle` (нормализует `plate_number` перед сохранением), `VehicleService.attach_owner(vehicle_id, client_id, acting_user) -> VehicleOwnership`, `VehicleService.get_owners(vehicle_id) -> list[VehicleOwnership]`, `VehicleService.update_mileage(vehicle_id, mileage: int) -> Vehicle` (используется модулем `visits` при приёме заезда — просто перезаписывает `mileage_current`, без собственной валидации "не меньше предыдущего": эта проверка — ответственность `visits.service`, см. Task 6).

- [ ] **Шаг 1: `app/core/plate.py`**

```python
import re


def normalize_plate(raw: str) -> str:
    """Верхний регистр, без пробелов/дефисов — для гос.номера."""
    return re.sub(r"[\s-]", "", raw).upper()
```

- [ ] **Шаг 2: тест нормализации — падает, затем проходит**

`tests/core/test_plate.py`:

```python
from app.core.plate import normalize_plate


def test_normalize_plate_strips_spaces_and_uppercases():
    assert normalize_plate("а 123 вс 77") == "А123ВС77"
    assert normalize_plate("а-123-вс-77") == "А123ВС77"
```

Run: `pytest tests/core/test_plate.py -v`
Expected: FAIL (файла нет), затем PASS после шага 1.

- [ ] **Шаг 3: `models.py`**

```python
import uuid
from datetime import date

from sqlalchemy import String, ForeignKey, Boolean, Date
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, SoftDeleteMixin, TimestampMixin, UUIDPkMixin


class Vehicle(Base, UUIDPkMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "vehicles"

    vin: Mapped[str] = mapped_column(String(17), nullable=False, unique=True, index=True)
    plate_number: Mapped[str] = mapped_column(String(16), nullable=False)
    make: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    modification: Mapped[str | None] = mapped_column(String(128), nullable=True)
    year: Mapped[int | None] = mapped_column(nullable=True)
    color: Mapped[str | None] = mapped_column(String(32), nullable=True)
    mileage_current: Mapped[int] = mapped_column(nullable=False, default=0)


class VehicleOwnership(Base, UUIDPkMixin):
    __tablename__ = "vehicle_ownership"

    vehicle_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("vehicles.id"), nullable=False
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("clients.id"), nullable=False
    )
    date_from: Mapped[date] = mapped_column(Date, nullable=False)
    date_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    show_history_before_ownership: Mapped[bool] = mapped_column(Boolean, default=False)
```

- [ ] **Шаг 4: `schemas.py`**

```python
import uuid
from datetime import date

from pydantic import BaseModel


class VehicleCreate(BaseModel):
    vin: str
    plate_number: str
    make: str
    model: str
    modification: str | None = None
    year: int | None = None
    color: str | None = None


class VehicleOut(BaseModel):
    id: uuid.UUID
    vin: str
    plate_number: str
    make: str
    model: str
    mileage_current: int

    class Config:
        from_attributes = True


class OwnershipCreate(BaseModel):
    client_id: uuid.UUID
    date_from: date
    show_history_before_ownership: bool = False
```

- [ ] **Шаг 5: `repository.py`**

```python
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.vehicles.models import Vehicle, VehicleOwnership


class VehicleRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, vehicle: Vehicle) -> Vehicle:
        self.session.add(vehicle)
        await self.session.flush()
        return vehicle

    async def get(self, vehicle_id: uuid.UUID) -> Vehicle | None:
        return await self.session.get(Vehicle, vehicle_id)

    async def get_by_vin(self, vin: str) -> Vehicle | None:
        result = await self.session.execute(select(Vehicle).where(Vehicle.vin == vin))
        return result.scalars().first()

    async def add_ownership(self, ownership: VehicleOwnership) -> VehicleOwnership:
        self.session.add(ownership)
        await self.session.flush()
        return ownership

    async def list_owners(self, vehicle_id: uuid.UUID) -> list[VehicleOwnership]:
        result = await self.session.execute(
            select(VehicleOwnership).where(VehicleOwnership.vehicle_id == vehicle_id)
        )
        return list(result.scalars())
```

- [ ] **Шаг 6: `service.py`**

```python
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.plate import normalize_plate
from app.modules.users.audit import record_audit
from app.modules.users.models import User
from app.modules.vehicles.models import Vehicle, VehicleOwnership
from app.modules.vehicles.repository import VehicleRepository
from app.modules.vehicles.schemas import OwnershipCreate, VehicleCreate


class VehicleService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = VehicleRepository(session)

    async def create_vehicle(self, data: VehicleCreate, acting_user: User) -> Vehicle:
        payload = data.model_dump()
        payload["plate_number"] = normalize_plate(payload["plate_number"])
        vehicle = Vehicle(**payload)
        await self.repo.create(vehicle)
        await record_audit(
            self.session,
            user=acting_user,
            entity_type="vehicle",
            entity_id=vehicle.id,
            action="create",
            new_value={"vin": vehicle.vin},
        )
        return vehicle

    async def get(self, vehicle_id: uuid.UUID) -> Vehicle | None:
        return await self.repo.get(vehicle_id)

    async def attach_owner(
        self, vehicle_id: uuid.UUID, data: OwnershipCreate, acting_user: User
    ) -> VehicleOwnership:
        ownership = VehicleOwnership(vehicle_id=vehicle_id, **data.model_dump())
        await self.repo.add_ownership(ownership)
        await record_audit(
            self.session,
            user=acting_user,
            entity_type="vehicle_ownership",
            entity_id=ownership.id,
            action="create",
            new_value={"vehicle_id": str(vehicle_id), "client_id": str(data.client_id)},
        )
        return ownership

    async def get_owners(self, vehicle_id: uuid.UUID) -> list[VehicleOwnership]:
        return await self.repo.list_owners(vehicle_id)

    async def update_mileage(self, vehicle_id: uuid.UUID, mileage: int) -> Vehicle:
        vehicle = await self.repo.get(vehicle_id)
        assert vehicle is not None
        vehicle.mileage_current = mileage
        await self.session.flush()
        return vehicle
```

- [ ] **Шаг 7: `router.py`**

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.enums import UserRole
from app.modules.users.auth import require_role
from app.modules.users.models import User
from app.modules.vehicles.schemas import OwnershipCreate, VehicleCreate, VehicleOut
from app.modules.vehicles.service import VehicleService

router = APIRouter(prefix="/vehicles", tags=["vehicles"])


@router.post("", response_model=VehicleOut, status_code=201)
async def create_vehicle(
    data: VehicleCreate,
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MASTER)),
):
    service = VehicleService(session)
    vehicle = await service.create_vehicle(data, acting_user)
    await session.commit()
    return vehicle


@router.get("/{vehicle_id}", response_model=VehicleOut)
async def get_vehicle(
    vehicle_id,
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MASTER)),
):
    service = VehicleService(session)
    vehicle = await service.get(vehicle_id)
    if vehicle is None:
        raise HTTPException(404, "Vehicle not found")
    return vehicle


@router.post("/{vehicle_id}/owners", status_code=201)
async def attach_owner(
    vehicle_id,
    data: OwnershipCreate,
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MASTER)),
):
    service = VehicleService(session)
    ownership = await service.attach_owner(vehicle_id, data, acting_user)
    await session.commit()
    return {"id": str(ownership.id)}
```

- [ ] **Шаг 8: тест — падает, затем проходит**

`tests/modules/vehicles/test_service.py`:

```python
import uuid
from datetime import date

from app.core.enums import UserRole
from app.modules.clients.schemas import ClientCreate
from app.modules.clients.service import ClientService
from app.modules.users.models import User
from app.modules.vehicles.schemas import OwnershipCreate, VehicleCreate
from app.modules.vehicles.service import VehicleService


async def test_attach_owner_and_list_owners(session):
    admin = User(role=UserRole.ADMIN, full_name="Админ", branch_id=uuid.uuid4())
    session.add(admin)
    await session.flush()

    client = await ClientService(session).create_client(
        ClientCreate(full_name="Иван", phone="79991234567"), admin
    )
    vehicle_service = VehicleService(session)
    vehicle = await vehicle_service.create_vehicle(
        VehicleCreate(vin="X" * 17, plate_number="А123ВС77", make="Toyota", model="Camry"),
        admin,
    )

    await vehicle_service.attach_owner(
        vehicle.id, OwnershipCreate(client_id=client.id, date_from=date(2024, 1, 1)), admin
    )

    owners = await vehicle_service.get_owners(vehicle.id)
    assert len(owners) == 1
    assert owners[0].client_id == client.id
```

Run: `pytest tests/modules/vehicles/test_service.py -v`
Expected: FAIL до реализации шагов 1–5, PASS после.

- [ ] **Шаг 9: подключить роутер, миграция**

```python
# app/main.py
from app.modules.vehicles.router import router as vehicles_router
app.include_router(vehicles_router)
```

Run: `alembic revision --autogenerate -m "vehicles and vehicle_ownership tables"`
Run: `alembic upgrade head`

- [ ] **Шаг 10: Commit**

```bash
git add app/modules/vehicles tests/modules/vehicles app/main.py alembic/versions
git commit -m "feat: vehicles module with ownership history"
```

---

### Task 5: Справочник работ (WorkCatalog) с fuzzy-подсказками

**Files:**
- Create: `app/modules/catalog/{__init__.py,models.py,schemas.py,repository.py,service.py,router.py}`
- Test: `tests/modules/catalog/test_service.py`

**Interfaces:**
- Consumes: `record_audit`, `require_role` (Task 2), `settings.catalog_fuzzy_threshold` (Task 1).
- Produces: `WorkCatalog` ORM-модель; `CatalogService.create_item(data, acting_user) -> WorkCatalog`, `CatalogService.suggest(text: str) -> list[WorkCatalog]` (top-3 по `similarity(name, text) > threshold`, убывание).

- [ ] **Шаг 1: `models.py`**

```python
import uuid

from sqlalchemy import String, ForeignKey, Numeric
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import WorkCategory
from app.core.models import Base, SoftDeleteMixin, TimestampMixin, UUIDPkMixin


class WorkCatalog(Base, UUIDPkMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "work_catalog"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[WorkCategory] = mapped_column(nullable=False)
    default_norm_hours: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
```

- [ ] **Шаг 2: `schemas.py`**

```python
import uuid

from pydantic import BaseModel

from app.core.enums import WorkCategory


class WorkCatalogCreate(BaseModel):
    name: str
    category: WorkCategory
    default_norm_hours: float


class WorkCatalogOut(BaseModel):
    id: uuid.UUID
    name: str
    category: WorkCategory
    default_norm_hours: float

    class Config:
        from_attributes = True
```

- [ ] **Шаг 3: `repository.py`**

```python
import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.catalog.models import WorkCatalog


class CatalogRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, item: WorkCatalog) -> WorkCatalog:
        self.session.add(item)
        await self.session.flush()
        return item

    async def suggest(self, query: str, threshold: float, limit: int = 3) -> list[WorkCatalog]:
        result = await self.session.execute(
            select(WorkCatalog)
            .where(
                WorkCatalog.deleted_at.is_(None),
                text("similarity(name, :q) > :threshold"),
            )
            .params(q=query, threshold=threshold)
            .order_by(text("similarity(name, :q) DESC"))
            .params(q=query)
            .limit(limit)
        )
        return list(result.scalars())
```

- [ ] **Шаг 4: `service.py`**

```python
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.modules.catalog.models import WorkCatalog
from app.modules.catalog.repository import CatalogRepository
from app.modules.catalog.schemas import WorkCatalogCreate
from app.modules.users.audit import record_audit
from app.modules.users.models import User


class CatalogService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = CatalogRepository(session)

    async def create_item(self, data: WorkCatalogCreate, acting_user: User) -> WorkCatalog:
        item = WorkCatalog(
            name=data.name,
            category=data.category,
            default_norm_hours=data.default_norm_hours,
            created_by_user_id=acting_user.id,
        )
        await self.repo.create(item)
        await record_audit(
            self.session,
            user=acting_user,
            entity_type="work_catalog",
            entity_id=item.id,
            action="create",
            new_value={"name": item.name},
        )
        return item

    async def suggest(self, query: str) -> list[WorkCatalog]:
        return await self.repo.suggest(query, settings.catalog_fuzzy_threshold)
```

- [ ] **Шаг 5: `router.py`**

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.enums import UserRole
from app.modules.catalog.schemas import WorkCatalogCreate, WorkCatalogOut
from app.modules.catalog.service import CatalogService
from app.modules.users.auth import require_role
from app.modules.users.models import User

router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.post("", response_model=WorkCatalogOut, status_code=201)
async def create_item(
    data: WorkCatalogCreate,
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MASTER)),
):
    service = CatalogService(session)
    item = await service.create_item(data, acting_user)
    await session.commit()
    return item


@router.get("/suggest", response_model=list[WorkCatalogOut])
async def suggest(
    text: str,
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MASTER)),
):
    service = CatalogService(session)
    return await service.suggest(text)
```

- [ ] **Шаг 6: тест fuzzy-подсказки — падает, затем проходит**

`tests/modules/catalog/test_service.py`:

```python
import uuid

from app.core.enums import UserRole, WorkCategory
from app.modules.catalog.schemas import WorkCatalogCreate
from app.modules.catalog.service import CatalogService
from app.modules.users.models import User


async def test_suggest_finds_similar_name_despite_typo(session):
    admin = User(role=UserRole.ADMIN, full_name="Админ", branch_id=uuid.uuid4())
    session.add(admin)
    await session.flush()

    service = CatalogService(session)
    await service.create_item(
        WorkCatalogCreate(name="Замена масла", category=WorkCategory.MAINTENANCE, default_norm_hours=1.0),
        admin,
    )

    suggestions = await service.suggest("замена масло")
    assert len(suggestions) == 1
    assert suggestions[0].name == "Замена масла"


async def test_suggest_returns_empty_for_unrelated_text(session):
    admin = User(role=UserRole.ADMIN, full_name="Админ", branch_id=uuid.uuid4())
    session.add(admin)
    await session.flush()

    service = CatalogService(session)
    await service.create_item(
        WorkCatalogCreate(name="Замена масла", category=WorkCategory.MAINTENANCE, default_norm_hours=1.0),
        admin,
    )

    suggestions = await service.suggest("развал схождение")
    assert suggestions == []
```

Run: `pytest tests/modules/catalog/test_service.py -v`
Expected: FAIL до реализации шагов 1–5, PASS после.

- [ ] **Шаг 7: подключить роутер, миграция**

```python
# app/main.py
from app.modules.catalog.router import router as catalog_router
app.include_router(catalog_router)
```

Run: `alembic revision --autogenerate -m "work_catalog table"`
Run: `alembic upgrade head`

- [ ] **Шаг 8: Commit**

```bash
git add app/modules/catalog tests/modules/catalog app/main.py alembic/versions
git commit -m "feat: work catalog module with pg_trgm fuzzy suggest"
```

---

### Task 6: Заезд (Visit) — создание, валидация пробега

**Files:**
- Create: `app/modules/visits/{__init__.py,models.py,schemas.py,repository.py,service.py,router.py}`
- Test: `tests/modules/visits/test_intake.py`

**Interfaces:**
- Consumes: `Client`, `Vehicle` (Tasks 3–4), `VehicleService.update_mileage` (Task 4), `record_audit`, `require_role` (Task 2).
- Produces: `Visit` ORM-модель (поле `document_url: str | None` включено уже здесь — используется в Task 12); `VisitService.create_visit(data, acting_user) -> Visit` (валидирует пробег: если `mileage_at_intake < vehicle.mileage_current` и `mileage_manually_confirmed` не передан как `True` — `409 Conflict`; иначе создаёт заезд в статусе `RECEIVED` и обновляет `vehicle.mileage_current`).

- [ ] **Шаг 1: `models.py`**

```python
import uuid

from sqlalchemy import String, ForeignKey, Numeric, Boolean, JSON
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import settings
from app.core.enums import VisitStatus
from app.core.models import Base, SoftDeleteMixin, TimestampMixin, UUIDPkMixin


class Visit(Base, UUIDPkMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "visits"

    branch_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False, default=lambda: settings.default_branch_id
    )
    client_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    vehicle_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("vehicles.id"), nullable=False)
    planned_ready_at: Mapped[object | None] = mapped_column(nullable=True)
    mileage_at_intake: Mapped[int] = mapped_column(nullable=False)
    mileage_manually_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[VisitStatus] = mapped_column(nullable=False, default=VisitStatus.RECEIVED)
    assigned_master_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    complaint_text: Mapped[str | None] = mapped_column(String, nullable=True)
    intake_photos: Mapped[list | None] = mapped_column(JSON, nullable=True)
    total_amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    discount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    cancelled_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    document_url: Mapped[str | None] = mapped_column(String, nullable=True)
```

- [ ] **Шаг 2: `schemas.py`**

```python
import uuid

from pydantic import BaseModel

from app.core.enums import VisitStatus


class VisitCreate(BaseModel):
    client_id: uuid.UUID
    vehicle_id: uuid.UUID
    assigned_master_id: uuid.UUID
    mileage_at_intake: int
    mileage_manually_confirmed: bool = False
    complaint_text: str | None = None
    intake_photos: list[str] | None = None


class VisitOut(BaseModel):
    id: uuid.UUID
    status: VisitStatus
    mileage_at_intake: int
    total_amount: float

    class Config:
        from_attributes = True
```

- [ ] **Шаг 3: `repository.py`**

```python
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.visits.models import Visit


class VisitRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, visit: Visit) -> Visit:
        self.session.add(visit)
        await self.session.flush()
        return visit

    async def get(self, visit_id: uuid.UUID) -> Visit | None:
        return await self.session.get(Visit, visit_id)
```

- [ ] **Шаг 4: доменное исключение**

`app/core/exceptions.py`:

```python
class MileageRollbackNotConfirmed(Exception):
    """Пробег при приёме меньше последнего зафиксированного, а флаг ручного
    подтверждения не установлен."""
```

- [ ] **Шаг 5: `service.py`**

```python
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import VisitStatus
from app.core.exceptions import MileageRollbackNotConfirmed
from app.modules.users.audit import record_audit
from app.modules.users.models import User
from app.modules.vehicles.service import VehicleService
from app.modules.visits.models import Visit
from app.modules.visits.repository import VisitRepository
from app.modules.visits.schemas import VisitCreate


class VisitService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = VisitRepository(session)
        self.vehicle_service = VehicleService(session)

    async def create_visit(self, data: VisitCreate, acting_user: User) -> Visit:
        vehicle = await self.vehicle_service.get(data.vehicle_id)
        assert vehicle is not None
        if data.mileage_at_intake < vehicle.mileage_current and not data.mileage_manually_confirmed:
            raise MileageRollbackNotConfirmed()

        visit = Visit(
            client_id=data.client_id,
            vehicle_id=data.vehicle_id,
            assigned_master_id=data.assigned_master_id,
            mileage_at_intake=data.mileage_at_intake,
            mileage_manually_confirmed=data.mileage_manually_confirmed,
            complaint_text=data.complaint_text,
            intake_photos=data.intake_photos,
            status=VisitStatus.RECEIVED,
        )
        await self.repo.create(visit)
        await self.vehicle_service.update_mileage(data.vehicle_id, data.mileage_at_intake)
        await record_audit(
            self.session,
            user=acting_user,
            entity_type="visit",
            entity_id=visit.id,
            action="create",
            new_value={"status": visit.status.value},
        )
        return visit

    async def get(self, visit_id) -> Visit | None:
        return await self.repo.get(visit_id)
```

- [ ] **Шаг 6: `router.py`**

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.enums import UserRole
from app.core.exceptions import MileageRollbackNotConfirmed
from app.modules.users.auth import require_role
from app.modules.users.models import User
from app.modules.visits.schemas import VisitCreate, VisitOut
from app.modules.visits.service import VisitService

router = APIRouter(prefix="/visits", tags=["visits"])


@router.post("", response_model=VisitOut, status_code=201)
async def create_visit(
    data: VisitCreate,
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MASTER)),
):
    service = VisitService(session)
    try:
        visit = await service.create_visit(data, acting_user)
    except MileageRollbackNotConfirmed:
        raise HTTPException(
            409, "Пробег меньше последнего зафиксированного, требуется mileage_manually_confirmed=true"
        )
    await session.commit()
    return visit


@router.get("/{visit_id}", response_model=VisitOut)
async def get_visit(
    visit_id,
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MASTER)),
):
    service = VisitService(session)
    visit = await service.get(visit_id)
    if visit is None:
        raise HTTPException(404, "Visit not found")
    return visit
```

- [ ] **Шаг 7: тест валидации пробега — падает, затем проходит**

`tests/modules/visits/test_intake.py`:

```python
import uuid
from datetime import date

import pytest

from app.core.enums import UserRole
from app.core.exceptions import MileageRollbackNotConfirmed
from app.modules.clients.schemas import ClientCreate
from app.modules.clients.service import ClientService
from app.modules.users.models import User
from app.modules.vehicles.schemas import VehicleCreate
from app.modules.vehicles.service import VehicleService
from app.modules.visits.schemas import VisitCreate
from app.modules.visits.service import VisitService


async def _setup(session):
    admin = User(role=UserRole.ADMIN, full_name="Админ", branch_id=uuid.uuid4())
    session.add(admin)
    await session.flush()
    client = await ClientService(session).create_client(
        ClientCreate(full_name="Иван", phone="79991234567"), admin
    )
    vehicle = await VehicleService(session).create_vehicle(
        VehicleCreate(vin="X" * 17, plate_number="А123ВС77", make="Toyota", model="Camry"),
        admin,
    )
    await VehicleService(session).update_mileage(vehicle.id, 50_000)
    return admin, client, vehicle


async def test_lower_mileage_without_confirmation_rejected(session):
    admin, client, vehicle = await _setup(session)

    with pytest.raises(MileageRollbackNotConfirmed):
        await VisitService(session).create_visit(
            VisitCreate(
                client_id=client.id,
                vehicle_id=vehicle.id,
                assigned_master_id=admin.id,
                mileage_at_intake=40_000,
            ),
            admin,
        )


async def test_lower_mileage_with_confirmation_accepted(session):
    admin, client, vehicle = await _setup(session)

    visit = await VisitService(session).create_visit(
        VisitCreate(
            client_id=client.id,
            vehicle_id=vehicle.id,
            assigned_master_id=admin.id,
            mileage_at_intake=40_000,
            mileage_manually_confirmed=True,
        ),
        admin,
    )
    assert visit.mileage_manually_confirmed is True
```

Run: `pytest tests/modules/visits/test_intake.py -v`
Expected: FAIL до реализации шагов 1–6, PASS после.

- [ ] **Шаг 8: подключить роутер, миграция**

```python
# app/main.py
from app.modules.visits.router import router as visits_router
app.include_router(visits_router)
```

Run: `alembic revision --autogenerate -m "visits table"`
Run: `alembic upgrade head`

- [ ] **Шаг 9: Commit**

```bash
git add app/modules/visits tests/modules/visits app/core/exceptions.py app/main.py alembic/versions
git commit -m "feat: visit intake with mileage rollback validation"
```

---

### Task 7: Статусная FSM заезда + visit_status_log

**Files:**
- Modify: `app/modules/visits/models.py` (добавить `VisitStatusLog`)
- Create: `app/modules/visits/fsm.py`
- Modify: `app/modules/visits/service.py` (добавить `change_status`)
- Modify: `app/modules/visits/router.py` (добавить `PATCH /visits/{id}/status`)
- Modify: `app/modules/visits/schemas.py` (добавить `VisitStatusChange`)
- Test: `tests/modules/visits/test_status_fsm.py`

**Interfaces:**
- Consumes: `Visit`, `VisitStatus` (Task 6/1).
- Produces: `VisitStatusLog` ORM-модель; `ALLOWED_TRANSITIONS: dict[VisitStatus, set[VisitStatus]]` (`app.modules.visits.fsm`); `VisitService.change_status(visit_id, new_status, acting_user, reason=None) -> Visit` (райзит `InvalidTransition`, `CancelReasonRequired`, `NotAllWorkItemsReady`).

- [ ] **Шаг 1: `app/modules/visits/fsm.py`**

```python
from app.core.enums import VisitStatus

ALLOWED_TRANSITIONS: dict[VisitStatus, set[VisitStatus]] = {
    VisitStatus.RECEIVED: {VisitStatus.DIAGNOSTICS, VisitStatus.CANCELLED},
    VisitStatus.DIAGNOSTICS: {VisitStatus.APPROVAL, VisitStatus.CANCELLED},
    VisitStatus.APPROVAL: {VisitStatus.IN_PROGRESS, VisitStatus.CANCELLED},
    VisitStatus.IN_PROGRESS: {VisitStatus.WAITING_PARTS, VisitStatus.READY, VisitStatus.CANCELLED},
    VisitStatus.WAITING_PARTS: {VisitStatus.IN_PROGRESS, VisitStatus.CANCELLED},
    VisitStatus.READY: {VisitStatus.ISSUED, VisitStatus.CANCELLED},
    VisitStatus.ISSUED: set(),
    VisitStatus.CANCELLED: set(),
}
```

- [ ] **Шаг 2: доменные исключения**

Добавить в `app/core/exceptions.py`:

```python
class InvalidTransition(Exception):
    """Переход между статусами заезда не разрешён FSM."""


class CancelReasonRequired(Exception):
    """Отмена заезда требует непустой причины."""


class NotAllWorkItemsReady(Exception):
    """Переход в 'Готов' требует, чтобы все работы были в статусе 'ready'."""
```

- [ ] **Шаг 3: `VisitStatusLog` в `models.py` (добавить в конец файла)**

```python
class VisitStatusLog(Base, UUIDPkMixin):
    __tablename__ = "visit_status_log"

    visit_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("visits.id"), nullable=False)
    from_status: Mapped[VisitStatus | None] = mapped_column(nullable=True)
    to_status: Mapped[VisitStatus] = mapped_column(nullable=False)
    changed_by_user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    reason: Mapped[str | None] = mapped_column(String, nullable=True)
```

(Добавить недостающие импорты `func`, `datetime`, `DateTime` в верх `models.py`, если их там ещё нет.)

- [ ] **Шаг 4: `VisitStatusChange` в `schemas.py`**

```python
class VisitStatusChange(BaseModel):
    new_status: VisitStatus
    reason: str | None = None
```

- [ ] **Шаг 5: `change_status` в `service.py`**

Добавить импорт `VisitWorkItem`, `WorkItemStatus`, `select`, исключений и `VisitStatusLog`, затем метод:

```python
    async def change_status(
        self, visit_id, new_status: VisitStatus, acting_user: User, reason: str | None = None
    ) -> Visit:
        visit = await self.repo.get(visit_id)
        assert visit is not None

        if new_status not in ALLOWED_TRANSITIONS[visit.status]:
            raise InvalidTransition()

        if new_status == VisitStatus.CANCELLED and not reason:
            raise CancelReasonRequired()

        if new_status == VisitStatus.READY:
            result = await self.session.execute(
                select(VisitWorkItem).where(VisitWorkItem.visit_id == visit_id)
            )
            items = list(result.scalars())
            if any(i.status != WorkItemStatus.READY for i in items):
                raise NotAllWorkItemsReady()

        old_status = visit.status
        visit.status = new_status
        if new_status == VisitStatus.CANCELLED:
            visit.cancelled_reason = reason

        self.session.add(
            VisitStatusLog(
                visit_id=visit.id,
                from_status=old_status,
                to_status=new_status,
                changed_by_user_id=acting_user.id,
                reason=reason,
            )
        )
        await self.session.flush()
        return visit
```

- [ ] **Шаг 6: эндпоинт в `router.py`**

```python
@router.patch("/{visit_id}/status", response_model=VisitOut)
async def change_status(
    visit_id,
    data: VisitStatusChange,
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MASTER)),
):
    service = VisitService(session)
    try:
        visit = await service.change_status(visit_id, data.new_status, acting_user, data.reason)
    except InvalidTransition:
        raise HTTPException(409, "Переход между статусами не разрешён")
    except CancelReasonRequired:
        raise HTTPException(422, "Причина отмены обязательна")
    except NotAllWorkItemsReady:
        raise HTTPException(409, "Не все работы в статусе 'готово'")
    await session.commit()
    return visit
```

(Добавить соответствующие импорты исключений в `router.py`.)

- [ ] **Шаг 7: тесты FSM — падают, затем проходят**

`tests/modules/visits/test_status_fsm.py`:

```python
import uuid

import pytest

from app.core.enums import UserRole, VisitStatus, WorkCategory
from app.core.exceptions import CancelReasonRequired, InvalidTransition, NotAllWorkItemsReady
from app.modules.clients.schemas import ClientCreate
from app.modules.clients.service import ClientService
from app.modules.users.models import User
from app.modules.vehicles.schemas import VehicleCreate
from app.modules.vehicles.service import VehicleService
from app.modules.visits.schemas import VisitCreate
from app.modules.visits.service import VisitService


async def _create_visit(session):
    admin = User(role=UserRole.ADMIN, full_name="Админ", branch_id=uuid.uuid4())
    session.add(admin)
    await session.flush()
    client = await ClientService(session).create_client(
        ClientCreate(full_name="Иван", phone="79991234567"), admin
    )
    vehicle = await VehicleService(session).create_vehicle(
        VehicleCreate(vin="X" * 17, plate_number="А123", make="Toyota", model="Camry"), admin
    )
    visit = await VisitService(session).create_visit(
        VisitCreate(client_id=client.id, vehicle_id=vehicle.id, assigned_master_id=admin.id, mileage_at_intake=1000),
        admin,
    )
    return admin, visit


async def test_valid_transition_logs_status_change(session):
    admin, visit = await _create_visit(session)
    updated = await VisitService(session).change_status(visit.id, VisitStatus.DIAGNOSTICS, admin)
    assert updated.status == VisitStatus.DIAGNOSTICS


async def test_invalid_transition_rejected(session):
    admin, visit = await _create_visit(session)
    with pytest.raises(InvalidTransition):
        await VisitService(session).change_status(visit.id, VisitStatus.READY, admin)


async def test_cancel_without_reason_rejected(session):
    admin, visit = await _create_visit(session)
    with pytest.raises(CancelReasonRequired):
        await VisitService(session).change_status(visit.id, VisitStatus.CANCELLED, admin, reason=None)


async def test_ready_blocked_until_all_work_items_ready(session):
    admin, visit = await _create_visit(session)
    for status in (VisitStatus.DIAGNOSTICS, VisitStatus.APPROVAL, VisitStatus.IN_PROGRESS):
        visit = await VisitService(session).change_status(visit.id, status, admin)

    with pytest.raises(NotAllWorkItemsReady):
        await VisitService(session).change_status(visit.id, VisitStatus.READY, admin)
```

Run: `pytest tests/modules/visits/test_status_fsm.py -v`
Expected: FAIL до реализации шагов 1–6, PASS после.

- [ ] **Шаг 8: миграция**

Run: `alembic revision --autogenerate -m "visit_status_log table"`
Run: `alembic upgrade head`

- [ ] **Шаг 9: Commit**

```bash
git add app/modules/visits tests/modules/visits/test_status_fsm.py app/core/exceptions.py alembic/versions
git commit -m "feat: visit status FSM with append-only status log"
```

---

### Task 8: Работы в заезде (VisitWorkItem)

**Files:**
- Create: `app/modules/visits/work_items_schemas.py`
- Modify: `app/modules/visits/models.py` (добавить `VisitWorkItem`)
- Create: `app/modules/visits/work_items_service.py`
- Create: `app/modules/visits/work_items_router.py`
- Test: `tests/modules/visits/test_work_items.py`

**Interfaces:**
- Consumes: `Visit`, `WorkItemStatus`, `ApprovedVia`, `WorkCategory` (Tasks 1/6), `WorkCatalog` (Task 5).
- Produces: `VisitWorkItem` ORM-модель; `WorkItemService.add_item(visit_id, data, acting_user) -> VisitWorkItem`, `WorkItemService.update_status(item_id, new_status, acting_user) -> VisitWorkItem` (механику разрешено менять только назначенные ему позиции — иначе `403`), `WorkItemService.approve(item_id, acting_user) -> VisitWorkItem` (ставит `approved_by_client=True`, `approved_at=now()`, `approved_via=CRM_STATUS`).

- [ ] **Шаг 1: `VisitWorkItem` в `models.py` (добавить в конец)**

```python
import uuid
from datetime import datetime

from app.core.enums import ApprovedVia, WorkCategory, WorkItemStatus


class VisitWorkItem(Base, UUIDPkMixin):
    __tablename__ = "visit_work_items"

    visit_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("visits.id"), nullable=False)
    catalog_item_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("work_catalog.id"), nullable=True
    )
    free_text_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    category: Mapped[WorkCategory] = mapped_column(nullable=False)
    norm_hours: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    hourly_rate: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    status: Mapped[WorkItemStatus] = mapped_column(nullable=False)
    assigned_mechanic_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    comment: Mapped[str | None] = mapped_column(String, nullable=True)
    is_extra_work: Mapped[bool] = mapped_column(Boolean, default=False)
    approved_by_client: Mapped[bool] = mapped_column(Boolean, default=False)
    approved_at: Mapped[datetime | None] = mapped_column(nullable=True)
    approved_via: Mapped[ApprovedVia | None] = mapped_column(nullable=True)
    progress_photos: Mapped[list | None] = mapped_column(JSON, nullable=True)
```

(Импорты `uuid`, `datetime`, enum'ов добавляются в верх `app/modules/visits/models.py`, если их там ещё нет — файл уже содержит часть этих импортов после Task 6.)

- [ ] **Шаг 2: доменное исключение**

Добавить в `app/core/exceptions.py`:

```python
class NotAssignedMechanic(Exception):
    """Механик пытается изменить статус работы, назначенной не на него."""


class MissingWorkNameSource(Exception):
    """Ни catalog_item_id, ни free_text_name не указаны."""
```

- [ ] **Шаг 3: `work_items_schemas.py`**

```python
import uuid

from pydantic import BaseModel, model_validator

from app.core.enums import WorkCategory, WorkItemStatus


class WorkItemCreate(BaseModel):
    catalog_item_id: uuid.UUID | None = None
    free_text_name: str | None = None
    category: WorkCategory
    norm_hours: float
    hourly_rate: float
    assigned_mechanic_id: uuid.UUID | None = None
    is_extra_work: bool = False
    comment: str | None = None

    @model_validator(mode="after")
    def check_name_source(self):
        if bool(self.catalog_item_id) == bool(self.free_text_name):
            raise ValueError("Укажите ровно одно: catalog_item_id или free_text_name")
        return self


class WorkItemStatusChange(BaseModel):
    new_status: WorkItemStatus


class WorkItemOut(BaseModel):
    id: uuid.UUID
    status: WorkItemStatus
    approved_by_client: bool

    class Config:
        from_attributes = True
```

- [ ] **Шаг 4: `work_items_service.py`**

```python
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ApprovedVia, WorkItemStatus
from app.core.exceptions import NotAssignedMechanic
from app.modules.users.audit import record_audit
from app.modules.users.models import User
from app.modules.visits.models import VisitWorkItem
from app.modules.visits.work_items_schemas import WorkItemCreate


class WorkItemService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add_item(self, visit_id: uuid.UUID, data: WorkItemCreate, acting_user: User) -> VisitWorkItem:
        item = VisitWorkItem(
            visit_id=visit_id,
            catalog_item_id=data.catalog_item_id,
            free_text_name=data.free_text_name,
            category=data.category,
            norm_hours=data.norm_hours,
            hourly_rate=data.hourly_rate,
            assigned_mechanic_id=data.assigned_mechanic_id,
            is_extra_work=data.is_extra_work,
            comment=data.comment,
            status=WorkItemStatus.NOT_READY,
        )
        self.session.add(item)
        await self.session.flush()
        await record_audit(
            self.session,
            user=acting_user,
            entity_type="visit_work_item",
            entity_id=item.id,
            action="create",
            new_value={"visit_id": str(visit_id)},
        )
        return item

    async def update_status(
        self, item_id: uuid.UUID, new_status: WorkItemStatus, acting_user: User
    ) -> VisitWorkItem:
        item = await self.session.get(VisitWorkItem, item_id)
        assert item is not None
        if acting_user.role.value == "mechanic" and item.assigned_mechanic_id != acting_user.id:
            raise NotAssignedMechanic()
        item.status = new_status
        await self.session.flush()
        return item

    async def approve(self, item_id: uuid.UUID, acting_user: User) -> VisitWorkItem:
        item = await self.session.get(VisitWorkItem, item_id)
        assert item is not None
        item.approved_by_client = True
        item.approved_at = datetime.now(timezone.utc)
        item.approved_via = ApprovedVia.CRM_STATUS
        await self.session.flush()
        return item
```

- [ ] **Шаг 5: `work_items_router.py`**

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.enums import UserRole
from app.core.exceptions import NotAssignedMechanic
from app.modules.users.auth import require_role
from app.modules.users.models import User
from app.modules.visits.work_items_schemas import WorkItemCreate, WorkItemOut, WorkItemStatusChange
from app.modules.visits.work_items_service import WorkItemService

router = APIRouter(prefix="/visits/{visit_id}/work-items", tags=["visit-work-items"])


@router.post("", response_model=WorkItemOut, status_code=201)
async def add_work_item(
    visit_id,
    data: WorkItemCreate,
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MASTER)),
):
    service = WorkItemService(session)
    item = await service.add_item(visit_id, data, acting_user)
    await session.commit()
    return item


@router.patch("/{item_id}/status", response_model=WorkItemOut)
async def change_work_item_status(
    visit_id,
    item_id,
    data: WorkItemStatusChange,
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MASTER, UserRole.MECHANIC)),
):
    service = WorkItemService(session)
    try:
        item = await service.update_status(item_id, data.new_status, acting_user)
    except NotAssignedMechanic:
        raise HTTPException(403, "Можно менять статус только своих назначенных работ")
    await session.commit()
    return item


@router.post("/{item_id}/approve", response_model=WorkItemOut)
async def approve_work_item(
    visit_id,
    item_id,
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MASTER)),
):
    service = WorkItemService(session)
    item = await service.approve(item_id, acting_user)
    await session.commit()
    return item
```

- [ ] **Шаг 6: тесты — падают, затем проходят**

`tests/modules/visits/test_work_items.py`:

```python
import uuid

import pytest

from app.core.enums import UserRole, VisitStatus, WorkCategory, WorkItemStatus
from app.core.exceptions import NotAssignedMechanic
from app.modules.clients.schemas import ClientCreate
from app.modules.clients.service import ClientService
from app.modules.users.models import User
from app.modules.vehicles.schemas import VehicleCreate
from app.modules.vehicles.service import VehicleService
from app.modules.visits.schemas import VisitCreate
from app.modules.visits.service import VisitService
from app.modules.visits.work_items_schemas import WorkItemCreate
from app.modules.visits.work_items_service import WorkItemService


async def _setup_visit_with_mechanic(session):
    admin = User(role=UserRole.ADMIN, full_name="Админ", branch_id=uuid.uuid4())
    mechanic_a = User(role=UserRole.MECHANIC, full_name="Механик А", branch_id=uuid.uuid4())
    mechanic_b = User(role=UserRole.MECHANIC, full_name="Механик Б", branch_id=uuid.uuid4())
    session.add_all([admin, mechanic_a, mechanic_b])
    await session.flush()

    client = await ClientService(session).create_client(
        ClientCreate(full_name="Иван", phone="79991234567"), admin
    )
    vehicle = await VehicleService(session).create_vehicle(
        VehicleCreate(vin="X" * 17, plate_number="А123", make="Toyota", model="Camry"), admin
    )
    visit = await VisitService(session).create_visit(
        VisitCreate(client_id=client.id, vehicle_id=vehicle.id, assigned_master_id=admin.id, mileage_at_intake=1000),
        admin,
    )
    item = await WorkItemService(session).add_item(
        visit.id,
        WorkItemCreate(
            free_text_name="Замена масла",
            category=WorkCategory.MAINTENANCE,
            norm_hours=1.0,
            hourly_rate=1500,
            assigned_mechanic_id=mechanic_a.id,
        ),
        admin,
    )
    return admin, mechanic_a, mechanic_b, item


async def test_assigned_mechanic_can_update_status(session):
    admin, mechanic_a, mechanic_b, item = await _setup_visit_with_mechanic(session)
    updated = await WorkItemService(session).update_status(item.id, WorkItemStatus.IN_PROGRESS, mechanic_a)
    assert updated.status == WorkItemStatus.IN_PROGRESS


async def test_other_mechanic_cannot_update_status(session):
    admin, mechanic_a, mechanic_b, item = await _setup_visit_with_mechanic(session)
    with pytest.raises(NotAssignedMechanic):
        await WorkItemService(session).update_status(item.id, WorkItemStatus.IN_PROGRESS, mechanic_b)


async def test_approve_sets_flags(session):
    admin, mechanic_a, mechanic_b, item = await _setup_visit_with_mechanic(session)
    approved = await WorkItemService(session).approve(item.id, admin)
    assert approved.approved_by_client is True
    assert approved.approved_at is not None
```

Run: `pytest tests/modules/visits/test_work_items.py -v`
Expected: FAIL до реализации шагов 1–5, PASS после.

- [ ] **Шаг 7: подключить роутер, миграция**

```python
# app/main.py
from app.modules.visits.work_items_router import router as work_items_router
app.include_router(work_items_router)
```

Run: `alembic revision --autogenerate -m "visit_work_items table"`
Run: `alembic upgrade head`

- [ ] **Шаг 8: Commit**

```bash
git add app/modules/visits tests/modules/visits/test_work_items.py app/core/exceptions.py app/main.py alembic/versions
git commit -m "feat: visit work items with mechanic-scoped status updates"
```

---

### Task 9: Запчасти в заезде + пересчёт итоговой суммы

**Files:**
- Modify: `app/modules/visits/models.py` (добавить `VisitPartItem`)
- Create: `app/modules/visits/part_items_schemas.py`
- Create: `app/modules/visits/part_items_service.py`
- Create: `app/modules/visits/part_items_router.py`
- Modify: `app/modules/visits/service.py` (добавить `recalculate_total`)
- Test: `tests/modules/visits/test_part_items.py`
- Test: `tests/modules/visits/test_totals.py`

**Interfaces:**
- Consumes: `VisitWorkItem` (Task 8), `Visit` (Task 6).
- Produces: `VisitPartItem` ORM-модель; `PartItemService.add_item(visit_id, work_item_id, data, acting_user) -> VisitPartItem`; `VisitService.recalculate_total(visit_id) -> Visit` (сумма `norm_hours*hourly_rate` по всем work_items визита + `quantity*unit_price` по всем part_items визита, минус `discount`; вызывается после `add_item` в обоих сервисах — добавить вызов в `WorkItemService.add_item` из Task 8 и здесь в `PartItemService.add_item`).

- [ ] **Шаг 1: `VisitPartItem` в `models.py` (добавить в конец)**

```python
from app.core.enums import PartAvailability


class VisitPartItem(Base, UUIDPkMixin):
    __tablename__ = "visit_part_items"

    visit_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("visits.id"), nullable=False)
    work_item_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("visit_work_items.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    article_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    quantity: Mapped[int] = mapped_column(nullable=False, default=1)
    unit_price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    availability_status: Mapped[PartAvailability] = mapped_column(nullable=False)
```

- [ ] **Шаг 2: `part_items_schemas.py`**

```python
import uuid

from pydantic import BaseModel

from app.core.enums import PartAvailability


class PartItemCreate(BaseModel):
    work_item_id: uuid.UUID
    name: str
    article_number: str | None = None
    quantity: int = 1
    unit_price: float
    availability_status: PartAvailability = PartAvailability.IN_STOCK


class PartItemOut(BaseModel):
    id: uuid.UUID
    name: str
    quantity: int
    unit_price: float

    class Config:
        from_attributes = True
```

- [ ] **Шаг 3: `recalculate_total` в `visits/service.py` (добавить метод и импорты `VisitWorkItem`, `VisitPartItem`, `select`, `func`)**

```python
    async def recalculate_total(self, visit_id: uuid.UUID) -> Visit:
        visit = await self.repo.get(visit_id)
        assert visit is not None

        work_result = await self.session.execute(
            select(VisitWorkItem).where(VisitWorkItem.visit_id == visit_id)
        )
        work_total = sum(float(i.norm_hours) * float(i.hourly_rate) for i in work_result.scalars())

        part_result = await self.session.execute(
            select(VisitPartItem).where(VisitPartItem.visit_id == visit_id)
        )
        part_total = sum(float(p.quantity) * float(p.unit_price) for p in part_result.scalars())

        visit.total_amount = work_total + part_total - float(visit.discount)
        await self.session.flush()
        return visit
```

- [ ] **Шаг 4: `part_items_service.py`**

```python
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.users.audit import record_audit
from app.modules.users.models import User
from app.modules.visits.models import VisitPartItem
from app.modules.visits.part_items_schemas import PartItemCreate
from app.modules.visits.service import VisitService


class PartItemService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.visit_service = VisitService(session)

    async def add_item(self, visit_id: uuid.UUID, data: PartItemCreate, acting_user: User) -> VisitPartItem:
        item = VisitPartItem(visit_id=visit_id, **data.model_dump())
        self.session.add(item)
        await self.session.flush()
        await self.visit_service.recalculate_total(visit_id)
        await record_audit(
            self.session,
            user=acting_user,
            entity_type="visit_part_item",
            entity_id=item.id,
            action="create",
            new_value={"name": item.name},
        )
        return item
```

- [ ] **Шаг 5: добавить пересчёт суммы в `WorkItemService.add_item` (Task 8) — modify**

В `app/modules/visits/work_items_service.py`, метод `add_item`: после `await self.session.flush()` и перед `record_audit` добавить:

```python
        from app.modules.visits.service import VisitService
        await VisitService(self.session).recalculate_total(visit_id)
```

- [ ] **Шаг 6: `part_items_router.py`**

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.enums import UserRole
from app.modules.users.auth import require_role
from app.modules.users.models import User
from app.modules.visits.part_items_schemas import PartItemCreate, PartItemOut
from app.modules.visits.part_items_service import PartItemService

router = APIRouter(prefix="/visits/{visit_id}/part-items", tags=["visit-part-items"])


@router.post("", response_model=PartItemOut, status_code=201)
async def add_part_item(
    visit_id,
    data: PartItemCreate,
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MASTER)),
):
    service = PartItemService(session)
    item = await service.add_item(visit_id, data, acting_user)
    await session.commit()
    return item
```

- [ ] **Шаг 7: тесты — падают, затем проходят**

`tests/modules/visits/test_totals.py`:

```python
import uuid

from app.core.enums import PartAvailability, UserRole, WorkCategory
from app.modules.clients.schemas import ClientCreate
from app.modules.clients.service import ClientService
from app.modules.users.models import User
from app.modules.vehicles.schemas import VehicleCreate
from app.modules.vehicles.service import VehicleService
from app.modules.visits.part_items_schemas import PartItemCreate
from app.modules.visits.part_items_service import PartItemService
from app.modules.visits.schemas import VisitCreate
from app.modules.visits.service import VisitService
from app.modules.visits.work_items_schemas import WorkItemCreate
from app.modules.visits.work_items_service import WorkItemService


async def test_total_amount_recalculates_after_adding_work_and_parts(session):
    admin = User(role=UserRole.ADMIN, full_name="Админ", branch_id=uuid.uuid4())
    session.add(admin)
    await session.flush()

    client = await ClientService(session).create_client(ClientCreate(full_name="Иван", phone="79991234567"), admin)
    vehicle = await VehicleService(session).create_vehicle(
        VehicleCreate(vin="X" * 17, plate_number="А123", make="Toyota", model="Camry"), admin
    )
    visit = await VisitService(session).create_visit(
        VisitCreate(client_id=client.id, vehicle_id=vehicle.id, assigned_master_id=admin.id, mileage_at_intake=1000),
        admin,
    )

    work_item = await WorkItemService(session).add_item(
        visit.id,
        WorkItemCreate(free_text_name="Замена масла", category=WorkCategory.MAINTENANCE, norm_hours=1.0, hourly_rate=1500),
        admin,
    )
    await PartItemService(session).add_item(
        visit.id,
        PartItemCreate(work_item_id=work_item.id, name="Масло", quantity=4, unit_price=500, availability_status=PartAvailability.IN_STOCK),
        admin,
    )

    updated_visit = await VisitService(session).get(visit.id)
    assert float(updated_visit.total_amount) == 1500 * 1.0 + 4 * 500
```

Run: `pytest tests/modules/visits/test_totals.py tests/modules/visits/test_part_items.py -v`
Expected: FAIL до реализации шагов 1–6, PASS после.

- [ ] **Шаг 8: подключить роутер, миграция**

```python
# app/main.py
from app.modules.visits.part_items_router import router as part_items_router
app.include_router(part_items_router)
```

Run: `alembic revision --autogenerate -m "visit_part_items table"`
Run: `alembic upgrade head`

- [ ] **Шаг 9: Commit**

```bash
git add app/modules/visits tests/modules/visits/test_totals.py tests/modules/visits/test_part_items.py app/main.py alembic/versions
git commit -m "feat: visit part items with automatic total recalculation"
```

---

### Task 10: Consent service — draft/токен/confirm, paper-фоллбэк

**Files:**
- Create: `app/modules/consent/{__init__.py,models.py,schemas.py,tokens.py,repository.py,service.py,router.py}`
- Test: `tests/modules/consent/test_service.py`

**Interfaces:**
- Consumes: `Client` (Task 3), `ConsentMethod` (Task 1), `settings.consent_token_ttl_minutes` (Task 1).
- Produces: `ConsentDraft`, `Consent` ORM-модели; `ConsentService.create_draft() -> ConsentDraft` (генерит токен + `expires_at`); `ConsentService.get_draft(token) -> ConsentDraft` (райзит `DraftExpired`/`DraftNotFound`); `ConsentService.confirm(token, client_data) -> Client` (конвертирует draft → `Client` + `Consent(method=QR_ONSITE)`); `ConsentService.register_paper(client_data, acting_user) -> Client` (создаёт `Client` + `Consent(method=PAPER)` без токена).

- [ ] **Шаг 1: `tokens.py`**

```python
import secrets


def generate_token() -> str:
    return secrets.token_urlsafe(24)
```

- [ ] **Шаг 2: `models.py`**

```python
import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import ConsentMethod
from app.core.models import Base, TimestampMixin, UUIDPkMixin


class ConsentDraft(Base, UUIDPkMixin, TimestampMixin):
    __tablename__ = "consent_drafts"

    token: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    converted_client_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("clients.id"), nullable=True
    )


class Consent(Base, UUIDPkMixin, TimestampMixin):
    __tablename__ = "consents"

    client_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("clients.id"), nullable=True)
    draft_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("consent_drafts.id"), nullable=True)
    consent_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consent_text_version: Mapped[str] = mapped_column(String(32), nullable=False)
    consent_method: Mapped[ConsentMethod] = mapped_column(nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    telegram_id: Mapped[int | None] = mapped_column(nullable=True)
    verification_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
```

- [ ] **Шаг 3: доменные исключения**

Добавить в `app/core/exceptions.py`:

```python
class DraftNotFound(Exception):
    """Черновик согласия по токену не найден."""


class DraftExpired(Exception):
    """Токен черновика согласия истёк (TTL 10-15 минут)."""
```

- [ ] **Шаг 4: `schemas.py`**

```python
import uuid

from pydantic import BaseModel

from app.core.enums import ClientType


class ConsentDraftOut(BaseModel):
    token: str
    expires_at: object


class ConsentConfirm(BaseModel):
    full_name: str
    phone: str
    client_type: ClientType = ClientType.INDIVIDUAL
    ip_address: str | None = None


class ConsentPaperRegister(BaseModel):
    full_name: str
    phone: str
    client_type: ClientType = ClientType.INDIVIDUAL
    verification_ref: str | None = None
```

- [ ] **Шаг 5: `repository.py`**

```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.consent.models import Consent, ConsentDraft


class ConsentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_draft(self, draft: ConsentDraft) -> ConsentDraft:
        self.session.add(draft)
        await self.session.flush()
        return draft

    async def get_draft_by_token(self, token: str) -> ConsentDraft | None:
        result = await self.session.execute(select(ConsentDraft).where(ConsentDraft.token == token))
        return result.scalars().first()

    async def create_consent(self, consent: Consent) -> Consent:
        self.session.add(consent)
        await self.session.flush()
        return consent
```

- [ ] **Шаг 6: `service.py`**

```python
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.enums import ConsentMethod
from app.core.exceptions import DraftExpired, DraftNotFound
from app.modules.clients.models import Client
from app.modules.clients.service import ClientService
from app.modules.consent.models import Consent, ConsentDraft
from app.modules.consent.repository import ConsentRepository
from app.modules.consent.schemas import ConsentConfirm, ConsentPaperRegister
from app.modules.consent.tokens import generate_token
from app.modules.clients.schemas import ClientCreate
from app.modules.users.models import User


CONSENT_TEXT_VERSION = "v1"


class ConsentService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = ConsentRepository(session)
        self.client_service = ClientService(session)

    async def create_draft(self) -> ConsentDraft:
        draft = ConsentDraft(
            token=generate_token(),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=settings.consent_token_ttl_minutes),
        )
        return await self.repo.create_draft(draft)

    async def get_valid_draft(self, token: str) -> ConsentDraft:
        draft = await self.repo.get_draft_by_token(token)
        if draft is None:
            raise DraftNotFound()
        if draft.expires_at < datetime.now(timezone.utc):
            raise DraftExpired()
        return draft

    async def confirm(self, token: str, data: ConsentConfirm) -> Client:
        draft = await self.get_valid_draft(token)

        client = await self.client_service.create_client(
            ClientCreate(full_name=data.full_name, phone=data.phone, client_type=data.client_type),
            acting_user=None,  # клиент сам себя регистрирует, без acting_user из CRM
        )
        draft.converted_client_id = client.id

        await self.repo.create_consent(
            Consent(
                client_id=client.id,
                draft_id=draft.id,
                consent_date=datetime.now(timezone.utc),
                consent_text_version=CONSENT_TEXT_VERSION,
                consent_method=ConsentMethod.QR_ONSITE,
                ip_address=data.ip_address,
            )
        )
        return client

    async def register_paper(self, data: ConsentPaperRegister, acting_user: User) -> Client:
        client = await self.client_service.create_client(
            ClientCreate(full_name=data.full_name, phone=data.phone, client_type=data.client_type),
            acting_user=acting_user,
        )
        await self.repo.create_consent(
            Consent(
                client_id=client.id,
                consent_date=datetime.now(timezone.utc),
                consent_text_version=CONSENT_TEXT_VERSION,
                consent_method=ConsentMethod.PAPER,
                verification_ref=data.verification_ref,
            )
        )
        return client
```

`ClientService.create_client` (Task 3) вызывает `record_audit(..., user=acting_user, ...)`, который требует непустого `User`. Для сценария `confirm` (клиент сам себя регистрирует, `acting_user=None`) нужно **изменить** `app/modules/clients/service.py::create_client`, сделав `acting_user: User | None = None` и оборачивая вызов `record_audit` в `if acting_user is not None:`. Это правка существующего файла — внести её в рамках этого шага.

- [ ] **Шаг 7: `router.py`**

```python
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.enums import UserRole
from app.core.exceptions import DraftExpired, DraftNotFound
from app.modules.consent.schemas import ConsentConfirm, ConsentDraftOut, ConsentPaperRegister
from app.modules.consent.service import ConsentService
from app.modules.users.auth import require_role
from app.modules.users.models import User

router = APIRouter(prefix="/consent", tags=["consent"])


@router.post("/draft", response_model=ConsentDraftOut, status_code=201)
async def create_draft(
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MASTER)),
):
    service = ConsentService(session)
    draft = await service.create_draft()
    await session.commit()
    return draft


@router.get("/draft/{token}")
async def get_draft(token: str, session: AsyncSession = Depends(get_session)):
    service = ConsentService(session)
    try:
        draft = await service.get_valid_draft(token)
    except DraftNotFound:
        raise HTTPException(404, "Черновик не найден")
    except DraftExpired:
        raise HTTPException(410, "Срок действия ссылки истёк")
    return {"token": draft.token, "expires_at": draft.expires_at}


@router.post("/confirm")
async def confirm(token: str, data: ConsentConfirm, request: Request, session: AsyncSession = Depends(get_session)):
    data.ip_address = data.ip_address or (request.client.host if request.client else None)
    service = ConsentService(session)
    try:
        client = await service.confirm(token, data)
    except DraftNotFound:
        raise HTTPException(404, "Черновик не найден")
    except DraftExpired:
        raise HTTPException(410, "Срок действия ссылки истёк")
    await session.commit()
    return {"client_id": str(client.id)}


@router.post("/paper")
async def register_paper(
    data: ConsentPaperRegister,
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MASTER)),
):
    service = ConsentService(session)
    client = await service.register_paper(data, acting_user)
    await session.commit()
    return {"client_id": str(client.id)}
```

- [ ] **Шаг 8: тесты — падают, затем проходят**

`tests/modules/consent/test_service.py`:

```python
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.core.exceptions import DraftExpired
from app.modules.consent.models import ConsentDraft
from app.modules.consent.schemas import ConsentConfirm, ConsentPaperRegister
from app.modules.consent.service import ConsentService


async def test_confirm_converts_draft_to_client_with_consent(session):
    service = ConsentService(session)
    draft = await service.create_draft()

    client = await service.confirm(
        draft.token, ConsentConfirm(full_name="Иван", phone="79991234567", ip_address="127.0.0.1")
    )
    assert client.id is not None


async def test_expired_draft_rejected(session):
    service = ConsentService(session)
    draft = ConsentDraft(token="expired-token", expires_at=datetime.now(timezone.utc) - timedelta(minutes=1))
    session.add(draft)
    await session.flush()

    with pytest.raises(DraftExpired):
        await service.confirm(draft.token, ConsentConfirm(full_name="Иван", phone="79991234567"))


async def test_paper_fallback_creates_client_without_token(session):
    from app.core.enums import UserRole
    from app.modules.users.models import User

    admin = User(role=UserRole.ADMIN, full_name="Админ", branch_id=uuid.uuid4())
    session.add(admin)
    await session.flush()

    service = ConsentService(session)
    client = await service.register_paper(
        ConsentPaperRegister(full_name="Пётр", phone="79997654321"), admin
    )
    assert client.id is not None
```

Run: `pytest tests/modules/consent/test_service.py -v`
Expected: FAIL до реализации шагов 1–7 (и правки `clients/service.py`), PASS после.

- [ ] **Шаг 9: подключить роутер, миграция**

```python
# app/main.py
from app.modules.consent.router import router as consent_router
app.include_router(consent_router)
```

Run: `alembic revision --autogenerate -m "consent_drafts and consents tables"`
Run: `alembic upgrade head`

- [ ] **Шаг 10: Commit**

```bash
git add app/modules/consent app/modules/clients/service.py tests/modules/consent app/main.py alembic/versions
git commit -m "feat: consent service with QR-onsite draft flow and paper fallback"
```

---

### Task 11: Поиск (конфигурируемые поля) + recent_views

**Files:**
- Create: `app/modules/search/{__init__.py,config.py,strategies.py,models.py,service.py,router.py}`
- Test: `tests/modules/search/test_service.py`

**Interfaces:**
- Consumes: `Client`, `Vehicle` (Tasks 3–4), `settings.search_fuzzy_threshold`, `settings.recent_views_limit` (Task 1).
- Produces: `SEARCH_FIELDS: list[SearchField]` (`app.modules.search.config`); `SearchService.search(query: str) -> list[SearchResult]`; `RecentView` ORM-модель; `SearchService.record_view(user_id, entity_type, entity_id) -> None`, `SearchService.recent(user_id) -> list[RecentView]`.

- [ ] **Шаг 1: `strategies.py`**

Стратегии `ExactStrategy`/`NormalizedPhoneStrategy`/`ExactOrSuffixStrategy` строят SQLAlchemy-условие по колонке напрямую. `FuzzyStrategy` работает иначе: `pg_trgm`-сравнение задаётся сырым SQL с именем колонки внутри строки, поэтому у него нет общего с остальными метода `build_clause(column, query)` — он используется в `service.py` отдельной веткой (см. шаг 3), а не через общий интерфейс.

```python
from typing import Protocol

from sqlalchemy import ColumnElement

from app.core.phone import normalize_phone


class MatchStrategy(Protocol):
    def build_clause(self, column: ColumnElement, query: str) -> ColumnElement: ...


class ExactStrategy:
    def build_clause(self, column, query: str):
        return column == query


class ExactOrSuffixStrategy:
    """Точное совпадение ИЛИ совпадение по последним 4+ символам (VIN)."""

    def build_clause(self, column, query: str):
        if len(query) <= 4:
            return column.like(f"%{query.upper()}")
        return column == query.upper()


class FuzzyStrategy:
    """Не реализует MatchStrategy.build_clause — см. пояснение выше."""

    def __init__(self, threshold: float):
        self.threshold = threshold
```

- [ ] **Шаг 2: `config.py`**

`match_type=NORMALIZED` сравнивает после применения `normalizer` к введённой строке — один общий тип на телефон и гос.номер, а не два похожих типа, чтобы добавление третьего "нормализуемого" поля в будущем не требовало нового `MatchType`.

```python
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from app.core.phone import normalize_phone
from app.core.plate import normalize_plate


class MatchType(str, Enum):
    EXACT = "exact"
    NORMALIZED = "normalized"
    EXACT_OR_SUFFIX = "exact_or_suffix"
    FUZZY = "fuzzy"


@dataclass(frozen=True)
class SearchField:
    entity: str  # "client" | "vehicle"
    field: str  # имя колонки в ORM-модели
    match_type: MatchType
    normalizer: Callable[[str], str] | None = None  # обязателен при match_type=NORMALIZED


SEARCH_FIELDS: list[SearchField] = [
    SearchField(entity="client", field="phone_normalized", match_type=MatchType.NORMALIZED, normalizer=normalize_phone),
    SearchField(entity="client", field="full_name", match_type=MatchType.FUZZY),
    SearchField(entity="vehicle", field="vin", match_type=MatchType.EXACT_OR_SUFFIX),
    SearchField(entity="vehicle", field="plate_number", match_type=MatchType.NORMALIZED, normalizer=normalize_plate),
    SearchField(entity="vehicle", field="make", match_type=MatchType.FUZZY),
    SearchField(entity="vehicle", field="model", match_type=MatchType.FUZZY),
]
```

`normalize_plate` импортируется из `app.core.plate` (создан в Task 4 — гос.номер нормализуется уже при сохранении `Vehicle`, см. Task 4 шаг 1а), а не определяется заново здесь.

- [ ] **Шаг 3: `service.py`**

```python
import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.modules.clients.models import Client
from app.modules.search.config import SEARCH_FIELDS, MatchType
from app.modules.search.models import RecentView
from app.modules.vehicles.models import Vehicle

ENTITY_MODELS = {"client": Client, "vehicle": Vehicle}


class SearchService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def search(self, query: str) -> list[dict]:
        results: list[dict] = []
        seen: set[tuple[str, uuid.UUID]] = set()

        for field in SEARCH_FIELDS:
            model = ENTITY_MODELS[field.entity]
            column = getattr(model, field.field)

            if field.match_type == MatchType.EXACT:
                stmt = select(model).where(column == query, model.deleted_at.is_(None))
            elif field.match_type == MatchType.NORMALIZED:
                assert field.normalizer is not None
                stmt = select(model).where(column == field.normalizer(query), model.deleted_at.is_(None))
            elif field.match_type == MatchType.EXACT_OR_SUFFIX:
                if len(query) <= 4:
                    stmt = select(model).where(column.like(f"%{query.upper()}"), model.deleted_at.is_(None))
                else:
                    stmt = select(model).where(column == query.upper(), model.deleted_at.is_(None))
            elif field.match_type == MatchType.FUZZY:
                stmt = (
                    select(model)
                    .where(
                        model.deleted_at.is_(None),
                        text(f"similarity({field.field}, :q) > :threshold"),
                    )
                    .params(q=query, threshold=settings.search_fuzzy_threshold)
                    .order_by(text(f"similarity({field.field}, :q) DESC"))
                    .params(q=query)
                )
            else:
                continue

            rows = (await self.session.execute(stmt)).scalars()
            for row in rows:
                key = (field.entity, row.id)
                if key in seen:
                    continue
                seen.add(key)
                results.append({"entity": field.entity, "id": row.id, "matched_field": field.field})

        return results

    async def record_view(self, user_id: uuid.UUID, entity_type: str, entity_id: uuid.UUID) -> None:
        self.session.add(RecentView(user_id=user_id, entity_type=entity_type, entity_id=entity_id))
        await self.session.flush()

    async def recent(self, user_id: uuid.UUID) -> list[RecentView]:
        stmt = (
            select(RecentView)
            .where(RecentView.user_id == user_id)
            .order_by(RecentView.viewed_at.desc())
            .limit(settings.recent_views_limit)
        )
        return list((await self.session.execute(stmt)).scalars())
```

(Шаг 1 выше — вспомогательные классы-стратегии для будущей замены `if/elif`-цепочки на диспатч по типу без дублирования кода; для MVP-объёма `service.py` их можно не выносить отдельно, а сразу писать `if/elif`, как показано здесь. Исполнитель может пропустить `strategies.py` как отдельный файл и оставить логику сравнения прямо в `service.py`, если это не усложнит добавление нового критерия — главное требование спека: новый критерий = новая строка в `SEARCH_FIELDS`, что этот код уже обеспечивает.)

- [ ] **Шаг 4: `models.py` (`RecentView`)**

```python
import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, UUIDPkMixin


class RecentView(Base, UUIDPkMixin):
    __tablename__ = "recent_views"

    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    viewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

- [ ] **Шаг 5: `router.py`**

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.enums import UserRole
from app.modules.search.service import SearchService
from app.modules.users.auth import require_role
from app.modules.users.models import User

router = APIRouter(prefix="/search", tags=["search"])


@router.get("")
async def search(
    q: str,
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MASTER, UserRole.MECHANIC)),
):
    service = SearchService(session)
    return await service.search(q)


@router.get("/recent")
async def recent(
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MASTER, UserRole.MECHANIC)),
):
    service = SearchService(session)
    views = await service.recent(acting_user.id)
    return [{"entity_type": v.entity_type, "entity_id": str(v.entity_id)} for v in views]
```

- [ ] **Шаг 6: тесты — падают, затем проходят**

`tests/modules/search/test_service.py`:

```python
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
```

Run: `pytest tests/modules/search/test_service.py -v`
Expected: FAIL до реализации шагов 1–5, PASS после.

- [ ] **Шаг 7: подключить роутер, миграция**

```python
# app/main.py
from app.modules.search.router import router as search_router
app.include_router(search_router)
```

Run: `alembic revision --autogenerate -m "recent_views table"`
Run: `alembic upgrade head`

- [ ] **Шаг 8: Commit**

```bash
git add app/modules/search tests/modules/search app/main.py alembic/versions
git commit -m "feat: configurable multi-field search with fuzzy/normalized strategies"
```

---

### Task 12: Генерация PDF заказ-наряда

**Files:**
- Create: `app/modules/documents/{__init__.py,storage.py,service.py,router.py}`
- Create: `app/modules/documents/templates/visit_order.html`
- Test: `tests/modules/documents/test_service.py`

**Interfaces:**
- Consumes: `Visit`, `VisitWorkItem`, `VisitPartItem` (Tasks 6, 8, 9), `Client`, `Vehicle` (Tasks 3–4), `settings.file_storage_root` (Task 1).
- Produces: `FileStorage` (протокол: `save(content: bytes, relative_path: str) -> str` — возвращает URL/путь); `LocalFileStorage` (реализация поверх файловой системы); `DocumentService.generate_visit_document(visit_id) -> str` (рендерит HTML → PDF через WeasyPrint, сохраняет, проставляет `visit.document_url`, возвращает URL).

- [ ] **Шаг 1: `storage.py`**

```python
from pathlib import Path
from typing import Protocol

from app.core.config import settings


class FileStorage(Protocol):
    def save(self, content: bytes, relative_path: str) -> str: ...


class LocalFileStorage:
    """MVP-реализация поверх локальной ФС. Замена на S3-совместимое
    хранилище — новый класс с тем же интерфейсом, без изменений в
    DocumentService."""

    def __init__(self, root: str | None = None):
        self.root = Path(root or settings.file_storage_root)
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, content: bytes, relative_path: str) -> str:
        full_path = self.root / relative_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_bytes(content)
        return str(full_path)
```

- [ ] **Шаг 2: `templates/visit_order.html`**

```html
<!DOCTYPE html>
<html lang="ru">
<head><meta charset="utf-8"><title>Заказ-наряд №{{ visit.id }}</title>
<style>
  body { font-family: sans-serif; font-size: 12px; }
  table { width: 100%; border-collapse: collapse; margin-top: 12px; }
  th, td { border: 1px solid #333; padding: 4px 8px; text-align: left; }
  .total { font-weight: bold; margin-top: 16px; }
  .signature { margin-top: 48px; }
</style>
</head>
<body>
  <h1>Заказ-наряд №{{ visit.id }}</h1>
  <p>Клиент: {{ client.full_name }}, тел. {{ client.phone_display }}</p>
  <p>Авто: {{ vehicle.make }} {{ vehicle.model }}, VIN {{ vehicle.vin }}, гос.номер {{ vehicle.plate_number }}</p>
  <p>Пробег на момент приёма: {{ visit.mileage_at_intake }} км</p>

  <h2>Работы</h2>
  <table>
    <tr><th>Наименование</th><th>Категория</th><th>Н/ч</th><th>Ставка</th><th>Сумма</th></tr>
    {% for item in work_items %}
    <tr>
      <td>{{ item.free_text_name or item.catalog_item_name }}</td>
      <td>{{ item.category }}</td>
      <td>{{ item.norm_hours }}</td>
      <td>{{ item.hourly_rate }}</td>
      <td>{{ item.norm_hours * item.hourly_rate }}</td>
    </tr>
    {% endfor %}
  </table>

  <h2>Запчасти</h2>
  <table>
    <tr><th>Наименование</th><th>Артикул</th><th>Кол-во</th><th>Цена</th><th>Сумма</th></tr>
    {% for part in part_items %}
    <tr>
      <td>{{ part.name }}</td>
      <td>{{ part.article_number or "" }}</td>
      <td>{{ part.quantity }}</td>
      <td>{{ part.unit_price }}</td>
      <td>{{ part.quantity * part.unit_price }}</td>
    </tr>
    {% endfor %}
  </table>

  <p class="total">Скидка: {{ visit.discount }} руб. Итого: {{ visit.total_amount }} руб.</p>

  <div class="signature">
    <p>Подпись клиента: _______________________</p>
    <p>(на MVP — согласование фиксируется статусом в CRM, юридической силы подпись не имеет)</p>
  </div>
</body>
</html>
```

- [ ] **Шаг 3: `service.py`**

```python
import uuid

import weasyprint
from jinja2 import Environment, FileSystemLoader
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.clients.models import Client
from app.modules.documents.storage import FileStorage, LocalFileStorage
from app.modules.vehicles.models import Vehicle
from app.modules.visits.models import Visit, VisitPartItem, VisitWorkItem

TEMPLATE_DIR = __file__.rsplit("/", 1)[0] + "/templates"
jinja_env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))


class DocumentService:
    def __init__(self, session: AsyncSession, storage: FileStorage | None = None):
        self.session = session
        self.storage = storage or LocalFileStorage()

    async def generate_visit_document(self, visit_id: uuid.UUID) -> str:
        visit = await self.session.get(Visit, visit_id)
        assert visit is not None
        client = await self.session.get(Client, visit.client_id)
        vehicle = await self.session.get(Vehicle, visit.vehicle_id)

        work_items = list(
            (await self.session.execute(select(VisitWorkItem).where(VisitWorkItem.visit_id == visit_id))).scalars()
        )
        part_items = list(
            (await self.session.execute(select(VisitPartItem).where(VisitPartItem.visit_id == visit_id))).scalars()
        )

        template = jinja_env.get_template("visit_order.html")
        html = template.render(
            visit=visit,
            client=client,
            vehicle=vehicle,
            work_items=[{"free_text_name": w.free_text_name, "catalog_item_name": None, **w.__dict__} for w in work_items],
            part_items=part_items,
        )

        pdf_bytes = weasyprint.HTML(string=html).write_pdf()
        url = self.storage.save(pdf_bytes, f"visits/{visit_id}.pdf")

        visit.document_url = url
        await self.session.flush()
        return url
```

- [ ] **Шаг 4: `router.py`**

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.enums import UserRole
from app.modules.documents.service import DocumentService
from app.modules.users.auth import require_role
from app.modules.users.models import User

router = APIRouter(prefix="/visits/{visit_id}/document", tags=["documents"])


@router.post("")
async def generate_document(
    visit_id,
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MASTER)),
):
    service = DocumentService(session)
    url = await service.generate_visit_document(visit_id)
    await session.commit()
    return {"document_url": url}
```

- [ ] **Шаг 5: тест — падает, затем проходит**

`tests/modules/documents/test_service.py`:

```python
import uuid

from app.core.enums import UserRole, WorkCategory
from app.modules.clients.schemas import ClientCreate
from app.modules.clients.service import ClientService
from app.modules.documents.service import DocumentService
from app.modules.documents.storage import LocalFileStorage
from app.modules.users.models import User
from app.modules.vehicles.schemas import VehicleCreate
from app.modules.vehicles.service import VehicleService
from app.modules.visits.schemas import VisitCreate
from app.modules.visits.service import VisitService
from app.modules.visits.work_items_schemas import WorkItemCreate
from app.modules.visits.work_items_service import WorkItemService


async def test_generate_visit_document_sets_document_url(session, tmp_path):
    admin = User(role=UserRole.ADMIN, full_name="Админ", branch_id=uuid.uuid4())
    session.add(admin)
    await session.flush()

    client = await ClientService(session).create_client(ClientCreate(full_name="Иван", phone="79991234567"), admin)
    vehicle = await VehicleService(session).create_vehicle(
        VehicleCreate(vin="X" * 17, plate_number="А123", make="Toyota", model="Camry"), admin
    )
    visit = await VisitService(session).create_visit(
        VisitCreate(client_id=client.id, vehicle_id=vehicle.id, assigned_master_id=admin.id, mileage_at_intake=1000),
        admin,
    )
    await WorkItemService(session).add_item(
        visit.id,
        WorkItemCreate(free_text_name="Замена масла", category=WorkCategory.MAINTENANCE, norm_hours=1.0, hourly_rate=1500),
        admin,
    )

    storage = LocalFileStorage(root=str(tmp_path))
    url = await DocumentService(session, storage=storage).generate_visit_document(visit.id)

    assert url is not None
    updated_visit = await VisitService(session).get(visit.id)
    assert updated_visit.document_url == url
```

Run: `pytest tests/modules/documents/test_service.py -v`
Expected: FAIL до реализации шагов 1–3 (нет модуля), PASS после. Требует установленных системных зависимостей WeasyPrint (Pango/Cairo) — если тест падает с ошибкой импорта `weasyprint`, установи их согласно официальной документации WeasyPrint для используемой ОС перед повторным запуском.

- [ ] **Шаг 6: подключить роутер**

```python
# app/main.py
from app.modules.documents.router import router as documents_router
app.include_router(documents_router)
```

- [ ] **Шаг 7: Commit**

```bash
git add app/modules/documents tests/modules/documents app/main.py
git commit -m "feat: PDF visit order generation via WeasyPrint with pluggable file storage"
```

---

### Task 13: Уведомления — интерфейс + MVP-реализация, интеграция со статусами

**Files:**
- Create: `app/modules/notifications/{__init__.py,interfaces.py,logging_sender.py}`
- Modify: `app/modules/visits/service.py` (вызов уведомления в `change_status`)
- Modify: `app/modules/visits/work_items_service.py` (вызов уведомления при `is_extra_work`)
- Test: `tests/modules/notifications/test_integration.py`

**Interfaces:**
- Consumes: `Visit`, `VisitStatus`, `VisitWorkItem` (Tasks 6–8).
- Produces: `NotificationSender` (протокол: `send_status_changed(visit, old_status, new_status)`, `send_extra_work_approval_request(work_item)`, `send_document(visit, url)`); `LoggingNotificationSender` (MVP-реализация — пишет структурированную запись в таблицу `notifications_outbox`, реальная отправка в Telegram появится вместе с ботом в следующем цикле и будет отдельной реализацией того же интерфейса).

- [ ] **Шаг 1: `interfaces.py`**

```python
from typing import Protocol

from app.core.enums import VisitStatus
from app.modules.visits.models import Visit, VisitWorkItem


class NotificationSender(Protocol):
    async def send_status_changed(self, visit: Visit, old_status: VisitStatus, new_status: VisitStatus) -> None: ...
    async def send_extra_work_approval_request(self, work_item: VisitWorkItem) -> None: ...
    async def send_document(self, visit: Visit, url: str) -> None: ...
```

- [ ] **Шаг 2: `notifications_outbox`-модель и `LoggingNotificationSender`**

`logging_sender.py`:

```python
import uuid
from datetime import datetime

from sqlalchemy import String, JSON, DateTime, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import VisitStatus
from app.core.models import Base, UUIDPkMixin
from app.modules.visits.models import Visit, VisitWorkItem


class NotificationOutbox(Base, UUIDPkMixin):
    """MVP-заглушка доставки: реальная отправка через Telegram Bot API
    подключается в следующем цикле (бот), подменяя NotificationSender —
    вызывающий код (visits.service) не меняется."""

    __tablename__ = "notifications_outbox"

    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LoggingNotificationSender:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def send_status_changed(self, visit: Visit, old_status: VisitStatus, new_status: VisitStatus) -> None:
        self.session.add(
            NotificationOutbox(
                kind="status_changed",
                payload={"visit_id": str(visit.id), "old_status": old_status.value, "new_status": new_status.value},
            )
        )
        await self.session.flush()

    async def send_extra_work_approval_request(self, work_item: VisitWorkItem) -> None:
        self.session.add(
            NotificationOutbox(
                kind="extra_work_approval_request",
                payload={"work_item_id": str(work_item.id), "visit_id": str(work_item.visit_id)},
            )
        )
        await self.session.flush()

    async def send_document(self, visit: Visit, url: str) -> None:
        self.session.add(
            NotificationOutbox(kind="document_ready", payload={"visit_id": str(visit.id), "url": url})
        )
        await self.session.flush()
```

- [ ] **Шаг 3: интеграция в `VisitService.change_status` (modify)**

В `app/modules/visits/service.py`, конструктор `VisitService.__init__` — добавить параметр `notification_sender: NotificationSender | None = None`, по умолчанию создавать `LoggingNotificationSender(session)`. В конце `change_status`, перед `return visit`, добавить:

```python
        if new_status in (VisitStatus.READY, VisitStatus.WAITING_PARTS):
            await self.notification_sender.send_status_changed(visit, old_status, new_status)
```

- [ ] **Шаг 4: интеграция в `WorkItemService.add_item` (modify, Task 8)**

В `app/modules/visits/work_items_service.py`, после пересчёта суммы (Task 9, шаг 5), добавить:

```python
        if item.is_extra_work:
            from app.modules.notifications.logging_sender import LoggingNotificationSender
            await LoggingNotificationSender(self.session).send_extra_work_approval_request(item)
```

- [ ] **Шаг 5: тест интеграции — падает, затем проходит**

`tests/modules/notifications/test_integration.py`:

```python
import uuid

from sqlalchemy import select

from app.core.enums import UserRole, VisitStatus
from app.modules.clients.schemas import ClientCreate
from app.modules.clients.service import ClientService
from app.modules.notifications.logging_sender import NotificationOutbox
from app.modules.users.models import User
from app.modules.vehicles.schemas import VehicleCreate
from app.modules.vehicles.service import VehicleService
from app.modules.visits.schemas import VisitCreate
from app.modules.visits.service import VisitService


async def test_status_change_to_waiting_parts_writes_notification(session):
    admin = User(role=UserRole.ADMIN, full_name="Админ", branch_id=uuid.uuid4())
    session.add(admin)
    await session.flush()
    client = await ClientService(session).create_client(ClientCreate(full_name="Иван", phone="79991234567"), admin)
    vehicle = await VehicleService(session).create_vehicle(
        VehicleCreate(vin="X" * 17, plate_number="А123", make="Toyota", model="Camry"), admin
    )
    visit_service = VisitService(session)
    visit = await visit_service.create_visit(
        VisitCreate(client_id=client.id, vehicle_id=vehicle.id, assigned_master_id=admin.id, mileage_at_intake=1000),
        admin,
    )
    for status in (VisitStatus.DIAGNOSTICS, VisitStatus.APPROVAL, VisitStatus.IN_PROGRESS):
        visit = await visit_service.change_status(visit.id, status, admin)
    await visit_service.change_status(visit.id, VisitStatus.WAITING_PARTS, admin)

    rows = list((await session.execute(select(NotificationOutbox))).scalars())
    assert any(r.kind == "status_changed" for r in rows)
```

Run: `pytest tests/modules/notifications/test_integration.py -v`
Expected: FAIL до реализации шагов 1–4, PASS после.

- [ ] **Шаг 6: миграция**

Run: `alembic revision --autogenerate -m "notifications_outbox table"`
Run: `alembic upgrade head`

- [ ] **Шаг 7: Commit**

```bash
git add app/modules/notifications app/modules/visits/service.py app/modules/visits/work_items_service.py tests/modules/notifications alembic/versions
git commit -m "feat: notification sender interface with MVP outbox implementation"
```

---

### Task 14: Сборка приложения — сквозной smoke-тест

**Files:**
- Modify: `app/main.py` (финальная сверка всех `include_router`)
- Test: `tests/test_end_to_end.py`

**Interfaces:**
- Consumes: все модули из Tasks 2–13.
- Produces: ничего нового — интеграционная проверка, что полный путь заезда работает поверх собранного приложения.

- [ ] **Шаг 1: убедиться, что `app/main.py` подключает все роутеры**

```python
from fastapi import FastAPI

from app.modules.catalog.router import router as catalog_router
from app.modules.clients.router import router as clients_router
from app.modules.consent.router import router as consent_router
from app.modules.documents.router import router as documents_router
from app.modules.search.router import router as search_router
from app.modules.users.router import router as users_router
from app.modules.vehicles.router import router as vehicles_router
from app.modules.visits.router import router as visits_router
from app.modules.visits.work_items_router import router as work_items_router
from app.modules.visits.part_items_router import router as part_items_router

app = FastAPI(title="CRM Backend")

for r in (
    users_router,
    clients_router,
    vehicles_router,
    catalog_router,
    visits_router,
    work_items_router,
    part_items_router,
    consent_router,
    search_router,
    documents_router,
):
    app.include_router(r)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Шаг 2: сквозной тест — падает при любом разрыве цепочки, затем проходит**

`tests/test_end_to_end.py`:

```python
import uuid

from app.core.enums import UserRole, VisitStatus, WorkCategory, WorkItemStatus
from app.modules.clients.schemas import ClientCreate
from app.modules.clients.service import ClientService
from app.modules.documents.service import DocumentService
from app.modules.documents.storage import LocalFileStorage
from app.modules.users.models import User
from app.modules.vehicles.schemas import VehicleCreate
from app.modules.vehicles.service import VehicleService
from app.modules.visits.schemas import VisitCreate
from app.modules.visits.service import VisitService
from app.modules.visits.work_items_schemas import WorkItemCreate
from app.modules.visits.work_items_service import WorkItemService


async def test_full_visit_lifecycle_produces_document(session, tmp_path):
    admin = User(role=UserRole.ADMIN, full_name="Админ", branch_id=uuid.uuid4())
    mechanic = User(role=UserRole.MECHANIC, full_name="Механик", branch_id=uuid.uuid4())
    session.add_all([admin, mechanic])
    await session.flush()

    client = await ClientService(session).create_client(ClientCreate(full_name="Иван", phone="79991234567"), admin)
    vehicle = await VehicleService(session).create_vehicle(
        VehicleCreate(vin="X" * 17, plate_number="А123", make="Toyota", model="Camry"), admin
    )

    visit_service = VisitService(session)
    visit = await visit_service.create_visit(
        VisitCreate(client_id=client.id, vehicle_id=vehicle.id, assigned_master_id=admin.id, mileage_at_intake=1000),
        admin,
    )

    work_item_service = WorkItemService(session)
    item = await work_item_service.add_item(
        visit.id,
        WorkItemCreate(
            free_text_name="Замена масла",
            category=WorkCategory.MAINTENANCE,
            norm_hours=1.0,
            hourly_rate=1500,
            assigned_mechanic_id=mechanic.id,
        ),
        admin,
    )

    for status in (VisitStatus.DIAGNOSTICS, VisitStatus.APPROVAL, VisitStatus.IN_PROGRESS):
        visit = await visit_service.change_status(visit.id, status, admin)

    await work_item_service.update_status(item.id, WorkItemStatus.READY, mechanic)
    visit = await visit_service.change_status(visit.id, VisitStatus.READY, admin)
    assert visit.status == VisitStatus.READY

    storage = LocalFileStorage(root=str(tmp_path))
    url = await DocumentService(session, storage=storage).generate_visit_document(visit.id)
    assert url is not None
```

Run: `pytest tests/test_end_to_end.py -v`
Expected: PASS (все зависимости уже реализованы в Tasks 1–13; если падает — сигнал о разрыве в интеграции между модулями, искать по трейсбеку).

- [ ] **Шаг 3: прогнать весь набор тестов**

Run: `pytest -v`
Expected: все тесты PASS.

- [ ] **Шаг 4: Commit**

```bash
git add app/main.py tests/test_end_to_end.py
git commit -m "test: end-to-end visit lifecycle smoke test wiring all modules together"
```

---

## Вне рамок этого плана

- Telegram-бот (aiogram 3) — отдельный план следующего цикла, тонкий клиент поверх этого API.
- Реальная отправка уведомлений через Telegram Bot API — заменит `LoggingNotificationSender` в цикле бота.
- Веб-страница consent-флоу (Task 10, `GET/POST /consent/...`) — backend-эндпоинты готовы, фронтенд самой QR-страницы (статический HTML/JS) — отдельная маленькая задача, не описанная здесь, может быть сделана вместе с ботом или раньше по необходимости.
- Полноценная аутентификация (OAuth/JWT) вместо `X-User-Id` — пересмотреть при появлении внешних клиентов (сайт, Mini App).
