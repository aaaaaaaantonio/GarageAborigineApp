# Заработок механиков и настройки видимости — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Механик видит цены работ и запчастей своих заездов, свой заработок (заработано / ожидается) и график заработка; админ включает это и видимость имени, телефона, VIN общими переключателями и задаёт каждому механику схему оплаты.

**Architecture:** Новый модуль `app/modules/settings/` (таблица `app_settings` «ключ → JSON», API настроек и оплаты), новый модуль `app/modules/pay/` (чистая функция `work_pay` и снимок заработка при выдаче), эндпоинт `GET /visits/{id}/mechanic-view` с серверным скрытием полей, расширение `/stats/mine` для механика. Веб: экран «Настройки», карточка заезда механика, цены на экране работы. Бот: «⚙️ Настройки» с переключателями и визардом оплаты, экран «Карточка заезда».

**Tech Stack:** FastAPI, SQLAlchemy 2 async, Alembic, PostgreSQL, pytest; React + TypeScript + TanStack Query + Vitest + MSW; aiogram 3.

**Spec:** `docs/superpowers/specs/2026-10-15-mechanic-pay-visibility-design.md`

## Global Constraints

- Ветка `mechanic-pay` (от `main`); в `main` вливается по команде владельца.
- Все скрытия делает сервер: выключенное поле приходит механику как `null`; клиент ничего не прячет ради безопасности.
- Ключи настроек (bool, по умолчанию `false`): `mechanic_sees_prices`, `mechanic_sees_client_name`, `mechanic_sees_client_phone`, `mechanic_sees_vin`. Нет строки в таблице = значение по умолчанию.
- Схемы оплаты: `percent` (0 < value ≤ 100), `per_hour` (value > 0, ₽ за нормо-час), `full` (value = NULL), не задана = `NULL`.
- Стоимость работы = `norm_hours × hourly_rate`, до скидки; запчасти в заработок не входят; округление `Decimal` до копеек `ROUND_HALF_UP`.
- «Заработано» — свои работы выданных в окне заездов: снимок `mechanic_pay`, без снимка — по текущей схеме. «Ожидается» — свои работы в открытых заездах по текущей схеме, кроме несогласованных доп. работ.
- Схема и заработок — только у роли `mechanic`; админ-исполнитель получает `mechanic_pay = NULL`.
- Схема оплаты не попадает в `UserOut` (её не видят мастера через `/users/mechanics`).
- При `mechanic_sees_prices = false` в `/stats/mine` механика нет ни одного `unit = "rub"` (старый тест остаётся).
- Одна миграция Alembic; новых pip/npm зависимостей нет.
- Тексты интерфейса — на русском; нормо-часы — «н/ч»; `callback_data` бота ≤ 64 байт.
- Перед тестами: `docker compose up -d postgres`. Команды: бэкенд и бот `uv run pytest -q`, веб `cd web && npx vitest run && npx tsc --noEmit -p .`.
- Коммиты заканчиваются строкой `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. Работу в уже выданном заезде переназначили другому механику — снимок должен пересчитаться под нового исполнителя (иначе новый получит заработок по схеме старого). Тест — в Task 3.
2. Число с запятой («12,5») в процентах/ставке — и в вебе, и в боте принимается как 12.5. Тесты — Task 6 (веб), Task 8 (бот).
3. Механик открывает карточку отменённого или выданного заезда со своей работой (из «Выполненных») — 200, а не 403. Тест — Task 4.
4. В заезде есть работа без исполнителя — карточка механика не падает и пишет «без исполнителя». Тесты — Task 4 (API), Task 7 (веб), Task 9 (бот).
5. Цены включены, а схема механику не задана — везде «схема оплаты не задана» / «—», а не 0 ₽. Тесты — Task 4, Task 5, Task 7, Task 9.

---

### Task 1: Модель данных, миграция и расчёт `work_pay`

**Files:**
- Modify: `app/core/enums.py` (enum `PayScheme`)
- Modify: `app/modules/users/models.py` (колонки `pay_scheme`, `pay_value`)
- Modify: `app/modules/visits/models.py` (колонка `VisitWorkItem.mechanic_pay`)
- Create: `app/modules/settings/__init__.py`, `app/modules/settings/models.py`
- Create: `app/modules/pay/__init__.py`, `app/modules/pay/calc.py`
- Create: `alembic/versions/b7d1e3f5a9c2_mechanic_pay_and_settings.py`
- Modify: `alembic/env.py`, `tests/conftest.py` (импорт `app.modules.settings.models`)
- Test: `tests/modules/pay/__init__.py`, `tests/modules/pay/test_calc.py`

**Interfaces:**
- Produces: `PayScheme` (`PERCENT="percent"`, `PER_HOUR="per_hour"`, `FULL="full"`); `User.pay_scheme: PayScheme | None`, `User.pay_value: float | None`; `VisitWorkItem.mechanic_pay: float | None`; `AppSetting(key, value, updated_at, updated_by_user_id)`; `work_pay(norm_hours, hourly_rate, scheme, value) -> Decimal | None`; `line_pay(snapshot, norm_hours, hourly_rate, scheme, value) -> Decimal | None`.

- [ ] **Step 1: Write the failing test**

`tests/modules/pay/__init__.py` — пустой файл. `tests/modules/pay/test_calc.py`:

```python
from decimal import Decimal

from app.core.enums import PayScheme
from app.modules.pay.calc import line_pay, work_pay


def test_percent_of_the_work_cost():
    assert work_pay(2, 1500, PayScheme.PERCENT, 40) == Decimal("1200.00")


def test_fixed_per_norm_hour_ignores_the_client_rate():
    assert work_pay(1.5, 2000, PayScheme.PER_HOUR, 700) == Decimal("1050.00")


def test_full_cost():
    assert work_pay(1.5, 2000, PayScheme.FULL, None) == Decimal("3000.00")


def test_no_scheme_means_unknown():
    assert work_pay(1, 1000, None, None) is None
    assert work_pay(1, 1000, PayScheme.PERCENT, None) is None


def test_rounds_half_up_to_kopecks():
    assert work_pay(0.01, 1, PayScheme.PERCENT, 50) == Decimal("0.01")


def test_snapshot_wins_over_the_current_scheme():
    assert line_pay(777, 2, 1000, PayScheme.FULL, None) == Decimal("777")
    assert line_pay(None, 2, 1000, PayScheme.FULL, None) == Decimal("2000.00")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose up -d postgres && uv run pytest tests/modules/pay/test_calc.py -q`
Expected: FAIL — `ImportError: cannot import name 'PayScheme'`.

- [ ] **Step 3: Write the implementation**

`app/core/enums.py` — добавить в конец:

```python
class PayScheme(str, enum.Enum):
    PERCENT = "percent"
    PER_HOUR = "per_hour"
    FULL = "full"
```

`app/modules/users/models.py` — импорты и две колонки у `User`:

```python
from sqlalchemy import BigInteger, Numeric, String

from app.core.enums import PayScheme, UserRole
```

```python
    # How a mechanic is paid for their works; NULL = not set (no earnings shown).
    pay_scheme: Mapped[PayScheme | None] = mapped_column(nullable=True)
    pay_value: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
```

`app/modules/visits/models.py` — у `VisitWorkItem` после `progress_photos`:

```python
    # The mechanic's pay for this work, fixed when the visit is issued.
    mechanic_pay: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
```

`app/modules/settings/__init__.py` — пустой. `app/modules/settings/models.py`:

```python
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base


class AppSetting(Base):
    """Service-wide settings as key → JSON value; a missing key means the default from code."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
```

`app/modules/pay/__init__.py` — пустой. `app/modules/pay/calc.py`:

```python
"""A mechanic's pay for one work. Pure functions: the snapshot at issue, the stats and the
mechanic's visit card all use them, so the numbers always agree."""
from decimal import ROUND_HALF_UP, Decimal

from app.core.enums import PayScheme

CENT = Decimal("0.01")


def _d(value) -> Decimal:
    return Decimal(str(value))


def work_pay(norm_hours, hourly_rate, scheme: PayScheme | None, value) -> Decimal | None:
    """Pay for a work of `norm_hours` at the client's `hourly_rate`; None when the scheme is unknown."""
    if scheme is None or (scheme != PayScheme.FULL and value is None):
        return None
    hours = _d(norm_hours)
    if scheme == PayScheme.PERCENT:
        pay = hours * _d(hourly_rate) * _d(value) / 100
    elif scheme == PayScheme.PER_HOUR:
        pay = hours * _d(value)
    else:
        pay = hours * _d(hourly_rate)
    return pay.quantize(CENT, rounding=ROUND_HALF_UP)


def line_pay(snapshot, norm_hours, hourly_rate, scheme: PayScheme | None, value) -> Decimal | None:
    """The snapshot taken at issue if there is one, else the pay by the current scheme."""
    if snapshot is not None:
        return _d(snapshot)
    return work_pay(norm_hours, hourly_rate, scheme, value)
```

`alembic/env.py` и `tests/conftest.py` — рядом с остальными импортами моделей добавить:

```python
import app.modules.settings.models  # noqa
```

`alembic/versions/b7d1e3f5a9c2_mechanic_pay_and_settings.py`:

```python
"""mechanic pay scheme, pay snapshot on work items, app settings

Revision ID: b7d1e3f5a9c2
Revises: a9c3e5f7b1d2
Create Date: 2026-10-15 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7d1e3f5a9c2'
down_revision: Union[str, Sequence[str], None] = 'a9c3e5f7b1d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

payscheme = sa.Enum('PERCENT', 'PER_HOUR', 'FULL', name='payscheme')


def upgrade() -> None:
    """Upgrade schema."""
    payscheme.create(op.get_bind(), checkfirst=True)
    op.add_column('users', sa.Column('pay_scheme', payscheme, nullable=True))
    op.add_column('users', sa.Column('pay_value', sa.Numeric(precision=10, scale=2), nullable=True))
    op.add_column('visit_work_items', sa.Column('mechanic_pay', sa.Numeric(precision=10, scale=2), nullable=True))
    op.create_table(
        'app_settings',
        sa.Column('key', sa.String(length=64), nullable=False),
        sa.Column('value', sa.JSON(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_by_user_id', sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(['updated_by_user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('key'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('app_settings')
    op.drop_column('visit_work_items', 'mechanic_pay')
    op.drop_column('users', 'pay_value')
    op.drop_column('users', 'pay_scheme')
    payscheme.drop(op.get_bind(), checkfirst=True)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/modules/pay/test_calc.py -q`
Expected: 6 passed.

- [ ] **Step 5: Check the migration on the dev database**

Run: `docker compose up -d --build api && sleep 8 && docker compose logs --tail 20 api`
Expected: в логе `Running upgrade a9c3e5f7b1d2 -> b7d1e3f5a9c2`, api `healthy` (`docker compose ps`).
Run: `docker compose exec -T api alembic downgrade -1 && docker compose exec -T api alembic upgrade head`
Expected: оба без ошибок.

- [ ] **Step 6: Full suite and commit**

Run: `uv run pytest -q` — всё зелёное.

```bash
git add app/core/enums.py app/modules/users/models.py app/modules/visits/models.py app/modules/settings app/modules/pay alembic tests/conftest.py tests/modules/pay
git commit -m "feat(pay): pay schemes, pay snapshot column, app settings table; work_pay calculation"
```

---

### Task 2: API настроек и оплаты механиков

**Files:**
- Create: `app/modules/settings/schemas.py`, `app/modules/settings/service.py`, `app/modules/settings/router.py`
- Modify: `app/main.py` (подключить роутер)
- Test: `tests/modules/settings/__init__.py`, `tests/modules/settings/test_settings_routes.py`

**Interfaces:**
- Consumes: `AppSetting`, `PayScheme`, `User.pay_scheme/pay_value` (Task 1); `record_audit(session, *, user, entity_type, entity_id, action, old_value, new_value)` из `app/modules/users/audit.py`.
- Produces: `SettingsService(session)` с `visibility() -> VisibilityOut`, `update_visibility(patch, acting_user) -> VisibilityOut`, `mechanic_pay() -> list[MechanicPayOut]`, `set_pay(user_id, patch, acting_user) -> MechanicPayOut`; `NotAMechanic`; эндпоинты `GET/PATCH /settings`, `GET /settings/pay`, `PATCH /settings/pay/{user_id}`.

- [ ] **Step 1: Write the failing tests**

`tests/modules/settings/__init__.py` — пустой. `tests/modules/settings/test_settings_routes.py`:

```python
import uuid

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.enums import UserRole
from app.modules.users.audit import AuditLog
from app.modules.users.models import User
from tests.helpers import staff_headers
from tests.modules.visits.test_visit_routes import api_app  # noqa: F401


async def _req(api_app, method, path, user, json=None):
    async with AsyncClient(transport=ASGITransport(app=api_app), base_url="http://test") as client:
        return await client.request(method, path, headers=staff_headers(user.id), json=json)


async def _staff(session):
    def user(role, name):
        return User(role=role, full_name=name, branch_id=uuid.uuid4())

    admin, master, mech, admin2 = (user(UserRole.ADMIN, "Иванов"), user(UserRole.MASTER, "Кузнецов"),
                                   user(UserRole.MECHANIC, "Морозов"), user(UserRole.ADMIN, "Орлова"))
    session.add_all([admin, master, mech, admin2])
    await session.flush()
    return admin, master, mech, admin2


OFF = {"mechanic_sees_prices": False, "mechanic_sees_client_name": False,
       "mechanic_sees_client_phone": False, "mechanic_sees_vin": False}


async def test_defaults_are_all_off_and_readable_by_every_role(api_app, session):
    admin, master, mech, _ = await _staff(session)
    for user in (admin, master, mech):
        response = await _req(api_app, "GET", "/settings", user)
        assert response.status_code == 200
        assert response.json() == OFF


async def test_admin_switches_one_setting_and_it_is_audited(api_app, session):
    admin, _, mech, _ = await _staff(session)

    response = await _req(api_app, "PATCH", "/settings", admin, {"mechanic_sees_prices": True})

    assert response.status_code == 200
    assert response.json() == OFF | {"mechanic_sees_prices": True}
    assert (await _req(api_app, "GET", "/settings", mech)).json()["mechanic_sees_prices"] is True
    audit = (await session.execute(select(AuditLog).where(AuditLog.entity_type == "settings"))).scalars().all()
    assert len(audit) == 1 and audit[0].new_value["mechanic_sees_prices"] is True


async def test_only_admin_changes_settings(api_app, session):
    _, master, mech, _ = await _staff(session)
    for user in (master, mech):
        assert (await _req(api_app, "PATCH", "/settings", user, {"mechanic_sees_vin": True})).status_code == 403


async def test_pay_list_is_admin_only_and_lists_active_mechanics(api_app, session):
    admin, master, mech, _ = await _staff(session)

    assert (await _req(api_app, "GET", "/settings/pay", master)).status_code == 403
    response = await _req(api_app, "GET", "/settings/pay", admin)

    assert response.json() == [{"user_id": str(mech.id), "full_name": "Морозов", "pay_scheme": None, "pay_value": None}]


async def test_admin_sets_a_percent_scheme(api_app, session):
    admin, _, mech, _ = await _staff(session)

    response = await _req(api_app, "PATCH", f"/settings/pay/{mech.id}", admin, {"pay_scheme": "percent", "pay_value": 40})

    assert response.status_code == 200
    assert response.json()["pay_scheme"] == "percent" and response.json()["pay_value"] == 40.0
    listed = (await _req(api_app, "GET", "/settings/pay", admin)).json()
    assert (listed[0]["pay_scheme"], listed[0]["pay_value"]) == ("percent", 40.0)
    audit = (await session.execute(select(AuditLog).where(AuditLog.action == "pay_changed"))).scalars().all()
    assert len(audit) == 1 and audit[0].entity_id == mech.id


async def test_pay_value_rules(api_app, session):
    admin, _, mech, admin2 = await _staff(session)
    path = f"/settings/pay/{mech.id}"

    assert (await _req(api_app, "PATCH", path, admin, {"pay_scheme": "percent", "pay_value": 150})).status_code == 422
    assert (await _req(api_app, "PATCH", path, admin, {"pay_scheme": "percent", "pay_value": None})).status_code == 422
    assert (await _req(api_app, "PATCH", path, admin, {"pay_scheme": "per_hour", "pay_value": 0})).status_code == 422
    full = await _req(api_app, "PATCH", path, admin, {"pay_scheme": "full", "pay_value": 5})
    assert (full.status_code, full.json()["pay_value"]) == (200, None)
    assert (await _req(api_app, "PATCH", f"/settings/pay/{admin2.id}", admin,
                       {"pay_scheme": "full", "pay_value": None})).status_code == 422


async def test_masters_do_not_see_pay_in_the_mechanics_list(api_app, session):
    admin, master, mech, _ = await _staff(session)
    await _req(api_app, "PATCH", f"/settings/pay/{mech.id}", admin, {"pay_scheme": "percent", "pay_value": 40})

    listed = (await _req(api_app, "GET", "/users/mechanics", master)).json()

    assert all("pay_scheme" not in u and "pay_value" not in u for u in listed)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/modules/settings -q`
Expected: FAIL — `/settings` отвечает 404.

- [ ] **Step 3: Write the implementation**

`app/modules/settings/schemas.py`:

```python
import uuid

from pydantic import BaseModel, ConfigDict, model_validator

from app.core.enums import PayScheme


class VisibilityOut(BaseModel):
    mechanic_sees_prices: bool
    mechanic_sees_client_name: bool
    mechanic_sees_client_phone: bool
    mechanic_sees_vin: bool


class VisibilityPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mechanic_sees_prices: bool | None = None
    mechanic_sees_client_name: bool | None = None
    mechanic_sees_client_phone: bool | None = None
    mechanic_sees_vin: bool | None = None


class MechanicPayOut(BaseModel):
    user_id: uuid.UUID
    full_name: str
    pay_scheme: PayScheme | None
    pay_value: float | None


class PayPatch(BaseModel):
    pay_scheme: PayScheme | None
    pay_value: float | None = None

    @model_validator(mode="after")
    def _check_value(self) -> "PayPatch":
        if self.pay_scheme in (None, PayScheme.FULL):
            self.pay_value = None
        elif self.pay_scheme == PayScheme.PERCENT and (self.pay_value is None or not 0 < self.pay_value <= 100):
            raise ValueError("Процент должен быть больше 0 и не больше 100")
        elif self.pay_scheme == PayScheme.PER_HOUR and (self.pay_value is None or self.pay_value <= 0):
            raise ValueError("Ставка за нормо-час должна быть больше нуля")
        return self
```

`app/modules/settings/service.py`:

```python
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
```

`app/modules/settings/router.py`:

```python
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.enums import UserRole
from app.modules.settings.schemas import MechanicPayOut, PayPatch, VisibilityOut, VisibilityPatch
from app.modules.settings.service import NotAMechanic, SettingsService
from app.modules.users.auth import require_role
from app.modules.users.models import User

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=VisibilityOut)
async def get_settings(
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MASTER, UserRole.MECHANIC)),
):
    return await SettingsService(session).visibility()


@router.patch("", response_model=VisibilityOut)
async def update_settings(
    data: VisibilityPatch,
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_role(UserRole.ADMIN)),
):
    out = await SettingsService(session).update_visibility(data, acting_user)
    await session.commit()
    return out


@router.get("/pay", response_model=list[MechanicPayOut])
async def list_mechanic_pay(
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_role(UserRole.ADMIN)),
):
    return await SettingsService(session).mechanic_pay()


@router.patch("/pay/{user_id}", response_model=MechanicPayOut)
async def set_mechanic_pay(
    user_id: uuid.UUID,
    data: PayPatch,
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_role(UserRole.ADMIN)),
):
    try:
        out = await SettingsService(session).set_pay(user_id, data, acting_user)
    except NotAMechanic:
        raise HTTPException(422, "Схему оплаты можно задать только активному механику")
    await session.commit()
    return out
```

`app/main.py` — импорт и подключение рядом с `stats_router`:

```python
from app.modules.settings.router import router as settings_router
```

```python
app.include_router(settings_router)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/modules/settings -q`
Expected: 7 passed.

- [ ] **Step 5: Full suite and commit**

Run: `uv run pytest -q` — всё зелёное.

```bash
git add app/modules/settings app/main.py tests/modules/settings
git commit -m "feat(settings): mechanic visibility switches and per-mechanic pay schemes (admin API, audited)"
```

---

### Task 3: Снимок заработка при выдаче и при переназначении выданной работы

**Files:**
- Create: `app/modules/pay/service.py`
- Modify: `app/modules/visits/service.py` (`change_status`)
- Modify: `app/modules/visits/work_items_service.py` (`assign_mechanic`)
- Test: `tests/modules/pay/test_snapshot.py`

**Interfaces:**
- Consumes: `work_pay` (Task 1); `VisitService(session).change_status(visit_id, new_status, acting_user, reason=None)`; `WorkItemService(session).assign_mechanic(visit_id, item_id, mechanic_id, acting_user)`.
- Produces: `snapshot_mechanic_pay(session, items: list[VisitWorkItem]) -> None` — пишет `item.mechanic_pay` по схеме текущего исполнителя (только роль `mechanic`, иначе `None`).

- [ ] **Step 1: Write the failing tests**

`tests/modules/pay/test_snapshot.py`:

```python
from decimal import Decimal

from app.core.enums import PayScheme, VisitStatus
from app.modules.visits.service import VisitService
from app.modules.visits.work_items_service import WorkItemService
from tests.modules.stats.helpers import msk, visit, work, world


async def _issue(session, w, v):
    await VisitService(session).change_status(v.id, VisitStatus.ISSUED, w.admin)
    await session.flush()


async def test_issue_fixes_pay_for_mechanics_with_a_scheme(session):
    w = await world(session)
    w.mech_a.pay_scheme, w.mech_a.pay_value = PayScheme.PERCENT, 50
    v = await visit(session, w, master=w.master_a, created=msk(10, 9), status=VisitStatus.READY)
    own = await work(session, v, name="Масло", hours=2, rate=1000, mechanic=w.mech_a)
    by_admin = await work(session, v, name="Сам", hours=1, rate=1000, mechanic=w.admin)
    no_scheme = await work(session, v, name="Чужая", hours=1, rate=1000, mechanic=w.mech_b)
    nobody = await work(session, v, name="Ничья", hours=1, rate=1000)

    await _issue(session, w, v)

    assert own.mechanic_pay == Decimal("1000.00")
    assert (by_admin.mechanic_pay, no_scheme.mechanic_pay, nobody.mechanic_pay) == (None, None, None)


async def test_changing_the_scheme_later_keeps_the_snapshot(session):
    w = await world(session)
    w.mech_a.pay_scheme, w.mech_a.pay_value = PayScheme.PERCENT, 50
    v = await visit(session, w, master=w.master_a, created=msk(10, 9), status=VisitStatus.READY)
    own = await work(session, v, name="Масло", hours=2, rate=1000, mechanic=w.mech_a)
    await _issue(session, w, v)

    w.mech_a.pay_value = 10
    await session.flush()
    await session.refresh(own)

    assert own.mechanic_pay == Decimal("1000.00")


async def test_reassigning_an_issued_work_recomputes_it_for_the_new_mechanic(session):
    w = await world(session)
    w.mech_a.pay_scheme, w.mech_a.pay_value = PayScheme.PERCENT, 50
    w.mech_b.pay_scheme, w.mech_b.pay_value = PayScheme.FULL, None
    v = await visit(session, w, master=w.master_a, created=msk(10, 9), status=VisitStatus.READY)
    item = await work(session, v, name="Масло", hours=2, rate=1000, mechanic=w.mech_a)
    await _issue(session, w, v)

    await WorkItemService(session).assign_mechanic(v.id, item.id, w.mech_b.id, w.admin)

    assert item.mechanic_pay == Decimal("2000.00")


async def test_reassigning_an_open_work_does_not_snapshot(session):
    w = await world(session)
    w.mech_a.pay_scheme, w.mech_a.pay_value = PayScheme.FULL, None
    v = await visit(session, w, master=w.master_a, created=msk(10, 9), status=VisitStatus.IN_PROGRESS)
    item = await work(session, v, name="Масло", hours=2, rate=1000, mechanic=w.mech_b)

    await WorkItemService(session).assign_mechanic(v.id, item.id, w.mech_a.id, w.admin)

    assert item.mechanic_pay is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/modules/pay/test_snapshot.py -q`
Expected: FAIL — `mechanic_pay` остаётся `None` в первом тесте (`assert None == Decimal('1000.00')`).

- [ ] **Step 3: Write the implementation**

`app/modules/pay/service.py`:

```python
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
```

`app/modules/visits/service.py` — импорт:

```python
from app.modules.pay.service import snapshot_mechanic_pay
```

В `change_status` сразу после блока `if new_status == VisitStatus.CANCELLED: visit.cancelled_reason = reason`:

```python
        if new_status == VisitStatus.ISSUED:
            result = await self.session.execute(select(VisitWorkItem).where(VisitWorkItem.visit_id == visit_id))
            await snapshot_mechanic_pay(self.session, list(result.scalars()))
```

`app/modules/visits/work_items_service.py` — импорт:

```python
from app.modules.pay.service import snapshot_mechanic_pay
```

В `assign_mechanic` заменить

```python
        item.assigned_mechanic_id = mechanic_id
        await self.session.flush()
```

на

```python
        item.assigned_mechanic_id = mechanic_id
        visit = await self.session.get(Visit, visit_id)
        if visit.status == VisitStatus.ISSUED:
            # The visit is already paid: the work's pay moves to the new assignee's scheme.
            await snapshot_mechanic_pay(self.session, [item])
        await self.session.flush()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/modules/pay -q`
Expected: 10 passed.

- [ ] **Step 5: Full suite and commit**

Run: `uv run pytest -q` — всё зелёное.

```bash
git add app/modules/pay/service.py app/modules/visits/service.py app/modules/visits/work_items_service.py tests/modules/pay/test_snapshot.py
git commit -m "feat(pay): fix mechanic pay when a visit is issued; recompute on reassigning an issued work"
```

---

### Task 4: Карточка заезда для механика — `GET /visits/{id}/mechanic-view`

**Files:**
- Create: `app/modules/visits/mechanic_view_schemas.py`, `app/modules/visits/mechanic_view_service.py`
- Modify: `app/modules/visits/router.py` (новый маршрут)
- Test: `tests/modules/visits/test_mechanic_view.py`

**Interfaces:**
- Consumes: `SettingsService(session).visibility()` (Task 2), `line_pay` (Task 1), `WorkItemService(session).list_for_visit(visit_id)` (элементы с `.name`, `.assigned_mechanic_name`, `.category`, `.status`, `.norm_hours`, `.hourly_rate`, `.assigned_mechanic_id`, `.mechanic_pay`).
- Produces: `MechanicVisitOut` (поля ниже); `MechanicViewService(session).get(visit_id, mechanic) -> MechanicVisitOut`; исключение `NotYourVisit`. JSON: `id, status, created_at, mileage_at_intake, plate_number, make_model, master_name, client_name, client_phone, client_telegram_username, vin, discount, total_amount, my_pay_total, works[{id, name, category, status, mechanic_name, is_mine, norm_hours, hourly_rate, amount, my_pay, parts[{name, article_number, quantity, availability_status, unit_price, amount}]}]`.

- [ ] **Step 1: Write the failing tests**

`tests/modules/visits/test_mechanic_view.py`:

```python
from app.core.enums import PayScheme, VisitStatus
from app.modules.settings.schemas import VisibilityPatch
from app.modules.settings.service import SettingsService
from tests.modules.stats.helpers import msk, part, visit, work, world
from tests.modules.visits.test_visit_routes import _get, api_app  # noqa: F401

PRICE_FIELDS = ("discount", "total_amount", "my_pay_total")
CLIENT_FIELDS = ("client_name", "client_phone", "client_telegram_username", "vin")


async def _setup(session, status=VisitStatus.IN_PROGRESS):
    w = await world(session)
    v = await visit(session, w, master=w.master_a, created=msk(10, 9), status=status, total=3200)
    w.own = await work(session, v, name="Масло", hours=2, rate=1000, mechanic=w.mech_a)
    await part(session, v, w.own, qty=2, price=300)
    await work(session, v, name="Рычаг", hours=1, rate=1000, mechanic=w.mech_b)
    await work(session, v, name="Ничья", hours=0.5, rate=1000)
    w.v = v
    return w


async def _view(api_app, w, user=None):
    return await _get(api_app, f"/visits/{w.v.id}/mechanic-view", user or w.mech_a)


async def test_only_a_mechanic_with_a_work_in_the_visit_may_open_it(api_app, session):
    w = await _setup(session)
    stranger = await visit(session, w, master=w.master_a, created=msk(10, 9), status=VisitStatus.IN_PROGRESS)
    await work(session, stranger, name="Чужое", hours=1, rate=1000, mechanic=w.mech_b)

    assert (await _view(api_app, w)).status_code == 200
    assert (await _get(api_app, f"/visits/{stranger.id}/mechanic-view", w.mech_a)).status_code == 403
    assert (await _view(api_app, w, w.master_a)).status_code == 403
    assert (await _get(api_app, "/visits/00000000-0000-0000-0000-000000000000/mechanic-view", w.mech_a)).status_code == 404


async def test_closed_visits_open_too(api_app, session):
    for status in (VisitStatus.ISSUED, VisitStatus.CANCELLED):
        w = await _setup(session, status)
        assert (await _view(api_app, w)).status_code == 200


async def test_by_default_no_prices_and_no_client_data(api_app, session):
    w = await _setup(session)

    body = (await _view(api_app, w)).json()

    assert (body["plate_number"], body["make_model"], body["master_name"]) == ("А123ВС77", "Toyota Camry", "Кузнецов")
    assert all(body[k] is None for k in PRICE_FIELDS + CLIENT_FIELDS)
    works = {x["name"]: x for x in body["works"]}
    assert set(works) == {"Масло", "Рычаг", "Ничья"}
    assert (works["Масло"]["is_mine"], works["Рычаг"]["mechanic_name"], works["Ничья"]["mechanic_name"]) == (True, "Соколов", None)
    assert works["Масло"]["norm_hours"] == 2
    assert all(x[k] is None for x in body["works"] for k in ("hourly_rate", "amount", "my_pay"))
    assert works["Масло"]["parts"][0] | {} == {"name": "Запчасть", "article_number": None, "quantity": 2,
                                               "availability_status": "in_stock", "unit_price": None, "amount": None}


async def test_everything_switched_on(api_app, session):
    w = await _setup(session)
    w.mech_a.pay_scheme, w.mech_a.pay_value = PayScheme.PERCENT, 50
    await SettingsService(session).update_visibility(VisibilityPatch(
        mechanic_sees_prices=True, mechanic_sees_client_name=True, mechanic_sees_client_phone=True, mechanic_sees_vin=True,
    ), w.admin)

    body = (await _view(api_app, w)).json()

    assert body["client_name"] == "Петров Иван" and "999" in body["client_phone"] and body["vin"] == "A" * 17
    assert (body["total_amount"], body["discount"], body["my_pay_total"]) == (3200, 0, 1000)
    works = {x["name"]: x for x in body["works"]}
    assert (works["Масло"]["hourly_rate"], works["Масло"]["amount"], works["Масло"]["my_pay"]) == (1000, 2000, 1000)
    assert (works["Рычаг"]["amount"], works["Рычаг"]["my_pay"]) == (1000, None)
    assert (works["Масло"]["parts"][0]["unit_price"], works["Масло"]["parts"][0]["amount"]) == (300, 600)


async def test_each_switch_opens_only_its_fields(api_app, session):
    w = await _setup(session)
    await SettingsService(session).update_visibility(VisibilityPatch(mechanic_sees_client_phone=True), w.admin)

    body = (await _view(api_app, w)).json()

    assert body["client_phone"] is not None
    assert (body["client_name"], body["vin"], body["total_amount"]) == (None, None, None)


async def test_prices_on_without_a_scheme_shows_no_pay(api_app, session):
    w = await _setup(session)
    await SettingsService(session).update_visibility(VisibilityPatch(mechanic_sees_prices=True), w.admin)

    body = (await _view(api_app, w)).json()

    assert body["total_amount"] == 3200
    assert body["my_pay_total"] is None
    assert {x["name"]: x["my_pay"] for x in body["works"]}["Масло"] is None


async def test_snapshot_is_shown_for_issued_visits(api_app, session):
    w = await _setup(session, VisitStatus.ISSUED)
    w.mech_a.pay_scheme, w.mech_a.pay_value = PayScheme.FULL, None
    w.own.mechanic_pay = 777
    await session.flush()
    await SettingsService(session).update_visibility(VisibilityPatch(mechanic_sees_prices=True), w.admin)

    body = (await _view(api_app, w)).json()

    assert body["my_pay_total"] == 777
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/modules/visits/test_mechanic_view.py -q`
Expected: FAIL — маршрут не найден (404/405 вместо 200).

- [ ] **Step 3: Write the implementation**

`app/modules/visits/mechanic_view_schemas.py`:

```python
import uuid
from datetime import datetime

from pydantic import BaseModel

from app.core.enums import PartAvailability, VisitStatus, WorkCategory, WorkItemStatus


class MechanicPartOut(BaseModel):
    name: str
    article_number: str | None
    quantity: int
    availability_status: PartAvailability
    unit_price: float | None
    amount: float | None


class MechanicWorkOut(BaseModel):
    id: uuid.UUID
    name: str
    category: WorkCategory
    status: WorkItemStatus
    mechanic_name: str | None
    is_mine: bool
    norm_hours: float
    hourly_rate: float | None
    amount: float | None
    my_pay: float | None
    parts: list[MechanicPartOut]


class MechanicVisitOut(BaseModel):
    """The visit card for a mechanic. Fields the admin's settings hide are None."""

    id: uuid.UUID
    status: VisitStatus
    created_at: datetime
    mileage_at_intake: int
    plate_number: str
    make_model: str
    master_name: str
    client_name: str | None
    client_phone: str | None
    client_telegram_username: str | None
    vin: str | None
    discount: float | None
    total_amount: float | None
    my_pay_total: float | None
    works: list[MechanicWorkOut]
```

`app/modules/visits/mechanic_view_service.py`:

```python
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
```

`app/modules/visits/router.py` — импорты:

```python
from app.modules.visits.mechanic_view_schemas import MechanicVisitOut
from app.modules.visits.mechanic_view_service import MechanicViewService, NotYourVisit
```

Маршрут после `get_visit_lines`:

```python
@router.get("/{visit_id}/mechanic-view", response_model=MechanicVisitOut)
async def get_mechanic_view(
    visit_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_role(UserRole.MECHANIC)),
):
    try:
        return await MechanicViewService(session).get(visit_id, acting_user)
    except VisitNotFound:
        raise HTTPException(404, "Visit not found")
    except NotYourVisit:
        raise HTTPException(403, "В этом заезде нет ваших работ")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/modules/visits/test_mechanic_view.py -q`
Expected: 7 passed.

- [ ] **Step 5: Full suite and commit**

Run: `uv run pytest -q` — всё зелёное.

```bash
git add app/modules/visits/mechanic_view_schemas.py app/modules/visits/mechanic_view_service.py app/modules/visits/router.py tests/modules/visits/test_mechanic_view.py
git commit -m "feat(visits): mechanic's read-only visit card; prices and client data follow admin settings"
```

---

### Task 5: «Заработано» и «Ожидается» в статистике механика

**Files:**
- Modify: `app/modules/stats/repository.py` (`work_lines` + `id`, `mechanic_pay`; новый `open_work_lines`)
- Modify: `app/modules/stats/service.py` (`_mine_mechanic`)
- Test: `tests/modules/stats/test_mine.py`

**Interfaces:**
- Consumes: `SettingsService(session).visibility()` (Task 2), `line_pay`, `work_pay` (Task 1), `User.pay_scheme/pay_value`.
- Produces: при `mechanic_sees_prices` — KPI `earned` («Заработано», `rub` с дельтой; без схемы и снимков — `"—"`, `text`, `compare=False`), KPI `expected` («Ожидается», `rub`, `compare=False`; без схемы — `"—"`, `text`), график `earned` («Заработок», `bars`, `rub`) первым. KPI порядок: `earned, expected, hours, works, in_progress, avg_hours`.

- [ ] **Step 1: Write the failing tests**

В `tests/modules/stats/test_mine.py` дописать (импорты — в начало файла):

```python
from app.core.enums import PayScheme
from app.modules.settings.schemas import VisibilityPatch
from app.modules.settings.service import SettingsService
```

```python
async def _prices_on(session, w):
    await SettingsService(session).update_visibility(VisibilityPatch(mechanic_sees_prices=True), w.admin)


async def test_mechanic_earnings_with_prices_on(session):
    w = await _mine_world(session)
    w.mech_a.pay_scheme, w.mech_a.pay_value = PayScheme.PERCENT, 50
    open_visit = await visit(session, w, master=w.master_a, created=msk(10, 13), status=VisitStatus.IN_PROGRESS)
    await work(session, open_visit, name="Не согласована", hours=10, rate=1000, mechanic=w.mech_a, extra=True)
    await work(session, open_visit, name="Согласована", hours=2, rate=1000, mechanic=w.mech_a, extra=True, approved=True)
    await _prices_on(session, w)

    out = await StatsService(session, now=NOW).mine(w.mech_a, "month")

    k = {x.key: x for x in out.kpis}
    assert [x.key for x in out.kpis][:2] == ["earned", "expected"]
    assert (k["earned"].value, k["earned"].unit) == (3750, "rub")  # (2 + 1.5 + 4) н/ч × 1000 × 50 %
    assert (k["expected"].value, k["expected"].compare) == (2000, False)  # (1 + 1 + 2) × 1000 × 50 %
    assert out.charts[0].key == "earned" and out.charts[0].series[0].values[-1] == 3750


async def test_snapshot_counts_instead_of_the_scheme(session):
    w = await _mine_world(session)
    w.mech_a.pay_scheme, w.mech_a.pay_value = PayScheme.PERCENT, 50
    lines = (await session.execute(select(VisitWorkItem).where(VisitWorkItem.free_text_name == "Масло"))).scalars().all()
    lines[0].mechanic_pay = 100
    await session.flush()
    await _prices_on(session, w)

    out = await StatsService(session, now=NOW).mine(w.mech_a, "month")

    assert {x.key: x for x in out.kpis}["earned"].value == 2850  # 3750 − 1000 (масло по схеме) + 100 (снимок)


async def test_prices_on_without_a_scheme_shows_dashes(session):
    w = await _mine_world(session)
    await _prices_on(session, w)

    out = await StatsService(session, now=NOW).mine(w.mech_a, "month")

    k = {x.key: x for x in out.kpis}
    assert (k["earned"].value, k["earned"].unit, k["earned"].compare) == ("—", "text", False)
    assert (k["expected"].value, k["expected"].unit) == ("—", "text")
```

И импорты для второго теста:

```python
from sqlalchemy import select

from app.modules.visits.models import VisitWorkItem
```

Старый `test_mechanic_sees_own_hours_and_no_money` не менять — он проверяет, что при выключенных ценах нет `rub`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/modules/stats/test_mine.py -q`
Expected: 3 новых FAIL — `KeyError: 'earned'`.

- [ ] **Step 3: Write the implementation**

`app/modules/stats/repository.py` — в `work_lines` в `select(...)` добавить первым `VisitWorkItem.id,` и после `VisitWorkItem.approved_by_client,` — `VisitWorkItem.mechanic_pay,`. Новый метод после `open_work_count`:

```python
    async def open_work_lines(self, mechanic_id: uuid.UUID) -> list[Row]:
        """Works assigned to `mechanic_id` in open (not issued, not cancelled) visits."""
        stmt = _alive(
            select(
                VisitWorkItem.norm_hours, VisitWorkItem.hourly_rate,
                VisitWorkItem.is_extra_work, VisitWorkItem.approved_by_client,
            ).select_from(VisitWorkItem).join(Visit, Visit.id == VisitWorkItem.visit_id)
        ).where(
            VisitWorkItem.assigned_mechanic_id == mechanic_id,
            Visit.status.not_in(CLOSED_STATUSES),
        )
        return await self._rows(stmt)
```

`app/modules/stats/service.py` — импорты:

```python
from app.modules.pay.calc import line_pay, work_pay
from app.modules.settings.service import SettingsService
```

В `StatsService.__init__` добавить `self.session = session`.

В `_mine_mechanic` заменить docstring на `"""Norm-hours; money only when the admin lets mechanics see prices."""` и заменить `return StatsOut(...)` целиком на:

```python
        kpis = [
            _kpi("hours", "Нормо-часов", round(hours, 2), "hours", sum(float(x.norm_hours) for x in lines_prev)),
            _kpi("works", "Работ выполнено", len(lines), "count", len(lines_prev)),
            _kpi("in_progress", "Сейчас в работе", await self.repo.open_work_count(user.id), "count", compare=False),
            _kpi("avg_hours", "Среднее на работу", round(hours / len(lines), 1) if lines else 0, "hours",
                 compare=False),
        ]
        charts = [
            _chart("hours", "bars", "Нормо-часы", "hours", [label for label, _ in steps],
                   ("Нормо-часы", _bucketed(steps, ((closed_at[x.visit_id], x.norm_hours) for x in lines)))),
            _chart("hours_by_category", "hbars", "По категориям", "hours", *_split(by_category, "Нормо-часы")),
        ]
        if (await SettingsService(self.session).visibility()).mechanic_sees_prices:
            money_kpis, money_chart = await self._mechanic_money(user, lines, lines_prev, closed_at, steps)
            kpis, charts = money_kpis + kpis, [money_chart, *charts]
        return StatsOut(section="mine", period=period, kpis=kpis, charts=charts)

    async def _mechanic_money(self, user: User, lines, lines_prev, closed_at, steps: Steps):
        """Earned (issued visits: snapshot, else the current scheme) and expected (open visits, current scheme)."""
        def pays(rows):
            return [line_pay(x.mechanic_pay, x.norm_hours, x.hourly_rate, user.pay_scheme, user.pay_value) for x in rows]

        current, previous = pays(lines), pays(lines_prev)
        known = [p for p in current if p is not None]
        if user.pay_scheme is None and not known:
            earned = _kpi("earned", "Заработано", "—", "text", compare=False)
        else:
            earned = _kpi("earned", "Заработано", round(float(sum(known)), 2), "rub",
                          float(sum(p for p in previous if p is not None)))
        if user.pay_scheme is None:
            expected = _kpi("expected", "Ожидается", "—", "text", compare=False)
        else:
            open_lines = [x for x in await self.repo.open_work_lines(user.id)
                          if not (x.is_extra_work and not x.approved_by_client)]
            total = sum(work_pay(x.norm_hours, x.hourly_rate, user.pay_scheme, user.pay_value) or 0 for x in open_lines)
            expected = _kpi("expected", "Ожидается", round(float(total), 2), "rub", compare=False)
        chart = _chart("earned", "bars", "Заработок", "rub", [label for label, _ in steps],
                       ("Заработок", _bucketed(steps, ((closed_at[x.visit_id], p)
                                                       for x, p in zip(lines, current) if p is not None))))
        return [earned, expected], chart
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/modules/stats -q`
Expected: все зелёные, включая старый `test_mechanic_sees_own_hours_and_no_money`.

- [ ] **Step 5: Full suite and commit**

Run: `uv run pytest -q` — всё зелёное.

```bash
git add app/modules/stats tests/modules/stats/test_mine.py
git commit -m "feat(stats): mechanic's earned and expected pay when prices are visible"
```

---

### Task 6: Веб — экран «Настройки» (видимость и оплата)

**Files:**
- Modify: `web/src/api/types.ts`, `web/src/api/endpoints.ts`
- Create: `web/src/screens/SettingsScreen.tsx`, `web/src/screens/SettingsScreen.test.tsx`
- Modify: `web/src/routes.tsx` (маршрут `/settings`), `web/src/screens/MoreScreen.tsx` (ссылка у админа), `web/src/theme.css` (`.toggle-row`)

**Interfaces:**
- Consumes: `GET/PATCH /settings`, `GET /settings/pay`, `PATCH /settings/pay/{user_id}` (Task 2).
- Produces: типы `PayScheme`, `VisibilitySettings`, `MechanicPay`; `settingsApi.get/update/pay/setPay`.

- [ ] **Step 1: Write the failing tests**

`web/src/screens/SettingsScreen.test.tsx`:

```tsx
import { screen, waitFor, within } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { renderApp } from '../test/render';
import { server } from '../test/server';

const OFF = { mechanic_sees_prices: false, mechanic_sees_client_name: false, mechanic_sees_client_phone: false, mechanic_sees_vin: false };

function serveSettings(pay = [{ user_id: 'm1', full_name: 'Морозов', pay_scheme: null, pay_value: null }]) {
  server.use(
    http.get('/api/settings', () => HttpResponse.json(OFF)),
    http.get('/api/settings/pay', () => HttpResponse.json(pay)),
  );
}

test('admin switches what mechanics see', async () => {
  serveSettings();
  let body: unknown = null;
  server.use(http.patch('/api/settings', async ({ request }) => {
    body = await request.json();
    return HttpResponse.json({ ...OFF, mechanic_sees_prices: true });
  }));
  const { user } = renderApp('/settings', { as: 'admin' });
  const prices = await screen.findByRole('switch', { name: 'Цены и заработок' });
  expect(prices).not.toBeChecked();
  expect(screen.getByRole('switch', { name: 'Телефон клиента' })).toBeInTheDocument();
  await user.click(prices);
  await waitFor(() => expect(body).toEqual({ mechanic_sees_prices: true }));
});

test('admin sets a percent scheme, comma decimals accepted', async () => {
  serveSettings();
  let body: unknown = null;
  server.use(http.patch('/api/settings/pay/m1', async ({ request }) => {
    body = await request.json();
    return HttpResponse.json({ user_id: 'm1', full_name: 'Морозов', pay_scheme: 'percent', pay_value: 12.5 });
  }));
  const { user } = renderApp('/settings', { as: 'admin' });
  const card = (await screen.findByText('Морозов')).closest('.card') as HTMLElement;
  expect(within(card).queryByLabelText('Процент, %')).not.toBeInTheDocument();
  await user.selectOptions(within(card).getByLabelText('Схема оплаты'), 'percent');
  await user.type(within(card).getByLabelText('Процент, %'), '12,5');
  await user.click(within(card).getByRole('button', { name: 'Сохранить' }));
  await waitFor(() => expect(body).toEqual({ pay_scheme: 'percent', pay_value: 12.5 }));
});

test('full cost needs no number', async () => {
  serveSettings();
  let body: unknown = null;
  server.use(http.patch('/api/settings/pay/m1', async ({ request }) => {
    body = await request.json();
    return HttpResponse.json({ user_id: 'm1', full_name: 'Морозов', pay_scheme: 'full', pay_value: null });
  }));
  const { user } = renderApp('/settings', { as: 'admin' });
  const card = (await screen.findByText('Морозов')).closest('.card') as HTMLElement;
  await user.selectOptions(within(card).getByLabelText('Схема оплаты'), 'full');
  expect(within(card).queryByLabelText(/Ставка|Процент/)).not.toBeInTheDocument();
  await user.click(within(card).getByRole('button', { name: 'Сохранить' }));
  await waitFor(() => expect(body).toEqual({ pay_scheme: 'full', pay_value: null }));
});

test('«Ещё» has «Настройки» for the admin only', async () => {
  renderApp('/more', { as: 'admin' });
  expect(await screen.findByRole('link', { name: 'Настройки' })).toHaveAttribute('href', '/settings');
});

test('a master has no «Настройки»', async () => {
  renderApp('/more', { as: 'master' });
  await screen.findByRole('link', { name: 'Статистика' });
  expect(screen.queryByRole('link', { name: 'Настройки' })).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd web && npx vitest run src/screens/SettingsScreen.test.tsx`
Expected: FAIL — нет переключателя «Цены и заработок» (маршрут `/settings` уводит на главную).

- [ ] **Step 3: Write the implementation**

`web/src/api/types.ts` — добавить в конец:

```ts
export type PayScheme = 'percent' | 'per_hour' | 'full';

export interface VisibilitySettings {
  mechanic_sees_prices: boolean;
  mechanic_sees_client_name: boolean;
  mechanic_sees_client_phone: boolean;
  mechanic_sees_vin: boolean;
}

export interface MechanicPay {
  user_id: string;
  full_name: string;
  pay_scheme: PayScheme | null;
  pay_value: number | null;
}
```

`web/src/api/endpoints.ts` — добавить типы в импорт из `./types` и в конец файла:

```ts
export const settingsApi = {
  get: () => api.get<VisibilitySettings>('/settings'),
  update: (body: Partial<VisibilitySettings>) => api.patch<VisibilitySettings>('/settings', body),
  pay: () => api.get<MechanicPay[]>('/settings/pay'),
  setPay: (userId: string, scheme: PayScheme | null, value: number | null) =>
    api.patch<MechanicPay>(`/settings/pay/${userId}`, { pay_scheme: scheme, pay_value: value }),
};
```

`web/src/screens/SettingsScreen.tsx`:

```tsx
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { settingsApi } from '../api/endpoints';
import type { MechanicPay, PayScheme, VisibilitySettings } from '../api/types';
import { parseNumber } from '../lib/format';
import { useAction } from '../lib/useAction';
import { Button } from '../ui/Button';
import { EmptyState } from '../ui/EmptyState';
import { Field } from '../ui/Field';
import { Loadable } from '../ui/Loadable';
import { Picker } from '../ui/Picker';
import { ScreenHeader } from '../ui/ScreenHeader';
import { useToast } from '../ui/Toast';

const TOGGLES: [keyof VisibilitySettings, string][] = [
  ['mechanic_sees_prices', 'Цены и заработок'],
  ['mechanic_sees_client_name', 'Имя клиента'],
  ['mechanic_sees_client_phone', 'Телефон клиента'],
  ['mechanic_sees_vin', 'VIN / номер кузова'],
];

type SchemeChoice = PayScheme | 'none';
const SCHEMES: { value: SchemeChoice; label: string }[] = [
  { value: 'none', label: 'Не задана' },
  { value: 'percent', label: 'Процент от работы' },
  { value: 'per_hour', label: 'Фикс за нормо-час' },
  { value: 'full', label: 'Вся стоимость' },
];

export function SettingsScreen() {
  const toast = useToast();
  const settings = useQuery({ queryKey: ['settings'], queryFn: settingsApi.get });
  const pay = useQuery({ queryKey: ['mechanicPay'], queryFn: settingsApi.pay });
  const toggle = useAction((patch: Partial<VisibilitySettings>) => settingsApi.update(patch), {
    invalidate: [['settings']],
    onSuccess: () => toast.show('Сохранено'),
  });
  return (
    <>
      <ScreenHeader title="Настройки" back />
      <div className="stack">
        <h2 className="section-title">Что видят механики</h2>
        <Loadable query={settings}>
          {(s) => (
            <div className="card">
              {TOGGLES.map(([key, label]) => (
                <label key={key} className="toggle-row">
                  <span>{label}</span>
                  <input type="checkbox" role="switch" checked={s[key]} disabled={toggle.isPending}
                    onChange={(e) => toggle.mutate({ [key]: e.target.checked })} />
                </label>
              ))}
            </div>
          )}
        </Loadable>
        <h2 className="section-title">Оплата механиков</h2>
        <Loadable query={pay}>
          {(list) => list.length === 0
            ? <EmptyState text="Механиков нет" />
            : <>{list.map((m) => <PayRow key={m.user_id} m={m} />)}</>}
        </Loadable>
      </div>
    </>
  );
}

function PayRow({ m }: { m: MechanicPay }) {
  const toast = useToast();
  const [scheme, setScheme] = useState<SchemeChoice>(m.pay_scheme ?? 'none');
  const [value, setValue] = useState(m.pay_value === null ? '' : String(m.pay_value).replace('.', ','));
  const needsValue = scheme === 'percent' || scheme === 'per_hour';
  const save = useAction(
    () => settingsApi.setPay(m.user_id, scheme === 'none' ? null : scheme, needsValue ? parseNumber(value) : null),
    { invalidate: [['mechanicPay']], onSuccess: () => toast.show('Сохранено') },
  );
  return (
    <div className="card">
      <b>{m.full_name}</b>
      <Picker label="Схема оплаты" value={scheme} options={SCHEMES} onChange={setScheme} />
      {needsValue && (
        <Field label={scheme === 'percent' ? 'Процент, %' : 'Ставка, ₽ за н/ч'} inputMode="decimal"
          value={value} onChange={(e) => setValue(e.target.value)} />
      )}
      <Button block busy={save.isPending} onClick={() => save.mutate()}>Сохранить</Button>
    </div>
  );
}
```

Проверить, что `parseNumber('12,5')` в `web/src/lib/format.ts` возвращает `12.5`; если нет — это дефект `parseNumber`, исправить там с тестом в `src/lib` и записать в отчёт.

`web/src/routes.tsx` — импорт `SettingsScreen` и маршрут рядом с `/staff/new`:

```tsx
        <Route path="/settings" element={<RoleGate roles={['admin']}><SettingsScreen /></RoleGate>} />
```

`web/src/screens/MoreScreen.tsx` — в админском блоке после «Добавить сотрудника»:

```tsx
            <Link className="btn btn-block" to="/settings">Настройки</Link>
```

`web/src/theme.css` — после правил `.chart-*`:

```css
.toggle-row { display: flex; justify-content: space-between; align-items: center; gap: 12px; min-height: 44px; cursor: pointer; }
.toggle-row input { width: 22px; height: 22px; accent-color: var(--amber); }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd web && npx vitest run src/screens/SettingsScreen.test.tsx`
Expected: 5 passed.

- [ ] **Step 5: Full web suite and commit**

Run: `cd web && npx vitest run && npx tsc --noEmit -p .` — всё зелёное.

```bash
git add web/src
git commit -m "feat(web): admin settings — what mechanics see, mechanic pay schemes"
```

---

### Task 7: Веб — карточка заезда механика, цены на экране работы, переход из «Выполненных»

**Files:**
- Modify: `web/src/api/types.ts`, `web/src/api/endpoints.ts` (`visitsApi.mechanicView`), `web/src/test/fixtures.ts` (`makeMechanicVisit`)
- Create: `web/src/screens/MechanicVisitScreen.tsx`, `web/src/screens/MechanicVisitScreen.test.tsx`
- Modify: `web/src/routes.tsx` (`/my/visit/:visitId`), `web/src/screens/WorkScreen.tsx`, `web/src/screens/WorkScreen.test.tsx`, `web/src/screens/DoneWorksScreen.tsx`

**Interfaces:**
- Consumes: `GET /visits/{id}/mechanic-view` (Task 4).
- Produces: типы `MechanicPart`, `MechanicWork`, `MechanicVisit`; `visitsApi.mechanicView(id)`; маршрут `/my/visit/:visitId`; query key `['mechanicVisit', visitId]`.

- [ ] **Step 1: Write the failing tests**

`web/src/test/fixtures.ts` — добавить (типы `MechanicVisit`, `MechanicWork` — в импорт):

```ts
export function makeMechanicWork(over: Partial<MechanicWork> = {}): MechanicWork {
  return {
    id: 'w1', name: 'Замена масла ДВС', category: 'maintenance', status: 'in_progress', mechanic_name: 'Сидоров Иван',
    is_mine: true, norm_hours: 2, hourly_rate: null, amount: null, my_pay: null,
    parts: [{ name: 'Фильтр', article_number: null, quantity: 1, availability_status: 'in_stock', unit_price: null, amount: null }],
    ...over,
  };
}

export function makeMechanicVisit(over: Partial<MechanicVisit> = {}): MechanicVisit {
  return {
    id: 'v1', status: 'in_progress', created_at: '2026-10-10T09:00:00+00:00', mileage_at_intake: 120000,
    plate_number: 'А123ВС77', make_model: 'Toyota Camry', master_name: 'Орлов Пётр',
    client_name: null, client_phone: null, client_telegram_username: null, vin: null,
    discount: null, total_amount: null, my_pay_total: null,
    works: [makeMechanicWork(), makeMechanicWork({ id: 'w2', name: 'Рычаг', is_mine: false, mechanic_name: 'Морозов', parts: [] }),
      makeMechanicWork({ id: 'w3', name: 'Мойка', is_mine: false, mechanic_name: null, parts: [] })],
    ...over,
  };
}

/** The same visit with prices on: own work 2 × 1 000, part 450, own pay 1 000. */
export function pricedMechanicVisit(over: Partial<MechanicVisit> = {}): MechanicVisit {
  const base = makeMechanicVisit();
  return {
    ...base, discount: 0, total_amount: 3450, my_pay_total: 1000,
    works: [
      makeMechanicWork({ hourly_rate: 1000, amount: 2000, my_pay: 1000,
        parts: [{ name: 'Фильтр', article_number: null, quantity: 1, availability_status: 'in_stock', unit_price: 450, amount: 450 }] }),
      makeMechanicWork({ id: 'w2', name: 'Рычаг', is_mine: false, mechanic_name: 'Морозов', hourly_rate: 1000, amount: 1000, parts: [] }),
    ],
    ...over,
  };
}
```

`web/src/screens/MechanicVisitScreen.test.tsx`:

```tsx
import { screen } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { renderApp } from '../test/render';
import { makeMechanicVisit, pricedMechanicVisit } from '../test/fixtures';
import { server } from '../test/server';

function serve(body: unknown) {
  server.use(http.get('/api/visits/v1/mechanic-view', () => HttpResponse.json(body)));
}

test('without prices: works and assignees, no money, no client', async () => {
  serve(makeMechanicVisit());
  renderApp('/my/visit/v1', { as: 'mechanic' });
  expect(await screen.findByText('Замена масла ДВС · моя')).toBeInTheDocument();
  expect(screen.getByText(/Морозов/)).toBeInTheDocument();
  expect(screen.getByText(/без исполнителя/)).toBeInTheDocument();
  expect(screen.getByText(/Мастер: Орлов Пётр/)).toBeInTheDocument();
  expect(screen.queryByText(/₽/)).not.toBeInTheDocument();
  expect(screen.queryByText(/Клиент:/)).not.toBeInTheDocument();
});

test('with prices and client data', async () => {
  serve(pricedMechanicVisit({ client_name: 'Петров Иван', client_phone: '+7 900 123-45-67', vin: 'XW8ZZZ61ZJG000001' }));
  renderApp('/my/visit/v1', { as: 'mechanic' });
  expect(await screen.findByText('Итого по заезду')).toBeInTheDocument();
  expect(screen.getByText('3 450 ₽')).toBeInTheDocument();
  expect(screen.getByText('Клиент: Петров Иван')).toBeInTheDocument();
  expect(screen.getByText('Телефон: +7 900 123-45-67')).toBeInTheDocument();
  expect(screen.getByText('VIN: XW8ZZZ61ZJG000001')).toBeInTheDocument();
  expect(screen.getByText('Ваш заработок по заезду').nextSibling).toHaveTextContent('1 000 ₽');
});

test('prices on but no pay scheme', async () => {
  serve(pricedMechanicVisit({ my_pay_total: null, works: [{ ...pricedMechanicVisit().works[0], my_pay: null }] }));
  renderApp('/my/visit/v1', { as: 'mechanic' });
  expect(await screen.findByText('Итого по заезду')).toBeInTheDocument();
  expect(screen.getAllByText('схема оплаты не задана')).toHaveLength(2);
});

test('done works open the visit card for a mechanic', async () => {
  server.use(http.get('/api/work-items/mine/done', () => HttpResponse.json({
    items: [{ id: 'w1', visit_id: 'v1', name: 'Замена масла ДВС', plate_number: 'А123ВС77', make_model: 'Toyota Camry',
      visit_status: 'issued', visit_date: '2026-10-10T09:00:00+00:00', closed_at: '2026-10-11T09:00:00+00:00', norm_hours: 2 }],
    count: 1, total_norm_hours: 2, has_more: false,
  })));
  renderApp('/my/done', { as: 'mechanic' });
  expect((await screen.findByText('Замена масла ДВС')).closest('a')).toHaveAttribute('href', '/my/visit/v1');
});
```

`web/src/screens/WorkScreen.test.tsx` — в `beforeEach` добавить обработчик по умолчанию:

```tsx
  server.use(http.get('/api/visits/v1/mechanic-view', () => HttpResponse.json(makeMechanicVisit())));
```

(импорт `makeMechanicVisit, pricedMechanicVisit` из `../test/fixtures`) и два теста:

```tsx
test('mechanic opens the visit card from the work', async () => {
  server.use(http.get('/api/work-items/mine', () => HttpResponse.json([makeMyWork()])));
  renderApp('/visits/v1/works/w1', { as: 'mechanic' });
  expect(await screen.findByRole('link', { name: 'Карточка заезда' })).toHaveAttribute('href', '/my/visit/v1');
  expect(screen.queryByText('Стоимость работы')).not.toBeInTheDocument();
});

test('mechanic sees the work price and own pay when prices are on', async () => {
  server.use(
    http.get('/api/work-items/mine', () => HttpResponse.json([makeMyWork()])),
    http.get('/api/visits/v1/mechanic-view', () => HttpResponse.json(pricedMechanicVisit())),
  );
  renderApp('/visits/v1/works/w1', { as: 'mechanic' });
  expect(await screen.findByText('Стоимость работы')).toBeInTheDocument();
  expect(screen.getByText('2 000 ₽')).toBeInTheDocument();
  expect(screen.getByText('Ваш заработок').nextSibling).toHaveTextContent('1 000 ₽');
});
```

Если `makeMyWork()` по умолчанию имеет `id` не `'w1'` или `visit_id` не `'v1'` — передать `makeMyWork({ id: 'w1', visit_id: 'v1' })`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd web && npx vitest run src/screens/MechanicVisitScreen.test.tsx src/screens/WorkScreen.test.tsx`
Expected: FAIL — нет маршрута `/my/visit/:visitId`, нет ссылки «Карточка заезда».

- [ ] **Step 3: Write the implementation**

`web/src/api/types.ts` — добавить:

```ts
export interface MechanicPart {
  name: string;
  article_number: string | null;
  quantity: number;
  availability_status: string;
  unit_price: number | null;
  amount: number | null;
}

export interface MechanicWork {
  id: string;
  name: string;
  category: WorkCategory;
  status: WorkItemStatus;
  mechanic_name: string | null;
  is_mine: boolean;
  norm_hours: number;
  hourly_rate: number | null;
  amount: number | null;
  my_pay: number | null;
  parts: MechanicPart[];
}

/** The visit card for a mechanic: fields the admin's settings hide are null. */
export interface MechanicVisit {
  id: string;
  status: VisitStatus;
  created_at: string;
  mileage_at_intake: number;
  plate_number: string;
  make_model: string;
  master_name: string;
  client_name: string | null;
  client_phone: string | null;
  client_telegram_username: string | null;
  vin: string | null;
  discount: number | null;
  total_amount: number | null;
  my_pay_total: number | null;
  works: MechanicWork[];
}
```

`web/src/api/endpoints.ts` — в `visitsApi` после `lines`:

```ts
  mechanicView: (id: string) => api.get<MechanicVisit>(`/visits/${id}/mechanic-view`),
```

`web/src/screens/MechanicVisitScreen.tsx`:

```tsx
import { useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { visitsApi } from '../api/endpoints';
import type { MechanicWork } from '../api/types';
import { formatHours, formatKm, formatRub } from '../lib/format';
import { Loadable } from '../ui/Loadable';
import { Plate } from '../ui/Plate';
import { ScreenHeader } from '../ui/ScreenHeader';
import { StatusTag } from '../ui/StatusTag';

const NO_SCHEME = 'схема оплаты не задана';

export function payText(pay: number | null): string {
  return pay === null ? NO_SCHEME : formatRub(pay);
}

export function MechanicVisitScreen() {
  const { visitId = '' } = useParams();
  const query = useQuery({ queryKey: ['mechanicVisit', visitId], queryFn: () => visitsApi.mechanicView(visitId) });
  return (
    <>
      <ScreenHeader title="Заезд" back />
      <Loadable query={query}>
        {(v) => {
          const prices = v.total_amount !== null;
          return (
            <div className="stack">
              <div className="card">
                <div className="row">
                  <Plate value={v.plate_number} />
                  <StatusTag kind="visit" status={v.status} />
                </div>
                <span>{v.make_model}</span>
                <span className="hint">Пробег: {formatKm(v.mileage_at_intake)} · Мастер: {v.master_name}</span>
                {v.client_name && <span className="hint">Клиент: {v.client_name}</span>}
                {v.client_phone && <span className="hint">Телефон: {v.client_phone}</span>}
                {v.vin && <span className="hint mono">VIN: {v.vin}</span>}
              </div>
              <h2 className="section-title">Работы</h2>
              {v.works.map((w) => <WorkCard key={w.id} w={w} prices={prices} />)}
              {prices && (
                <div className="card">
                  {v.discount ? (
                    <div className="row"><span>Скидка</span><span className="mono">−{formatRub(v.discount)}</span></div>
                  ) : null}
                  <div className="row"><b>Итого по заезду</b><b className="mono">{formatRub(v.total_amount!)}</b></div>
                  <div className="row"><span>Ваш заработок по заезду</span><span className="mono">{payText(v.my_pay_total)}</span></div>
                </div>
              )}
            </div>
          );
        }}
      </Loadable>
    </>
  );
}

function WorkCard({ w, prices }: { w: MechanicWork; prices: boolean }) {
  return (
    <div className="card">
      <div className="row">
        <b>{w.is_mine ? `${w.name} · моя` : w.name}</b>
        <StatusTag kind="work" status={w.status} />
      </div>
      <span className="hint">{w.mechanic_name ?? 'без исполнителя'} · {formatHours(w.norm_hours)}</span>
      {prices && w.amount !== null && (
        <div className="row"><span className="hint">Стоимость</span><span className="mono">{formatRub(w.amount)}</span></div>
      )}
      {prices && w.is_mine && (
        <div className="row"><span>Ваш заработок</span><span className="mono">{payText(w.my_pay)}</span></div>
      )}
      {w.parts.map((p, i) => (
        <div key={i} className="part-row hint">
          <span>🔩 {p.name} × {p.quantity}</span>
          {p.amount !== null && <span className="mono">{formatRub(p.amount)}</span>}
        </div>
      ))}
    </div>
  );
}
```

`web/src/routes.tsx` — импорт и маршрут после `/my/done`:

```tsx
        <Route path="/my/visit/:visitId" element={<RoleGate roles={['mechanic']}><MechanicVisitScreen /></RoleGate>} />
```

`web/src/screens/WorkScreen.tsx`:
- импорт `payText` из `./MechanicVisitScreen`;
- после `const lines = useQuery(...)` добавить:

```tsx
  const view = useQuery({ queryKey: ['mechanicVisit', visitId], queryFn: () => visitsApi.mechanicView(visitId), enabled: isMechanic });
  const mine = view.data?.works.find((x) => x.id === itemId);
```

- в `invalidate` добавить `['mechanicVisit', visitId]`;
- сразу после первого `<div className="card">…</div>` (карточка работы) вставить:

```tsx
              {isMechanic && mine && mine.amount !== null && (
                <div className="card">
                  <div className="row"><span>Стоимость работы</span><span className="mono">{formatRub(mine.amount)}</span></div>
                  {mine.parts.map((p, i) => (
                    <div key={i} className="part-row hint">
                      <span>🔩 {p.name} × {p.quantity}</span>
                      {p.amount !== null && <span className="mono">{formatRub(p.amount)}</span>}
                    </div>
                  ))}
                  <div className="row"><span>Ваш заработок</span><span className="mono">{payText(mine.my_pay)}</span></div>
                </div>
              )}
              {isMechanic && <Link className="btn btn-block" to={`/my/visit/${visitId}`}>Карточка заезда</Link>}
```

`web/src/screens/DoneWorksScreen.tsx` — взять `const { user } = useAuth();` (импорт `useAuth` из `../auth/AuthProvider`) и у `<Card key={w.id}>` добавить `to={user!.role === 'mechanic' ? `/my/visit/${w.visit_id}` : undefined}`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd web && npx vitest run src/screens/MechanicVisitScreen.test.tsx src/screens/WorkScreen.test.tsx`
Expected: все зелёные (включая старый «mechanic sees only status steps»).

- [ ] **Step 5: Full web suite and commit**

Run: `cd web && npx vitest run && npx tsc --noEmit -p .` — всё зелёное.

```bash
git add web/src
git commit -m "feat(web): mechanic's visit card; work price and own pay on the work screen; done works link to the card"
```

---

### Task 8: Бот — «⚙️ Настройки»: переключатели и оплата механиков

**Files:**
- Modify: `bot/api_client.py` (4 метода), `bot/actions.py` (`SETTING`, `PAY`), `bot/states.py` (`PayStates`)
- Create: `bot/handlers/admin_settings.py`
- Modify: `bot/handlers/menu.py` (пункт у админа), `bot/main.py` (импорт и `include_router`)
- Test: `tests/bot/test_admin_settings.py`; Modify: `tests/bot/test_start_handler.py` (меню админа), `tests/bot/test_callback_sizes.py` (`SCREEN_ARGS` и моки)

**Interfaces:**
- Consumes: `/settings`, `/settings/pay`, `/settings/pay/{id}` (Task 2); `nav.screen`, `nav.go_data`, `nav.top_args`, `nav.refresh`; `wizard.step/start/goto/reprompt/finish`; `encode_id/decode_id`; `format_number` из `bot/formatting.py`.
- Produces: `ApiClient.get_settings() -> dict`, `update_settings(**changes) -> dict`, `list_mechanic_pay() -> list[dict]`, `set_mechanic_pay(user_id, scheme, value) -> dict`; экраны `settings`, `pay`; `pay_label(m: dict) -> str`.

- [ ] **Step 1: Write the failing tests**

`tests/bot/test_admin_settings.py`:

```python
from unittest.mock import AsyncMock

import pytest

from bot import nav
from bot.api_client import ApiForbidden
from bot.callback_ids import encode_id
from bot.handlers.admin_settings import (
    choose_scheme, pay_label, receive_value, render_pay, render_settings, start_pay, toggle_setting,
)
from bot.states import PayStates
from tests.bot.helpers import ADMIN, MASTER, MECHANIC, buttons, fsm_context, make_callback, make_message, on_screens, shown

M1 = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"
OFF = {"mechanic_sees_prices": False, "mechanic_sees_client_name": False,
       "mechanic_sees_client_phone": False, "mechanic_sees_vin": True}
PAY = [{"user_id": M1, "full_name": "Морозов", "pay_scheme": "percent", "pay_value": 40.0}]


def _api():
    api = AsyncMock()
    api.get_settings.return_value = OFF
    api.list_mechanic_pay.return_value = PAY
    return api


async def test_settings_screen_shows_switch_states():
    _, markup = await render_settings(_api(), ADMIN, {})

    assert buttons(markup) == [
        ("⬜ Цены и заработок", "act:set:prices"), ("⬜ Имя клиента", "act:set:name"),
        ("⬜ Телефон клиента", "act:set:phone"), ("✅ VIN / номер кузова", "act:set:vin"),
        ("💰 Оплата механиков", nav.go_data("pay")),
    ]


async def test_settings_are_admin_only():
    for user in (MASTER, MECHANIC):
        with pytest.raises(ApiForbidden):
            await render_settings(_api(), user, {})


async def test_toggle_flips_the_setting_and_redraws():
    state = fsm_context()
    await on_screens(state, ("settings", {}))
    api = _api()

    await toggle_setting(make_callback("act:set:vin"), state, api=api, user=ADMIN)

    api.update_settings.assert_awaited_once_with(mechanic_sees_vin=False)


def test_pay_labels():
    assert pay_label({"pay_scheme": "percent", "pay_value": 40.0}) == "40% от работы"
    assert pay_label({"pay_scheme": "percent", "pay_value": 12.5}) == "12,5% от работы"
    assert pay_label({"pay_scheme": "per_hour", "pay_value": 700.0}) == "700 ₽ за н/ч"
    assert pay_label({"pay_scheme": "full", "pay_value": None}) == "вся стоимость"
    assert pay_label({"pay_scheme": None, "pay_value": None}) == "схема не задана"


async def test_pay_screen_lists_mechanics():
    text, markup = await render_pay(_api(), ADMIN, {})

    assert text.startswith("💰 Оплата механиков")
    assert buttons(markup) == [("Морозов · 40% от работы", f"act:pay:{encode_id(M1)}")]


async def _pay_wizard(state, api):
    await on_screens(state, ("settings", {}), ("pay", {}))
    callback = make_callback(f"act:pay:{encode_id(M1)}")
    await start_pay(callback, state, api=api, user=ADMIN)
    return callback


async def test_percent_with_a_comma_saves_and_returns_to_the_list():
    state, api = fsm_context(), _api()
    callback = await _pay_wizard(state, api)
    assert shown(callback)[0] == "Схема оплаты: Морозов"

    await choose_scheme(make_callback("pay_scheme:percent"), state, api=api, user=ADMIN)
    assert await state.get_state() == PayStates.waiting_for_value.state
    message = make_message("12,5")
    await receive_value(message, state, api=api, user=ADMIN)

    api.set_mechanic_pay.assert_awaited_once_with(M1, "percent", 12.5)
    assert await state.get_state() is None
    assert shown(message)[0].startswith("Сохранено\n\n💰 Оплата механиков")


async def test_full_saves_without_asking_a_number():
    state, api = fsm_context(), _api()
    await _pay_wizard(state, api)

    await choose_scheme(make_callback("pay_scheme:full"), state, api=api, user=ADMIN)

    api.set_mechanic_pay.assert_awaited_once_with(M1, "full", None)


async def test_wrong_number_reprompts():
    state, api = fsm_context(), _api()
    await _pay_wizard(state, api)
    await choose_scheme(make_callback("pay_scheme:percent"), state, api=api, user=ADMIN)

    for text in ("abc", "150", "0"):
        message = make_message(text)
        await receive_value(message, state, api=api, user=ADMIN)
        assert shown(message)[0].startswith("Процент — число больше 0 и не больше 100")
    api.set_mechanic_pay.assert_not_awaited()


async def test_pay_refused_for_master():
    state = fsm_context()
    await on_screens(state, ("pay", {}))
    callback = make_callback(f"act:pay:{encode_id(M1)}")

    await start_pay(callback, state, api=_api(), user=MASTER)

    callback.answer.assert_awaited_once_with("Недостаточно прав")
```

`tests/bot/test_start_handler.py` — в `test_admin_menu_adds_own_works_and_staff` в ожидаемый список кнопок после `("👥 Добавить сотрудника", "wiz:new_staff")` добавить `("⚙️ Настройки", "go:settings")`.

`tests/bot/test_callback_sizes.py` — в `_api()`:

```python
    api.get_settings.return_value = {"mechanic_sees_prices": True, "mechanic_sees_client_name": True,
                                     "mechanic_sees_client_phone": True, "mechanic_sees_vin": True}
    api.list_mechanic_pay.return_value = [{"user_id": M, "full_name": "Механик с очень длинным именем",
                                           "pay_scheme": "per_hour", "pay_value": 12345.5}]
```

и в `SCREEN_ARGS` добавить `"settings": {}, "pay": {}`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/bot/test_admin_settings.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'bot.handlers.admin_settings'`.

- [ ] **Step 3: Write the implementation**

`bot/api_client.py` — после `get_my_stats`:

```python
    async def get_settings(self) -> dict:
        return await self.get("/settings")

    async def update_settings(self, **changes) -> dict:
        return await self.patch("/settings", json=changes)

    async def list_mechanic_pay(self) -> list[dict]:
        return await self.get("/settings/pay")

    async def set_mechanic_pay(self, user_id: str, scheme: str | None, value: float | None) -> dict:
        return await self.patch(f"/settings/pay/{user_id}", json={"pay_scheme": scheme, "pay_value": value})
```

`bot/actions.py` — в конец:

```python
SETTING = "act:set"  # + ":<prices|name|phone|vin>" flips that mechanic visibility switch
PAY = "act:pay"  # + ":<encoded mechanic id>" starts the pay scheme wizard
```

`bot/states.py` — в конец:

```python
class PayStates(StatesGroup):
    choosing_scheme = State()
    waiting_for_value = State()
```

`bot/handlers/admin_settings.py`:

```python
"""Admin settings: what mechanics see (switches) and each mechanic's pay scheme (a short wizard)."""
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot import actions, nav, wizard
from bot.api_client import ApiClient, ApiForbidden
from bot.callback_ids import decode_id, encode_id
from bot.formatting import format_number
from bot.states import PayStates

router = Router()

# short callback key, setting key, label
TOGGLES = [
    ("prices", "mechanic_sees_prices", "Цены и заработок"),
    ("name", "mechanic_sees_client_name", "Имя клиента"),
    ("phone", "mechanic_sees_client_phone", "Телефон клиента"),
    ("vin", "mechanic_sees_vin", "VIN / номер кузова"),
]
SCHEMES = [("percent", "Процент от работы"), ("per_hour", "Фикс за нормо-час"), ("full", "Вся стоимость"), ("none", "Не задана")]
FORBIDDEN = "Недостаточно прав"


def _num(value: float) -> str:
    return format_number(value) if float(value).is_integer() else f"{value:g}".replace(".", ",")


def pay_label(m: dict) -> str:
    scheme, value = m["pay_scheme"], m["pay_value"]
    if scheme == "percent":
        return f"{_num(value)}% от работы"
    if scheme == "per_hour":
        return f"{_num(value)} ₽ за н/ч"
    if scheme == "full":
        return "вся стоимость"
    return "схема не задана"


@nav.screen("settings")
async def render_settings(api: ApiClient, user: dict, args: dict) -> nav.Rendered:
    if user["role"] != "admin":
        raise ApiForbidden(FORBIDDEN)
    current = await api.get_settings()
    builder = InlineKeyboardBuilder()
    for short, key, label in TOGGLES:
        builder.button(text=f"{'✅' if current[key] else '⬜'} {label}", callback_data=f"{actions.SETTING}:{short}")
    builder.button(text="💰 Оплата механиков", callback_data=nav.go_data("pay"))
    builder.adjust(1)
    return "⚙️ Настройки\nЧто видят механики — нажмите, чтобы переключить.", builder.as_markup()


@router.callback_query(F.data.startswith(f"{actions.SETTING}:"))
async def toggle_setting(callback: CallbackQuery, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    if user["role"] != "admin":
        await callback.answer(FORBIDDEN)
        return
    if await nav.top_args(callback, state, "settings") is None:
        return
    key = {short: key for short, key, _ in TOGGLES}.get(callback.data.rsplit(":", 1)[1])
    if key is None:
        await callback.answer()
        return
    current = await api.get_settings()
    await api.update_settings(**{key: not current[key]})
    await nav.refresh(callback, state, api, user)


@nav.screen("pay")
async def render_pay(api: ApiClient, user: dict, args: dict) -> nav.Rendered:
    if user["role"] != "admin":
        raise ApiForbidden(FORBIDDEN)
    mechanics = await api.list_mechanic_pay()
    builder = InlineKeyboardBuilder()
    for m in mechanics:
        builder.button(text=f"{m['full_name']} · {pay_label(m)}", callback_data=f"{actions.PAY}:{encode_id(m['user_id'])}")
    builder.adjust(1)
    text = "💰 Оплата механиков\nВыберите механика, чтобы изменить схему." if mechanics else "💰 Оплата механиков\nМехаников нет."
    return text, builder.as_markup()


@wizard.step(PayStates.choosing_scheme)
async def scheme_prompt(state: FSMContext, api: ApiClient, user: dict):
    builder = InlineKeyboardBuilder()
    for scheme, label in SCHEMES:
        builder.button(text=label, callback_data=f"pay_scheme:{scheme}")
    builder.adjust(1)
    return f"Схема оплаты: {(await state.get_data())['pay_name']}", builder.as_markup()


@wizard.step(PayStates.waiting_for_value)
async def value_prompt(state: FSMContext, api: ApiClient, user: dict):
    if (await state.get_data())["pay_scheme"] == "percent":
        return "Введите процент от стоимости работы (например, 40):", None
    return "Введите ставку в рублях за нормо-час (например, 700):", None


@router.callback_query(F.data.startswith(f"{actions.PAY}:"))
async def start_pay(callback: CallbackQuery, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    if user["role"] != "admin":
        await callback.answer(FORBIDDEN)
        return
    if await nav.top_args(callback, state, "pay") is None:
        return
    user_id = decode_id(callback.data.rsplit(":", 1)[1])
    mechanic = next((m for m in await api.list_mechanic_pay() if str(m["user_id"]) == user_id), None)
    if mechanic is None:
        await callback.answer("Механик не найден")
        return
    await wizard.start(callback, state, api, user, "pay", PayStates.choosing_scheme,
                       pay_user_id=user_id, pay_name=mechanic["full_name"])


async def _save(event: nav.Event, state: FSMContext, api: ApiClient, user: dict, scheme: str | None, value: float | None):
    await api.set_mechanic_pay((await state.get_data())["pay_user_id"], scheme, value)
    await wizard.finish(state)
    await nav.refresh(event, state, api, user, notice="Сохранено")


@router.callback_query(PayStates.choosing_scheme, F.data.startswith("pay_scheme:"))
async def choose_scheme(callback: CallbackQuery, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    scheme = callback.data.split(":", 1)[1]
    if scheme in ("percent", "per_hour"):
        await state.update_data(pay_scheme=scheme)
        await wizard.goto(callback, state, api, user, PayStates.waiting_for_value)
        return
    await _save(callback, state, api, user, None if scheme == "none" else scheme, None)


@router.message(PayStates.waiting_for_value)
async def receive_value(message: Message, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    scheme = (await state.get_data())["pay_scheme"]
    try:
        value = float((message.text or "").strip().replace(",", "."))
    except ValueError:
        value = None
    if scheme == "percent" and (value is None or not 0 < value <= 100):
        await wizard.reprompt(message, state, api, user, "Процент — число больше 0 и не больше 100, например 40.")
        return
    if scheme == "per_hour" and (value is None or value <= 0):
        await wizard.reprompt(message, state, api, user, "Ставка — число больше нуля, например 700.")
        return
    await _save(message, state, api, user, scheme, value)
```

Проверить в `bot/nav.py`, что `refresh(..., notice=...)` выводит уведомление первой строкой и пустой строкой после (как «Сотрудник создан: …\n\nГлавное меню» в `nav.home`); тест `test_percent_with_a_comma_saves_and_returns_to_the_list` на это опирается.

`bot/handlers/menu.py` — в `_ADMIN_ITEMS` после `("👥 Добавить сотрудника", actions.NEW_STAFF),`:

```python
    ("⚙️ Настройки", nav.go_data("settings")),
```

`bot/main.py` — в импорт `from bot.handlers import (...)` добавить `admin_settings,` (по алфавиту, после `admin,`) и в `setup_routers` после `dp.include_router(admin.router)`:

```python
    dp.include_router(admin_settings.router)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/bot -q`
Expected: всё зелёное, включая `test_callback_sizes.py` и `test_start_handler.py`.

- [ ] **Step 5: Full suite and commit**

Run: `uv run pytest -q` — всё зелёное.

```bash
git add bot tests/bot
git commit -m "feat(bot): admin «⚙️ Настройки» — mechanic visibility switches and pay scheme wizard"
```

---

### Task 9: Бот — «🚗 Карточка заезда» для механика

**Files:**
- Modify: `bot/api_client.py` (`get_mechanic_view`), `bot/handlers/mechanic.py` (экран `mech_visit`), `bot/handlers/work_items.py` (кнопка у механика)
- Test: `tests/bot/test_mechanic_visit.py`; Modify: `tests/bot/test_visit_screens.py` (ожидание кнопок механика), `tests/bot/test_callback_sizes.py`

**Interfaces:**
- Consumes: `GET /visits/{id}/mechanic-view` (Task 4); `format_value` из `bot/handlers/stats.py`; `format_hours`, `format_number` из `bot/formatting.py`; `work_item_icon` из `bot/work_item_status.py`.
- Produces: `ApiClient.get_mechanic_view(visit_id) -> dict`; экран `mech_visit` (params `visit_id`).

- [ ] **Step 1: Write the failing tests**

`tests/bot/test_mechanic_visit.py`:

```python
from unittest.mock import AsyncMock

from bot.handlers.mechanic import render_mech_visit
from tests.bot.helpers import MECHANIC

VISIT = "11111111-1111-1111-1111-111111111111"
PART = {"name": "Фильтр", "article_number": None, "quantity": 1, "availability_status": "in_stock", "unit_price": None, "amount": None}


def _view(**over):
    base = {
        "id": VISIT, "status": "in_progress", "created_at": "2026-10-10T09:00:00+00:00", "mileage_at_intake": 120000,
        "plate_number": "А123ВС77", "make_model": "Toyota Camry", "master_name": "Орлов",
        "client_name": None, "client_phone": None, "client_telegram_username": None, "vin": None,
        "discount": None, "total_amount": None, "my_pay_total": None,
        "works": [
            {"id": "w1", "name": "Масло", "category": "maintenance", "status": "in_progress", "mechanic_name": "Сидоров",
             "is_mine": True, "norm_hours": 2, "hourly_rate": None, "amount": None, "my_pay": None, "parts": [PART]},
            {"id": "w2", "name": "Мойка", "category": "other", "status": "not_ready", "mechanic_name": None,
             "is_mine": False, "norm_hours": 0.5, "hourly_rate": None, "amount": None, "my_pay": None, "parts": []},
        ],
    }
    return base | over


async def test_card_without_prices():
    api = AsyncMock()
    api.get_mechanic_view.return_value = _view()

    text, _ = await render_mech_visit(api, MECHANIC, {"visit_id": VISIT})

    api.get_mechanic_view.assert_awaited_once_with(VISIT)
    assert text.splitlines()[:2] == ["🚗 А123ВС77 · Toyota Camry", "Пробег: 120 000 км · Мастер: Орлов"]
    assert "Масло · моя" in text and "без исполнителя" in text and "🔩 Фильтр × 1" in text
    assert "₽" not in text and "Клиент" not in text


async def test_card_with_prices_client_and_no_scheme():
    api = AsyncMock()
    view = _view(client_name="Петров", client_phone="+7 900 123-45-67", vin="X" * 17,
                 discount=0, total_amount=3450, my_pay_total=None)
    view["works"][0] |= {"hourly_rate": 1000, "amount": 2000, "my_pay": None,
                         "parts": [PART | {"unit_price": 450, "amount": 450}]}
    api.get_mechanic_view.return_value = view

    text, _ = await render_mech_visit(api, MECHANIC, {"visit_id": VISIT})

    assert "Клиент: Петров" in text and "Телефон: +7 900 123-45-67" in text and f"VIN: {'X' * 17}" in text
    assert "2 000 ₽" in text and "🔩 Фильтр × 1 · 450 ₽" in text
    assert "Итого по заезду: 3 450 ₽" in text
    assert "Ваш заработок по заезду: схема оплаты не задана" in text


async def test_card_with_own_pay():
    api = AsyncMock()
    view = _view(discount=0, total_amount=3450, my_pay_total=1000)
    view["works"][0] |= {"hourly_rate": 1000, "amount": 2000, "my_pay": 1000}
    api.get_mechanic_view.return_value = view

    text, _ = await render_mech_visit(api, MECHANIC, {"visit_id": VISIT})

    assert "Ваш заработок: 1 000 ₽" in text and "Ваш заработок по заезду: 1 000 ₽" in text
```

`tests/bot/test_visit_screens.py` — в `test_work_screen_for_mechanic_has_only_status_buttons_and_no_visit_call` (импорт `from bot import nav`, если его нет) заменить ожидание кнопок на:

```python
    assert buttons(markup) == [("→ В работе", "act:wstatus:in_progress"), ("🚗 Карточка заезда", nav.go_data("mech_visit", VISIT))]
```

`tests/bot/test_callback_sizes.py` — в `_api()`:

```python
    api.get_mechanic_view.return_value = {
        "plate_number": "А1", "make_model": "X Y", "mileage_at_intake": 1, "master_name": "М", "client_name": None,
        "client_phone": None, "vin": None, "discount": None, "total_amount": None, "my_pay_total": None, "works": [],
    }
```

и в `SCREEN_ARGS` добавить `"mech_visit": {"visit_id": V}`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/bot/test_mechanic_visit.py -q`
Expected: FAIL — `ImportError: cannot import name 'render_mech_visit'`.

- [ ] **Step 3: Write the implementation**

`bot/api_client.py` — после `list_my_done_work_items`:

```python
    async def get_mechanic_view(self, visit_id: str) -> dict:
        return await self.get(f"/visits/{visit_id}/mechanic-view")
```

`bot/handlers/mechanic.py` — импорты:

```python
from bot.formatting import format_date, format_hours, format_number
from bot.handlers.stats import format_value
```

и в конец файла:

```python
NO_SCHEME = "схема оплаты не задана"


def _rub(value) -> str:
    return format_value(value, "rub")


def _pay(value) -> str:
    return NO_SCHEME if value is None else _rub(value)


@nav.screen("mech_visit", params=("visit_id",))
async def render_mech_visit(api: ApiClient, user: dict, args: dict) -> nav.Rendered:
    """The visit card for a mechanic: the server already left out what the admin hides."""
    v = await api.get_mechanic_view(args["visit_id"])
    prices = v["total_amount"] is not None
    lines = [
        f"🚗 {v['plate_number']} · {v['make_model']}",
        f"Пробег: {format_number(v['mileage_at_intake'])} км · Мастер: {v['master_name']}",
    ]
    for label, key in (("Клиент", "client_name"), ("Телефон", "client_phone"), ("VIN", "vin")):
        if v.get(key):
            lines.append(f"{label}: {v[key]}")
    for w in v["works"]:
        lines += ["", f"{work_item_icon(w['status'])} {w['name']}{' · моя' if w['is_mine'] else ''}"]
        detail = f"   {w['mechanic_name'] or 'без исполнителя'} · {format_hours(w['norm_hours'])}"
        lines.append(detail + (f" · {_rub(w['amount'])}" if prices and w["amount"] is not None else ""))
        if prices and w["is_mine"]:
            lines.append(f"   Ваш заработок: {_pay(w['my_pay'])}")
        for p in w["parts"]:
            lines.append(f"   🔩 {p['name']} × {p['quantity']}" + (f" · {_rub(p['amount'])}" if p["amount"] is not None else ""))
    if prices:
        lines.append("")
        if v["discount"]:
            lines.append(f"Скидка: {_rub(v['discount'])}")
        lines += [f"Итого по заезду: {_rub(v['total_amount'])}", f"Ваш заработок по заезду: {_pay(v['my_pay_total'])}"]
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=[])
```

`bot/handlers/work_items.py` — в `render_work` после цикла кнопок статусов:

```python
    if not staff:
        builder.button(text="🚗 Карточка заезда", callback_data=nav.go_data("mech_visit", args["visit_id"]))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/bot -q`
Expected: всё зелёное.

- [ ] **Step 5: Full suite and commit**

Run: `uv run pytest -q` — всё зелёное.

```bash
git add bot tests/bot
git commit -m "feat(bot): mechanic's «🚗 Карточка заезда» from the work screen"
```

---

### Task 10: Живая проверка

**Files:** нет изменений кода (только исправления найденного, отдельными коммитами с тестом).

- [ ] **Step 1: Поднять стек из ветки**

Run: `docker compose up -d --build api bot && sleep 8 && docker compose ps && docker compose logs --tail 3 bot`
Expected: api `healthy`, в логе бота `Start polling`.

- [ ] **Step 2: API на демо-данных**

```bash
KEY=$(grep ^INTERNAL_API_KEY= .env | cut -d= -f2-)
ADMIN=$(docker compose exec -T postgres psql -U crm -d crm -tAc "select id from users where full_name='Иван Иванов'")
MECH=$(docker compose exec -T postgres psql -U crm -d crm -tAc "select id from users where full_name='Потапом Витя'")
H() { echo -H "X-Service-Key: $KEY" -H "X-User-Id: $1"; }
curl -s $(H $MECH) "http://localhost:8000/stats/mine?period=year" | python3 -c "import json,sys; print([k['key'] for k in json.load(sys.stdin)['kpis']])"
curl -s -X PATCH $(H $ADMIN) -H 'Content-Type: application/json' -d '{"mechanic_sees_prices": true}' http://localhost:8000/settings
curl -s -X PATCH $(H $ADMIN) -H 'Content-Type: application/json' -d '{"pay_scheme": "percent", "pay_value": 40}' "http://localhost:8000/settings/pay/$MECH"
curl -s $(H $MECH) "http://localhost:8000/stats/mine?period=year" | python3 -m json.tool | head -30
```

Expected: первый вывод — без `earned`; после включения — `earned`/`expected` в ₽, правдоподобные числа.

- [ ] **Step 3: Скриншоты веба (390px)**

Через Vite (`cd web && npx vite --host`, в фоне) и playwright-core из scratchpad: под админом открыть «Ещё → Настройки» и снять экран; под механиком «Потапом Витя» открыть любую свою работу → «Карточка заезда» и «Статистика» (год). Проверить глазами: переключатели читаются, цены и «Ваш заработок» на месте, нет горизонтальной прокрутки (`document.documentElement.scrollWidth <= 390`). Затем выключить цены (`PATCH /settings {"mechanic_sees_prices": false}`) и убедиться, что у механика ₽ исчезли везде.

- [ ] **Step 4: Вернуть демо-настройки и итоговый прогон**

Run: `curl -s -X PATCH $(H $ADMIN) -H 'Content-Type: application/json' -d '{"mechanic_sees_prices": false}' http://localhost:8000/settings` (по умолчанию механики не видят цен; схему 40 % у «Потапом Витя» оставить — владелец увидит её в настройках).
Run: `uv run pytest -q && cd web && npx vitest run && npx tsc --noEmit -p .`
Expected: всё зелёное. Остановить Vite.
