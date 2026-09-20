# CRM Telegram Bot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the aiogram 3 Telegram bot (staff-only: ADMIN/MASTER/MECHANIC) as a thin HTTP client over the existing CRM backend API, covering the full role-scenario set from the design spec, plus the three small backend additions the bot needs first.

**Architecture:** Two processes sharing one repo/venv. Backend (`app/`) gains two read endpoints and a real Telegram-sending `NotificationSender` implementation. A new top-level `bot/` package runs as a separate long-polling aiogram process: a middleware resolves the Telegram user to a CRM `User` on every update, a thin `ApiClient` wraps all HTTP calls to the backend (auth header injection + error-to-text mapping in one place), and per-domain handler modules implement FSM wizards and inline-keyboard flows for clients/vehicles/visits/work-items/part-items/documents/search/consent/admin/mechanic scenarios.

**Tech Stack:** Python 3.12, aiogram 3 (bot + backend's outbound sending), FastAPI/SQLAlchemy/PostgreSQL (existing backend), httpx (bot's HTTP client to the backend), pytest + pytest-asyncio, unittest.mock for handler/API-client tests.

**Spec:** `docs/superpowers/specs/2026-09-19-crm-bot-design.md` (bot design — read this first, it has full context on roles, UX, and error-handling conventions). Backend conventions also draw from `docs/superpowers/specs/2026-09-15-crm-backend-design.md`.

## Global Constraints

- Bot has no direct DB access — every action goes through the CRM HTTP API, same principle as the (future) web/Mini App (spec: "Архитектура бота").
- Role checks are never duplicated in the bot — the bot only hides menu items a role can't use; `require_role` on the backend is the single source of truth (spec: "Аутентификация / middleware").
- FSM storage is aiogram `MemoryStorage` — no Redis on MVP, single bot instance (spec: "UX: меню + FSM-визарды + inline-кнопки").
- All HTTP-error-to-text mapping lives in one place, `bot/api_client.py` — handlers never catch raw `httpx` exceptions or format error text themselves (spec: "Обработка ошибок").
- Bot runs via long polling, no webhook/HTTPS infra (spec: "Архитектура бота").
- `X-User-Id` header auth model is unchanged and not re-implemented in the bot — `ApiClient` just sets the header from the already-resolved CRM `User.id` (spec: "Аутентификация / middleware"; backend spec's documented MVP trust model).
- Every new backend route/service method follows the existing per-module layering (`router.py` → `service.py` → `repository.py`/raw query), matching the pattern already used across `app/modules/*`.

---

## Task 1: Backend — `GET /users/by-telegram/{telegram_id}`

**Files:**
- Modify: `app/modules/users/repository.py`
- Modify: `app/modules/users/service.py`
- Modify: `app/modules/users/router.py`
- Test: `tests/modules/users/test_service.py`

**Interfaces:**
- Consumes: `User` model (`app/modules/users/models.py`), existing `UserRepository`/`UserService`/`UserOut` (`app/modules/users/schemas.py`).
- Produces: `UserRepository.get_by_telegram_id(telegram_id: int) -> User | None`, `UserService.get_by_telegram_id(telegram_id: int) -> User | None`, route `GET /users/by-telegram/{telegram_id}` returning `UserOut` or `404`. The bot's auth middleware (Task 6) calls this route by telegram id to resolve the acting `User`.

- [ ] **Step 1: Write the failing test**

Append to `tests/modules/users/test_service.py`:

```python
async def test_get_by_telegram_id_finds_active_user(session):
    user = User(role=UserRole.MASTER, full_name="Мастер", telegram_id=555111, branch_id=uuid.uuid4())
    session.add(user)
    await session.flush()

    found = await UserService(session).get_by_telegram_id(555111)
    assert found is not None
    assert found.id == user.id


async def test_get_by_telegram_id_returns_none_when_unknown(session):
    found = await UserService(session).get_by_telegram_id(999999)
    assert found is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/modules/users/test_service.py -v`
Expected: FAIL with `AttributeError: 'UserService' object has no attribute 'get_by_telegram_id'`

- [ ] **Step 3: Implement repository + service methods**

In `app/modules/users/repository.py`, add:

```python
    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        result = await self.session.execute(select(User).where(User.telegram_id == telegram_id))
        return result.scalars().first()
```

In `app/modules/users/service.py`, add to `UserService`:

```python
    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        return await self.repo.get_by_telegram_id(telegram_id)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/modules/users/test_service.py -v`
Expected: PASS (4 tests: the 2 new ones plus the existing 2)

- [ ] **Step 5: Add the route**

In `app/modules/users/router.py`, add (below the existing `list_users` route, no auth dependency — this is the bootstrap identity-resolution point the bot calls before it has any `User` to put in `X-User-Id`; same trusted-internal-network assumption as the rest of the MVP API):

```python
from fastapi import APIRouter, Depends, HTTPException
```

(replace the existing `from fastapi import APIRouter, Depends` import line with the one above), then add:

```python
@router.get("/by-telegram/{telegram_id}", response_model=UserOut)
async def get_user_by_telegram(
    telegram_id: int,
    session: AsyncSession = Depends(get_session),
):
    service = UserService(session)
    user = await service.get_by_telegram_id(telegram_id)
    if user is None or user.deleted_at is not None:
        raise HTTPException(404, "User not found")
    return user
```

- [ ] **Step 6: Manual route sanity check**

Run: `uv run python -c "from app.main import app; print('/users/by-telegram/{telegram_id}' in [r.path for r in app.routes])"`
Expected: `True`

- [ ] **Step 7: Run full suite**

Run: `uv run pytest -q`
Expected: all pass, count increased by 2

- [ ] **Step 8: Commit**

```bash
git add app/modules/users/repository.py app/modules/users/service.py app/modules/users/router.py tests/modules/users/test_service.py
git commit -m "feat: add GET /users/by-telegram/{telegram_id} for bot identity resolution"
```

---

## Task 2: Backend — `GET /work-items/mine`

**Files:**
- Modify: `app/modules/visits/work_items_service.py`
- Modify: `app/modules/visits/work_items_schemas.py`
- Create: `app/modules/visits/work_items_mine_router.py`
- Modify: `app/main.py`
- Test: `tests/modules/visits/test_work_items.py`

**Interfaces:**
- Consumes: `VisitWorkItem` model, existing `WorkItemService`, `require_role` (`app/modules/users/auth.py`).
- Produces: `WorkItemService.list_mine(acting_user: User) -> list[VisitWorkItem]`, schema `WorkItemMineOut` (`id`, `visit_id`, `status`, `free_text_name`, `catalog_item_id`), route `GET /work-items/mine` (role: `MECHANIC`). The bot's mechanic handler (Task 17) calls this route.

- [ ] **Step 1: Write the failing test**

Append to `tests/modules/visits/test_work_items.py`:

```python
async def test_list_mine_returns_only_own_assigned_items(session):
    admin, mechanic_a, mechanic_b, item_a = await _setup_visit_with_mechanic(session)

    mine = await WorkItemService(session).list_mine(mechanic_a)
    assert [i.id for i in mine] == [item_a.id]

    other = await WorkItemService(session).list_mine(mechanic_b)
    assert other == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/modules/visits/test_work_items.py -v`
Expected: FAIL with `AttributeError: 'WorkItemService' object has no attribute 'list_mine'`

- [ ] **Step 3: Implement `list_mine`**

In `app/modules/visits/work_items_service.py`, add to `WorkItemService` (needs `select` and `VisitWorkItem`, both already imported in that file):

```python
    async def list_mine(self, acting_user: User) -> list[VisitWorkItem]:
        result = await self.session.execute(
            select(VisitWorkItem).where(VisitWorkItem.assigned_mechanic_id == acting_user.id)
        )
        return list(result.scalars())
```

Add `from sqlalchemy import select` to the file's imports if not already present (it currently is not — the file only imports `AsyncSession` from `sqlalchemy.ext.asyncio`).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/modules/visits/test_work_items.py -v`
Expected: PASS

- [ ] **Step 5: Add `WorkItemMineOut` schema**

In `app/modules/visits/work_items_schemas.py`, add:

```python
class WorkItemMineOut(BaseModel):
    id: uuid.UUID
    visit_id: uuid.UUID
    status: WorkItemStatus
    free_text_name: str | None
    catalog_item_id: uuid.UUID | None

    class Config:
        from_attributes = True
```

- [ ] **Step 6: Create the router**

Create `app/modules/visits/work_items_mine_router.py`:

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.enums import UserRole
from app.modules.users.auth import require_role
from app.modules.users.models import User
from app.modules.visits.work_items_schemas import WorkItemMineOut
from app.modules.visits.work_items_service import WorkItemService

router = APIRouter(prefix="/work-items", tags=["work-items-mine"])


@router.get("/mine", response_model=list[WorkItemMineOut])
async def list_my_work_items(
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_role(UserRole.MECHANIC)),
):
    service = WorkItemService(session)
    return await service.list_mine(acting_user)
```

- [ ] **Step 7: Register the router in `app/main.py`**

Add the import next to the other visits-related router imports:

```python
from app.modules.visits.work_items_mine_router import router as work_items_mine_router
```

Add `app.include_router(work_items_mine_router)` next to the other `app.include_router(...)` calls (order doesn't matter — the prefix `/work-items` doesn't collide with `/visits/{visit_id}/work-items`).

- [ ] **Step 8: Manual route sanity check**

Run: `uv run python -c "from app.main import app; print('/work-items/mine' in [r.path for r in app.routes])"`
Expected: `True`

- [ ] **Step 9: Run full suite**

Run: `uv run pytest -q`
Expected: all pass, count increased by 1

- [ ] **Step 10: Commit**

```bash
git add app/modules/visits/work_items_service.py app/modules/visits/work_items_schemas.py app/modules/visits/work_items_mine_router.py app/main.py tests/modules/visits/test_work_items.py
git commit -m "feat: add GET /work-items/mine for the mechanic bot flow"
```

---

## Task 3: Backend — `TelegramNotificationSender`

**Files:**
- Modify: `pyproject.toml`
- Modify: `app/core/config.py`
- Modify: `.env.example`
- Create: `app/modules/notifications/telegram_sender.py`
- Create: `app/modules/notifications/factory.py`
- Modify: `app/modules/visits/service.py`
- Modify: `app/modules/visits/work_items_service.py`
- Test: `tests/modules/notifications/test_telegram_sender.py`

**Interfaces:**
- Consumes: `NotificationSender` protocol (`app/modules/notifications/interfaces.py`), `LoggingNotificationSender` (`app/modules/notifications/logging_sender.py`), `Visit`/`VisitWorkItem` models, `User` model, `settings` (`app/core/config.py`).
- Produces: `TelegramNotificationSender` (implements `NotificationSender`, wraps `LoggingNotificationSender` for the audit-trail write, then attempts a real send via `aiogram.Bot.send_message`), `get_notification_sender(session: AsyncSession) -> NotificationSender` factory in `app/modules/notifications/factory.py`. `VisitService.__init__`'s default and `WorkItemService.add_item`'s extra-work notification call both switch from hardcoding `LoggingNotificationSender` to calling this factory.

- [ ] **Step 1: Add `aiogram` and `httpx` to backend's main dependencies**

In `pyproject.toml`, change the `dependencies` list to add both (httpx moves up from `dev` since production code — `TelegramNotificationSender`'s test mocks it, but keeping only `aiogram` production-side and `httpx` dev-only would leave httpx correctly dev-only here — **only add `aiogram`**, httpx stays dev-only; the bot process, not the backend, is what will need `httpx` as a runtime dependency, added in Task 4):

```toml
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
    "aiogram>=3.13",
]
```

Run: `uv sync --extra dev` (re-resolves and installs `aiogram` into the venv)

- [ ] **Step 2: Add `telegram_bot_token` setting**

In `app/core/config.py`, add to `Settings`:

```python
    telegram_bot_token: str | None = None
```

In `.env.example`, add:

```
TELEGRAM_BOT_TOKEN=
```

- [ ] **Step 3: Write the failing test**

Create `tests/modules/notifications/test_telegram_sender.py`:

```python
import uuid
from unittest.mock import AsyncMock

from app.core.enums import UserRole, VisitStatus
from app.modules.notifications.logging_sender import NotificationOutbox
from app.modules.notifications.telegram_sender import TelegramNotificationSender
from app.modules.users.models import User
from app.modules.visits.models import Visit
from sqlalchemy import select


async def _make_visit_with_master(session, telegram_id):
    master = User(role=UserRole.MASTER, full_name="Мастер", telegram_id=telegram_id, branch_id=uuid.uuid4())
    session.add(master)
    await session.flush()
    visit = Visit(
        client_id=uuid.uuid4(),
        vehicle_id=uuid.uuid4(),
        assigned_master_id=master.id,
        mileage_at_intake=1000,
        status=VisitStatus.RECEIVED,
    )
    session.add(visit)
    await session.flush()
    return visit


async def test_send_status_changed_writes_outbox_and_calls_telegram(session):
    visit = await _make_visit_with_master(session, telegram_id=777)
    bot = AsyncMock()
    sender = TelegramNotificationSender(session, bot)

    await sender.send_status_changed(visit, VisitStatus.RECEIVED, VisitStatus.READY)

    rows = list((await session.execute(select(NotificationOutbox))).scalars())
    assert any(r.kind == "status_changed" for r in rows)
    bot.send_message.assert_awaited_once()
    assert bot.send_message.await_args.kwargs["chat_id"] == 777


async def test_send_status_changed_skips_telegram_when_no_telegram_id(session):
    visit = await _make_visit_with_master(session, telegram_id=None)
    bot = AsyncMock()
    sender = TelegramNotificationSender(session, bot)

    await sender.send_status_changed(visit, VisitStatus.RECEIVED, VisitStatus.READY)

    rows = list((await session.execute(select(NotificationOutbox))).scalars())
    assert any(r.kind == "status_changed" for r in rows)
    bot.send_message.assert_not_awaited()
```

- [ ] **Step 4: Run test to verify it fails**

Run: `uv run pytest tests/modules/notifications/test_telegram_sender.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.modules.notifications.telegram_sender'`

- [ ] **Step 5: Implement `TelegramNotificationSender`**

Create `app/modules/notifications/telegram_sender.py`:

```python
import uuid

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import VisitStatus
from app.modules.notifications.logging_sender import LoggingNotificationSender
from app.modules.users.models import User
from app.modules.visits.models import Visit, VisitWorkItem


class TelegramNotificationSender:
    def __init__(self, session: AsyncSession, bot: Bot):
        self.session = session
        self.bot = bot
        self._log = LoggingNotificationSender(session)

    async def _master_chat_id(self, master_id: uuid.UUID) -> int | None:
        master = await self.session.get(User, master_id)
        return master.telegram_id if master else None

    async def _send(self, chat_id: int | None, text: str) -> None:
        if chat_id is None:
            return
        await self.bot.send_message(chat_id=chat_id, text=text)

    async def send_status_changed(self, visit: Visit, old_status: VisitStatus, new_status: VisitStatus) -> None:
        await self._log.send_status_changed(visit, old_status, new_status)
        chat_id = await self._master_chat_id(visit.assigned_master_id)
        await self._send(chat_id, f"Заезд {visit.id}: статус изменён {old_status.value} → {new_status.value}")

    async def send_extra_work_approval_request(self, work_item: VisitWorkItem) -> None:
        await self._log.send_extra_work_approval_request(work_item)
        visit = await self.session.get(Visit, work_item.visit_id)
        chat_id = await self._master_chat_id(visit.assigned_master_id) if visit else None
        await self._send(chat_id, f"Требуется согласование доп.работы по заезду {work_item.visit_id}")

    async def send_document(self, visit: Visit, url: str) -> None:
        await self._log.send_document(visit, url)
        chat_id = await self._master_chat_id(visit.assigned_master_id)
        await self._send(chat_id, f"Документ по заезду {visit.id} готов: {url}")
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/modules/notifications/test_telegram_sender.py -v`
Expected: PASS

- [ ] **Step 7: Implement the factory**

Create `app/modules/notifications/factory.py`:

```python
from functools import lru_cache

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.modules.notifications.interfaces import NotificationSender
from app.modules.notifications.logging_sender import LoggingNotificationSender
from app.modules.notifications.telegram_sender import TelegramNotificationSender


@lru_cache
def _bot() -> Bot | None:
    if not settings.telegram_bot_token:
        return None
    return Bot(token=settings.telegram_bot_token)


def get_notification_sender(session: AsyncSession) -> NotificationSender:
    bot = _bot()
    if bot is None:
        return LoggingNotificationSender(session)
    return TelegramNotificationSender(session, bot)
```

- [ ] **Step 8: Wire the factory into `VisitService`**

In `app/modules/visits/service.py`, replace:

```python
from app.modules.notifications.interfaces import NotificationSender
from app.modules.notifications.logging_sender import LoggingNotificationSender
```

with:

```python
from app.modules.notifications.factory import get_notification_sender
from app.modules.notifications.interfaces import NotificationSender
```

and replace the `__init__` line:

```python
        self.notification_sender = notification_sender or LoggingNotificationSender(session)
```

with:

```python
        self.notification_sender = notification_sender or get_notification_sender(session)
```

- [ ] **Step 9: Wire the factory into `WorkItemService.add_item`**

In `app/modules/visits/work_items_service.py`, replace:

```python
        if item.is_extra_work:
            from app.modules.notifications.logging_sender import LoggingNotificationSender

            await LoggingNotificationSender(self.session).send_extra_work_approval_request(item)
```

with:

```python
        if item.is_extra_work:
            from app.modules.notifications.factory import get_notification_sender

            await get_notification_sender(self.session).send_extra_work_approval_request(item)
```

- [ ] **Step 10: Run full suite**

Run: `uv run pytest -q`
Expected: all pass (no `TELEGRAM_BOT_TOKEN` is set in the test `.env`, so the factory keeps returning `LoggingNotificationSender` everywhere except the two new direct-construction tests above — no behavior change for existing tests)

- [ ] **Step 11: Commit**

```bash
git add pyproject.toml app/core/config.py .env.example app/modules/notifications/telegram_sender.py app/modules/notifications/factory.py app/modules/visits/service.py app/modules/visits/work_items_service.py tests/modules/notifications/test_telegram_sender.py uv.lock
git commit -m "feat: add TelegramNotificationSender, wired in behind a config-driven factory"
```

---

## Task 4: Bot — package scaffold, config, states, keyboards

**Files:**
- Create: `bot/__init__.py`
- Create: `bot/config.py`
- Create: `bot/states.py`
- Create: `bot/keyboards.py`
- Modify: `pyproject.toml`
- Test: `tests/bot/__init__.py`
- Test: `tests/bot/test_keyboards.py`

**Interfaces:**
- Consumes: nothing (foundation task).
- Produces: `bot.config.settings` (`BotSettings`: `bot_token: str`, `api_base_url: str`), FSM state groups in `bot.states` (`NewVisitStates`, `NewClientStates`, `NewVehicleStates`, `AddWorkItemStates`, `AddPartItemStates`, `NewStaffStates` — each a placeholder `StatesGroup` with the states its own task will need, declared upfront so later tasks only add attributes, never redefine the class), `bot.keyboards.main_menu(role: UserRole) -> ReplyKeyboardMarkup`. All later bot tasks import from these three modules.

- [ ] **Step 1: Add bot dependencies and package discovery**

In `pyproject.toml`, add `httpx` to main `dependencies` (it's already a dev dependency for backend tests — the bot needs it at runtime too, so it must also be a main dependency; keep it listed under `dev` as well is harmless, but the important part is adding it to `dependencies`):

```toml
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
    "aiogram>=3.13",
    "httpx>=0.27",
]
```

And change `[tool.setuptools.packages.find]` to also pick up the bot package:

```toml
[tool.setuptools.packages.find]
include = ["app*", "bot*"]
```

Run: `uv sync --extra dev && uv pip install -e .`

- [ ] **Step 2: Create `bot/config.py`**

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class BotSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    bot_token: str = ""
    api_base_url: str = "http://localhost:8000"


settings = BotSettings()
```

(Reads `BOT_TOKEN` from the environment/`.env` by pydantic-settings' default snake-case-to-upper-case env var mapping; kept separate from backend's `TELEGRAM_BOT_TOKEN` setting name deliberately — the bot process and the backend process each own their config independently, even though in practice they'll be pointed at the same physical token value via two env vars.)

Add to `.env.example`:

```
BOT_TOKEN=
API_BASE_URL=http://localhost:8000
```

- [ ] **Step 3: Create `bot/states.py`**

```python
from aiogram.fsm.state import State, StatesGroup


class NewClientStates(StatesGroup):
    waiting_for_phone = State()
    waiting_for_full_name = State()


class NewVehicleStates(StatesGroup):
    waiting_for_vin = State()
    waiting_for_plate = State()
    waiting_for_make_model = State()


class NewVisitStates(StatesGroup):
    choosing_client = State()
    choosing_vehicle = State()
    waiting_for_mileage = State()
    choosing_master = State()


class AddWorkItemStates(StatesGroup):
    waiting_for_name = State()
    choosing_suggestion = State()
    waiting_for_hours_and_rate = State()


class AddPartItemStates(StatesGroup):
    choosing_work_item = State()
    waiting_for_name = State()
    waiting_for_quantity_and_price = State()


class NewStaffStates(StatesGroup):
    choosing_role = State()
    waiting_for_full_name = State()
    waiting_for_telegram_id = State()
```

- [ ] **Step 4: Write the failing test for the main menu keyboard**

Create `tests/bot/__init__.py` (empty) and `tests/bot/test_keyboards.py`:

```python
from app.core.enums import UserRole
from bot.keyboards import main_menu


def test_mechanic_menu_has_only_my_work_items_button():
    markup = main_menu(UserRole.MECHANIC)
    texts = [button.text for row in markup.keyboard for button in row]
    assert texts == ["Мои работы"]


def test_master_menu_has_full_staff_buttons_but_not_admin_only():
    markup = main_menu(UserRole.MASTER)
    texts = [button.text for row in markup.keyboard for button in row]
    assert "Новый заезд" in texts
    assert "Поиск" in texts
    assert "Добавить сотрудника" not in texts


def test_admin_menu_includes_add_staff_button():
    markup = main_menu(UserRole.ADMIN)
    texts = [button.text for row in markup.keyboard for button in row]
    assert "Добавить сотрудника" in texts
```

- [ ] **Step 5: Run test to verify it fails**

Run: `uv run pytest tests/bot/test_keyboards.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bot.keyboards'`

- [ ] **Step 6: Implement `bot/keyboards.py`**

```python
from aiogram.types import ReplyKeyboardMarkup
from aiogram.utils.keyboard import ReplyKeyboardBuilder

from app.core.enums import UserRole

STAFF_BUTTONS = ["Новый заезд", "Поиск", "Регистрация клиента (бумага)"]
ADMIN_ONLY_BUTTONS = ["Добавить сотрудника"]
MECHANIC_BUTTONS = ["Мои работы"]


def main_menu(role: UserRole) -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    if role == UserRole.MECHANIC:
        buttons = MECHANIC_BUTTONS
    else:
        buttons = list(STAFF_BUTTONS)
        if role == UserRole.ADMIN:
            buttons += ADMIN_ONLY_BUTTONS
    for text in buttons:
        builder.button(text=text)
    builder.adjust(1)
    return builder.as_markup(resize_keyboard=True)
```

- [ ] **Step 7: Run test to verify it passes**

Run: `uv run pytest tests/bot/test_keyboards.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add bot/__init__.py bot/config.py bot/states.py bot/keyboards.py pyproject.toml .env.example tests/bot/__init__.py tests/bot/test_keyboards.py uv.lock
git commit -m "feat: scaffold bot package — config, FSM states, main menu keyboard"
```

---

## Task 5: Bot — `ApiClient` (HTTP core + error mapping)

**Files:**
- Create: `bot/api_client.py`
- Test: `tests/bot/test_api_client.py`

**Interfaces:**
- Consumes: `bot.config.settings`.
- Produces: exceptions `ApiNotFound`, `ApiConflict`, `ApiValidationError`, `ApiUnavailable` (all carrying a human-readable `message: str`), class `ApiClient` with `__init__(self, user_id: uuid.UUID | None = None)`, generic verbs `get`, `post`, `patch` (each: `path: str, json: dict | None = None -> dict | list`, raising the above exceptions on non-2xx), and the one typed method every later task needs first: `get_user_by_telegram(telegram_id: int) -> dict | None`. Every subsequent bot handler task adds its own typed methods to this same file (e.g. `create_client`, `create_visit`) — this task only builds the core plus the one bootstrap method.

- [ ] **Step 1: Write the failing tests**

Create `tests/bot/test_api_client.py`:

```python
import httpx
import pytest
import respx

from bot.api_client import ApiClient, ApiConflict, ApiNotFound, ApiUnavailable, ApiValidationError


@respx.mock
async def test_get_returns_json_on_success():
    respx.get("http://localhost:8000/clients/abc").mock(
        return_value=httpx.Response(200, json={"id": "abc"})
    )
    client = ApiClient()
    result = await client.get("/clients/abc")
    assert result == {"id": "abc"}


@respx.mock
async def test_get_raises_api_not_found_on_404():
    respx.get("http://localhost:8000/clients/abc").mock(
        return_value=httpx.Response(404, json={"detail": "Client not found"})
    )
    client = ApiClient()
    with pytest.raises(ApiNotFound, match="Client not found"):
        await client.get("/clients/abc")


@respx.mock
async def test_post_raises_api_conflict_on_409():
    respx.post("http://localhost:8000/visits/abc/status").mock(
        return_value=httpx.Response(409, json={"detail": "Переход между статусами не разрешён"})
    )
    client = ApiClient()
    with pytest.raises(ApiConflict, match="не разрешён"):
        await client.patch("/visits/abc/status", json={"new_status": "ready"})


@respx.mock
async def test_post_raises_api_validation_error_on_422():
    respx.post("http://localhost:8000/visits").mock(
        return_value=httpx.Response(422, json={"detail": "assigned_master_id должен ссылаться на MASTER"})
    )
    client = ApiClient()
    with pytest.raises(ApiValidationError):
        await client.post("/visits", json={})


@respx.mock
async def test_get_raises_api_unavailable_on_500():
    respx.get("http://localhost:8000/clients").mock(return_value=httpx.Response(500))
    client = ApiClient()
    with pytest.raises(ApiUnavailable):
        await client.get("/clients")


@respx.mock
async def test_requests_carry_x_user_id_header_when_set():
    route = respx.get("http://localhost:8000/clients").mock(return_value=httpx.Response(200, json=[]))
    client = ApiClient(user_id="11111111-1111-1111-1111-111111111111")
    await client.get("/clients")
    assert route.calls.last.request.headers["X-User-Id"] == "11111111-1111-1111-1111-111111111111"


@respx.mock
async def test_get_user_by_telegram_returns_none_on_404():
    respx.get("http://localhost:8000/users/by-telegram/42").mock(
        return_value=httpx.Response(404, json={"detail": "User not found"})
    )
    client = ApiClient()
    assert await client.get_user_by_telegram(42) is None


@respx.mock
async def test_get_user_by_telegram_returns_dict_on_success():
    respx.get("http://localhost:8000/users/by-telegram/42").mock(
        return_value=httpx.Response(200, json={"id": "u1", "role": "master"})
    )
    client = ApiClient()
    result = await client.get_user_by_telegram(42)
    assert result == {"id": "u1", "role": "master"}
```

Add `respx` to `pyproject.toml`'s `dev` dependencies:

```toml
dev = [
    "pytest>=8.3",
    "pytest-asyncio>=0.24",
    "httpx>=0.27",
    "respx>=0.21",
]
```

Run: `uv sync --extra dev`

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/bot/test_api_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bot.api_client'`

- [ ] **Step 3: Implement `bot/api_client.py`**

```python
import httpx

from bot.config import settings


class ApiError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class ApiNotFound(ApiError):
    pass


class ApiConflict(ApiError):
    pass


class ApiValidationError(ApiError):
    pass


class ApiUnavailable(ApiError):
    pass


class ApiClient:
    def __init__(self, user_id: str | None = None):
        self.user_id = user_id

    def _headers(self) -> dict[str, str]:
        if self.user_id is None:
            return {}
        return {"X-User-Id": str(self.user_id)}

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.status_code < 400:
            return
        try:
            detail = response.json().get("detail", "")
        except Exception:
            detail = ""
        if response.status_code == 404:
            raise ApiNotFound(detail or "Не найдено")
        if response.status_code == 409:
            raise ApiConflict(detail or "Конфликт")
        if response.status_code == 422:
            raise ApiValidationError(detail or "Некорректные данные")
        raise ApiUnavailable("Сервис временно недоступен, попробуйте позже")

    async def get(self, path: str) -> dict | list:
        async with httpx.AsyncClient(base_url=settings.api_base_url) as client:
            response = await client.get(path, headers=self._headers())
        self._raise_for_status(response)
        return response.json()

    async def post(self, path: str, json: dict | None = None) -> dict | list:
        async with httpx.AsyncClient(base_url=settings.api_base_url) as client:
            response = await client.post(path, json=json or {}, headers=self._headers())
        self._raise_for_status(response)
        return response.json()

    async def patch(self, path: str, json: dict | None = None) -> dict | list:
        async with httpx.AsyncClient(base_url=settings.api_base_url) as client:
            response = await client.patch(path, json=json or {}, headers=self._headers())
        self._raise_for_status(response)
        return response.json()

    async def get_user_by_telegram(self, telegram_id: int) -> dict | None:
        try:
            return await self.get(f"/users/by-telegram/{telegram_id}")
        except ApiNotFound:
            return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/bot/test_api_client.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add bot/api_client.py pyproject.toml tests/bot/test_api_client.py uv.lock
git commit -m "feat: add bot ApiClient with centralized HTTP-error-to-exception mapping"
```

---

## Task 6: Bot — auth + error-handling middlewares

**Files:**
- Create: `bot/middlewares/__init__.py`
- Create: `bot/middlewares/auth.py`
- Create: `bot/middlewares/error_handling.py`
- Test: `tests/bot/test_auth_middleware.py`
- Test: `tests/bot/test_error_handling_middleware.py`

**Interfaces:**
- Consumes: `bot.api_client.ApiClient.get_user_by_telegram`, `bot.api_client.ApiError`.
- Produces: `AuthMiddleware` (an `aiogram.BaseMiddleware`) that resolves `event.from_user.id` via `ApiClient().get_user_by_telegram(...)`, injects `data["user"] = <dict with id/role>` and `data["api"] = ApiClient(user_id=...)` on success, or calls `event.answer(...)` with a rejection message and returns `None` (short-circuits, does not call `handler`) when the user is unknown. `ErrorHandlingMiddleware` — the single point (per spec's "Обработка ошибок") that catches any `ApiError` (and subclasses `ApiNotFound`/`ApiConflict`/`ApiValidationError`/`ApiUnavailable`) raised by a handler and replies with the exception's `.message` instead of letting it propagate as an unhandled exception; handlers never catch `ApiError` themselves. Both are registered on the `Dispatcher` in Task 7; every handler from Task 7 onward receives `user` and `api` as keyword arguments and can let any `ApiError` simply propagate.

- [ ] **Step 1: Write the failing test**

Create `tests/bot/test_auth_middleware.py`:

```python
from unittest.mock import AsyncMock, patch

from bot.middlewares.auth import AuthMiddleware


async def test_known_user_is_injected_and_handler_called():
    middleware = AuthMiddleware()
    handler = AsyncMock(return_value="handled")
    event = AsyncMock()
    event.from_user.id = 42
    data = {}

    with patch("bot.middlewares.auth.ApiClient") as MockClient:
        MockClient.return_value.get_user_by_telegram = AsyncMock(
            return_value={"id": "u1", "role": "master"}
        )
        result = await middleware(handler, event, data)

    assert result == "handled"
    handler.assert_awaited_once_with(event, data)
    assert data["user"] == {"id": "u1", "role": "master"}
    assert data["api"].user_id == "u1"


async def test_unknown_user_is_rejected_without_calling_handler():
    middleware = AuthMiddleware()
    handler = AsyncMock()
    event = AsyncMock()
    event.from_user.id = 99
    data = {}

    with patch("bot.middlewares.auth.ApiClient") as MockClient:
        MockClient.return_value.get_user_by_telegram = AsyncMock(return_value=None)
        result = await middleware(handler, event, data)

    assert result is None
    handler.assert_not_awaited()
    event.answer.assert_awaited_once()
    assert "администратору" in event.answer.await_args.args[0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/bot/test_auth_middleware.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bot.middlewares'`

- [ ] **Step 3: Implement the middleware**

Create `bot/middlewares/__init__.py` (empty) and `bot/middlewares/auth.py`:

```python
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from bot.api_client import ApiClient


class AuthMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        telegram_id = event.from_user.id
        client = ApiClient()
        user = await client.get_user_by_telegram(telegram_id)
        if user is None:
            await event.answer("Обратитесь к администратору, ваш Telegram не привязан к учётной записи.")
            return None
        data["user"] = user
        data["api"] = ApiClient(user_id=user["id"])
        return await handler(event, data)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/bot/test_auth_middleware.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add bot/middlewares/__init__.py bot/middlewares/auth.py tests/bot/test_auth_middleware.py
git commit -m "feat: add bot auth middleware resolving Telegram users to CRM users"
```

---

## Task 7: Bot — entrypoint, `/start`, main menu

**Files:**
- Create: `bot/handlers/__init__.py`
- Create: `bot/handlers/start.py`
- Create: `bot/main.py`
- Test: `tests/bot/test_start_handler.py`

**Interfaces:**
- Consumes: `bot.keyboards.main_menu`, `bot.middlewares.auth.AuthMiddleware`, `bot.states` (imported here only to confirm the module loads cleanly — no wizard logic yet).
- Produces: `bot.handlers.start.router` (an `aiogram.Router` with one `/start` handler), `bot/main.py`'s `main()` coroutine wiring `Bot`, `Dispatcher(storage=MemoryStorage())`, the auth middleware, and `start.router`, then calling `dp.start_polling(bot)`. This is the first end-to-end runnable slice: starting the bot and sending `/start` shows the role-appropriate menu. Every later handler task adds its own `router` module, imported and `include_router`-ed in `bot/main.py`.

- [ ] **Step 1: Write the failing test**

Create `tests/bot/test_start_handler.py`:

```python
from unittest.mock import AsyncMock

from bot.handlers.start import cmd_start


async def test_start_shows_role_appropriate_menu():
    message = AsyncMock()
    user = {"id": "u1", "role": "mechanic"}

    await cmd_start(message, user=user)

    message.answer.assert_awaited_once()
    args, kwargs = message.answer.await_args
    assert "Мои работы" in [b.text for row in kwargs["reply_markup"].keyboard for b in row]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/bot/test_start_handler.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bot.handlers.start'`

- [ ] **Step 3: Implement `bot/handlers/start.py`**

Create `bot/handlers/__init__.py` (empty) and `bot/handlers/start.py`:

```python
from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from app.core.enums import UserRole
from bot.keyboards import main_menu

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, user: dict, **kwargs) -> None:
    role = UserRole(user["role"])
    await message.answer("Добро пожаловать в CRM-бот автосервиса.", reply_markup=main_menu(role))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/bot/test_start_handler.py -v`
Expected: PASS

- [ ] **Step 5: Implement `bot/main.py`**

```python
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from bot.config import settings
from bot.handlers import start
from bot.middlewares.auth import AuthMiddleware


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    bot = Bot(token=settings.bot_token)
    dp = Dispatcher(storage=MemoryStorage())
    dp.message.middleware(AuthMiddleware())
    dp.callback_query.middleware(AuthMiddleware())
    dp.include_router(start.router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 6: Run full bot test suite**

Run: `uv run pytest tests/bot/ -v`
Expected: all pass

- [ ] **Step 7: Commit**

```bash
git add bot/handlers/__init__.py bot/handlers/start.py bot/main.py tests/bot/test_start_handler.py
git commit -m "feat: bot entrypoint with /start and role-based main menu — first runnable slice"
```

---

## Task 8: Bot — clients handler (search + create)

**Files:**
- Modify: `bot/api_client.py`
- Create: `bot/handlers/clients.py`
- Modify: `bot/main.py`
- Test: `tests/bot/test_clients_handler.py`

**Interfaces:**
- Consumes: `ApiClient` (Task 5), `NewClientStates` (Task 4), `main_menu` (Task 4).
- Produces: `ApiClient.search(query: str) -> list[dict]` and `ApiClient.create_client(full_name: str, phone: str) -> dict` (new methods on the existing class), `bot.handlers.clients.router` handling the "Поиск" button (delegates to Task 14's dedicated search handler — this task's router only owns the client-creation wizard, triggered from the new-visit flow in Task 10 via `NewClientStates`) and a standalone "Создать клиента" entry point for ad-hoc creation.

- [ ] **Step 1: Write the failing test**

Create `tests/bot/test_clients_handler.py`:

```python
from unittest.mock import AsyncMock

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.base import StorageKey

from bot.handlers.clients import receive_full_name, start_new_client
from bot.states import NewClientStates


def _fsm_context() -> FSMContext:
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=1, user_id=1)
    return FSMContext(storage=storage, key=key)


async def test_start_new_client_asks_for_phone():
    message = AsyncMock()
    state = _fsm_context()

    await start_new_client(message, state)

    message.answer.assert_awaited_once()
    assert (await state.get_state()) == NewClientStates.waiting_for_phone.state


async def test_receive_full_name_creates_client_via_api():
    message = AsyncMock()
    message.text = "Иван Иванов"
    state = _fsm_context()
    await state.update_data(phone="79991234567")
    api = AsyncMock()
    api.create_client.return_value = {"id": "c1", "full_name": "Иван Иванов"}

    await receive_full_name(message, state, api=api)

    api.create_client.assert_awaited_once_with(full_name="Иван Иванов", phone="79991234567")
    assert (await state.get_state()) is None
    message.answer.assert_awaited()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/bot/test_clients_handler.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bot.handlers.clients'`

- [ ] **Step 3: Add client methods to `ApiClient`**

In `bot/api_client.py`, add to `ApiClient`:

```python
    async def search(self, query: str) -> list[dict]:
        result = await self.get(f"/search?q={query}")
        return result

    async def create_client(self, full_name: str, phone: str) -> dict:
        return await self.post("/clients", json={"full_name": full_name, "phone": phone})
```

- [ ] **Step 4: Implement `bot/handlers/clients.py`**

```python
from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.api_client import ApiClient
from bot.states import NewClientStates

router = Router()


@router.message(Command("new_client"))
async def start_new_client(message: Message, state: FSMContext, **kwargs) -> None:
    await state.set_state(NewClientStates.waiting_for_phone)
    await message.answer("Введите телефон клиента:")


@router.message(NewClientStates.waiting_for_phone)
async def receive_phone(message: Message, state: FSMContext, **kwargs) -> None:
    await state.update_data(phone=message.text)
    await state.set_state(NewClientStates.waiting_for_full_name)
    await message.answer("Введите ФИО клиента:")


@router.message(NewClientStates.waiting_for_full_name)
async def receive_full_name(message: Message, state: FSMContext, api: ApiClient, **kwargs) -> None:
    data = await state.get_data()
    client = await api.create_client(full_name=message.text, phone=data["phone"])
    await state.clear()
    await message.answer(f"Клиент создан: {client['full_name']}")
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/bot/test_clients_handler.py -v`
Expected: PASS

- [ ] **Step 6: Register the router in `bot/main.py`**

Add `from bot.handlers import clients` and `dp.include_router(clients.router)` next to the `start.router` registration.

- [ ] **Step 7: Run full bot test suite**

Run: `uv run pytest tests/bot/ -v`
Expected: all pass

- [ ] **Step 8: Commit**

```bash
git add bot/api_client.py bot/handlers/clients.py bot/main.py tests/bot/test_clients_handler.py
git commit -m "feat: bot client-creation wizard"
```

---

## Task 9: Bot — vehicles handler (search + create)

**Files:**
- Modify: `bot/api_client.py`
- Create: `bot/handlers/vehicles.py`
- Modify: `bot/main.py`
- Test: `tests/bot/test_vehicles_handler.py`

**Interfaces:**
- Consumes: `ApiClient`, `NewVehicleStates`.
- Produces: `ApiClient.create_vehicle(vin, plate_number, make, model) -> dict`, `bot.handlers.vehicles.router` with a `/new_vehicle` wizard (VIN → plate → make/model → create), same shape as Task 8's client wizard.

- [ ] **Step 1: Write the failing test**

Create `tests/bot/test_vehicles_handler.py`:

```python
from unittest.mock import AsyncMock

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.base import StorageKey

from bot.handlers.vehicles import receive_make_model, start_new_vehicle
from bot.states import NewVehicleStates


def _fsm_context() -> FSMContext:
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=1, user_id=1)
    return FSMContext(storage=storage, key=key)


async def test_start_new_vehicle_asks_for_vin():
    message = AsyncMock()
    state = _fsm_context()

    await start_new_vehicle(message, state)

    assert (await state.get_state()) == NewVehicleStates.waiting_for_vin.state


async def test_receive_make_model_creates_vehicle_via_api():
    message = AsyncMock()
    message.text = "Toyota Camry"
    state = _fsm_context()
    await state.update_data(vin="X" * 17, plate_number="А123")
    api = AsyncMock()
    api.create_vehicle.return_value = {"id": "v1", "vin": "X" * 17}

    await receive_make_model(message, state, api=api)

    api.create_vehicle.assert_awaited_once_with(
        vin="X" * 17, plate_number="А123", make="Toyota", model="Camry"
    )
    assert (await state.get_state()) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/bot/test_vehicles_handler.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bot.handlers.vehicles'`

- [ ] **Step 3: Add vehicle method to `ApiClient`**

In `bot/api_client.py`, add:

```python
    async def create_vehicle(self, vin: str, plate_number: str, make: str, model: str) -> dict:
        return await self.post(
            "/vehicles", json={"vin": vin, "plate_number": plate_number, "make": make, "model": model}
        )
```

- [ ] **Step 4: Implement `bot/handlers/vehicles.py`**

```python
from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.api_client import ApiClient
from bot.states import NewVehicleStates

router = Router()


@router.message(Command("new_vehicle"))
async def start_new_vehicle(message: Message, state: FSMContext, **kwargs) -> None:
    await state.set_state(NewVehicleStates.waiting_for_vin)
    await message.answer("Введите VIN:")


@router.message(NewVehicleStates.waiting_for_vin)
async def receive_vin(message: Message, state: FSMContext, **kwargs) -> None:
    await state.update_data(vin=message.text)
    await state.set_state(NewVehicleStates.waiting_for_plate)
    await message.answer("Введите гос.номер:")


@router.message(NewVehicleStates.waiting_for_plate)
async def receive_plate(message: Message, state: FSMContext, **kwargs) -> None:
    await state.update_data(plate_number=message.text)
    await state.set_state(NewVehicleStates.waiting_for_make_model)
    await message.answer("Введите марку и модель через пробел (например: Toyota Camry):")


@router.message(NewVehicleStates.waiting_for_make_model)
async def receive_make_model(message: Message, state: FSMContext, api: ApiClient, **kwargs) -> None:
    make, _, model = message.text.partition(" ")
    data = await state.get_data()
    vehicle = await api.create_vehicle(vin=data["vin"], plate_number=data["plate_number"], make=make, model=model)
    await state.clear()
    await message.answer(f"Автомобиль создан: {vehicle['vin']}")
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/bot/test_vehicles_handler.py -v`
Expected: PASS

- [ ] **Step 6: Register the router in `bot/main.py`**

Add `from bot.handlers import vehicles` and `dp.include_router(vehicles.router)`.

- [ ] **Step 7: Run full bot test suite**

Run: `uv run pytest tests/bot/ -v`
Expected: all pass

- [ ] **Step 8: Commit**

```bash
git add bot/api_client.py bot/handlers/vehicles.py bot/main.py tests/bot/test_vehicles_handler.py
git commit -m "feat: bot vehicle-creation wizard"
```

---

## Task 10: Bot — visits handler (new visit wizard + visit card)

**Files:**
- Modify: `bot/api_client.py`
- Create: `bot/handlers/visits.py`
- Modify: `bot/main.py`
- Test: `tests/bot/test_visits_handler.py`

**Interfaces:**
- Consumes: `ApiClient`, `NewVisitStates`.
- Produces: `ApiClient.create_visit(client_id, vehicle_id, assigned_master_id, mileage_at_intake) -> dict`, `ApiClient.change_visit_status(visit_id, new_status) -> dict`, `bot.handlers.visits.router` with the new-visit wizard entry point (`/new_visit`, taking already-known `client_id`/`vehicle_id` via FSM data set by a preceding search — this task's wizard starts from the mileage step onward, since client/vehicle lookup already exists in Tasks 8/9/14 and this task does not re-implement search UI) and a `send_visit_card(message, visit: dict)` helper building the inline status-transition keyboard. `send_visit_card` is imported by Task 11 (work items) and Task 13 (documents) to redisplay the card after an action.

- [ ] **Step 1: Write the failing test**

Create `tests/bot/test_visits_handler.py`:

```python
from unittest.mock import AsyncMock

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.base import StorageKey

from bot.handlers.visits import receive_mileage, send_visit_card
from bot.states import NewVisitStates


def _fsm_context() -> FSMContext:
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=1, user_id=1)
    return FSMContext(storage=storage, key=key)


async def test_receive_mileage_creates_visit_via_api():
    message = AsyncMock()
    message.text = "45000"
    state = _fsm_context()
    await state.set_state(NewVisitStates.waiting_for_mileage)
    await state.update_data(client_id="c1", vehicle_id="v1", master_id="m1")
    api = AsyncMock()
    api.create_visit.return_value = {"id": "visit1", "status": "received"}

    await receive_mileage(message, state, api=api)

    api.create_visit.assert_awaited_once_with(
        client_id="c1", vehicle_id="v1", assigned_master_id="m1", mileage_at_intake=45000
    )
    assert (await state.get_state()) is None


async def test_send_visit_card_shows_status_buttons():
    message = AsyncMock()
    visit = {"id": "visit1", "status": "received", "total_amount": "0.00"}

    await send_visit_card(message, visit)

    message.answer.assert_awaited_once()
    _, kwargs = message.answer.await_args
    assert kwargs["reply_markup"] is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/bot/test_visits_handler.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bot.handlers.visits'`

- [ ] **Step 3: Add visit methods to `ApiClient`**

In `bot/api_client.py`, add:

```python
    async def create_visit(self, client_id: str, vehicle_id: str, assigned_master_id: str, mileage_at_intake: int) -> dict:
        return await self.post(
            "/visits",
            json={
                "client_id": client_id,
                "vehicle_id": vehicle_id,
                "assigned_master_id": assigned_master_id,
                "mileage_at_intake": mileage_at_intake,
            },
        )

    async def change_visit_status(self, visit_id: str, new_status: str) -> dict:
        return await self.patch(f"/visits/{visit_id}/status", json={"new_status": new_status})
```

- [ ] **Step 4: Implement `bot/handlers/visits.py`**

```python
from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.api_client import ApiClient
from bot.states import NewVisitStates

router = Router()

_NEXT_STATUS_BY_CURRENT = {
    "received": ["diagnostics", "cancelled"],
    "diagnostics": ["approval", "cancelled"],
    "approval": ["in_progress", "cancelled"],
    "in_progress": ["waiting_parts", "ready", "cancelled"],
    "waiting_parts": ["in_progress", "cancelled"],
    "ready": ["issued"],
}


async def send_visit_card(message: Message, visit: dict) -> None:
    builder = InlineKeyboardBuilder()
    for status in _NEXT_STATUS_BY_CURRENT.get(visit["status"], []):
        builder.button(text=status, callback_data=f"visit_status:{visit['id']}:{status}")
    builder.adjust(1)
    await message.answer(
        f"Заезд {visit['id']}\nСтатус: {visit['status']}\nСумма: {visit.get('total_amount', '—')}",
        reply_markup=builder.as_markup(),
    )


@router.message(NewVisitStates.waiting_for_mileage)
async def receive_mileage(message: Message, state: FSMContext, api: ApiClient, **kwargs) -> None:
    data = await state.get_data()
    visit = await api.create_visit(
        client_id=data["client_id"],
        vehicle_id=data["vehicle_id"],
        assigned_master_id=data["master_id"],
        mileage_at_intake=int(message.text),
    )
    await state.clear()
    await send_visit_card(message, visit)


@router.callback_query(lambda c: c.data.startswith("visit_status:"))
async def change_status_callback(callback: CallbackQuery, api: ApiClient, **kwargs) -> None:
    _, visit_id, new_status = callback.data.split(":")
    visit = await api.change_visit_status(visit_id, new_status)
    await callback.message.answer(f"Статус обновлён: {visit['status']}")
    await callback.answer()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/bot/test_visits_handler.py -v`
Expected: PASS

- [ ] **Step 6: Register the router in `bot/main.py`**

Add `from bot.handlers import visits` and `dp.include_router(visits.router)`.

- [ ] **Step 7: Run full bot test suite**

Run: `uv run pytest tests/bot/ -v`
Expected: all pass

- [ ] **Step 8: Commit**

```bash
git add bot/api_client.py bot/handlers/visits.py bot/main.py tests/bot/test_visits_handler.py
git commit -m "feat: bot visit creation and status-transition card"
```

---

## Task 11: Bot — work items handler (add work, status, approve)

**Files:**
- Modify: `bot/api_client.py`
- Create: `bot/handlers/work_items.py`
- Modify: `bot/main.py`
- Test: `tests/bot/test_work_items_handler.py`

**Interfaces:**
- Consumes: `ApiClient`, `AddWorkItemStates`, `send_visit_card` (Task 10).
- Produces: `ApiClient.suggest_catalog(text: str) -> list[dict]`, `ApiClient.add_work_item(visit_id, **fields) -> dict`, `ApiClient.update_work_item_status(item_id, new_status) -> dict`, `ApiClient.approve_work_item(item_id) -> dict`, `bot.handlers.work_items.router`.

- [ ] **Step 1: Write the failing test**

Create `tests/bot/test_work_items_handler.py`:

```python
from unittest.mock import AsyncMock

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.base import StorageKey

from bot.handlers.work_items import receive_work_name
from bot.states import AddWorkItemStates


def _fsm_context() -> FSMContext:
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=1, user_id=1)
    return FSMContext(storage=storage, key=key)


async def test_receive_work_name_shows_catalog_suggestions():
    message = AsyncMock()
    message.text = "замена масла"
    state = _fsm_context()
    await state.set_state(AddWorkItemStates.waiting_for_name)
    await state.update_data(visit_id="visit1")
    api = AsyncMock()
    api.suggest_catalog.return_value = [{"id": "cat1", "name": "Замена масла"}]

    await receive_work_name(message, state, api=api)

    api.suggest_catalog.assert_awaited_once_with("замена масла")
    message.answer.assert_awaited_once()
    assert (await state.get_state()) == AddWorkItemStates.choosing_suggestion.state
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/bot/test_work_items_handler.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bot.handlers.work_items'`

- [ ] **Step 3: Add work-item methods to `ApiClient`**

In `bot/api_client.py`, add:

```python
    async def suggest_catalog(self, text: str) -> list[dict]:
        return await self.get(f"/catalog/suggest?text={text}")

    async def add_work_item(self, visit_id: str, **fields) -> dict:
        return await self.post(f"/visits/{visit_id}/work-items", json=fields)

    async def update_work_item_status(self, item_id: str, new_status: str) -> dict:
        return await self.patch(f"/visits/_/work-items/{item_id}/status", json={"new_status": new_status})

    async def approve_work_item(self, item_id: str) -> dict:
        return await self.post(f"/visits/_/work-items/{item_id}/approve")
```

Note: the backend's work-item routes are nested under `/visits/{visit_id}/work-items/{item_id}/...` but `visit_id` isn't used for routing to a specific item by the backend handler beyond path structure — confirm against `app/modules/visits/work_items_router.py` at implementation time; if the real path requires a valid `visit_id` (it does, per that router's prefix), thread the actual `visit_id` through `update_work_item_status`/`approve_work_item`'s signature instead of the `_` placeholder shown here before writing this step's code.

- [ ] **Step 4: Implement `bot/handlers/work_items.py`**

```python
from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.api_client import ApiClient
from bot.states import AddWorkItemStates

router = Router()


@router.message(AddWorkItemStates.waiting_for_name)
async def receive_work_name(message: Message, state: FSMContext, api: ApiClient, **kwargs) -> None:
    suggestions = await api.suggest_catalog(message.text)
    await state.update_data(free_text_name=message.text)
    builder = InlineKeyboardBuilder()
    for item in suggestions:
        builder.button(text=item["name"], callback_data=f"catalog_pick:{item['id']}")
    builder.button(text="Своя формулировка", callback_data="catalog_pick:none")
    builder.adjust(1)
    await state.set_state(AddWorkItemStates.choosing_suggestion)
    await message.answer("Выберите работу из справочника или укажите свою:", reply_markup=builder.as_markup())
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/bot/test_work_items_handler.py -v`
Expected: PASS

- [ ] **Step 6: Register the router in `bot/main.py`**

Add `from bot.handlers import work_items` and `dp.include_router(work_items.router)`.

- [ ] **Step 7: Run full bot test suite**

Run: `uv run pytest tests/bot/ -v`
Expected: all pass

- [ ] **Step 8: Commit**

```bash
git add bot/api_client.py bot/handlers/work_items.py bot/main.py tests/bot/test_work_items_handler.py
git commit -m "feat: bot work-item creation with catalog suggestions"
```

---

## Task 12: Bot — part items handler

**Files:**
- Modify: `bot/api_client.py`
- Create: `bot/handlers/part_items.py`
- Modify: `bot/main.py`
- Test: `tests/bot/test_part_items_handler.py`

**Interfaces:**
- Consumes: `ApiClient`, `AddPartItemStates`.
- Produces: `ApiClient.add_part_item(visit_id, work_item_id, name, quantity, unit_price) -> dict`, `bot.handlers.part_items.router`.

- [ ] **Step 1: Write the failing test**

Create `tests/bot/test_part_items_handler.py`:

```python
from unittest.mock import AsyncMock

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.base import StorageKey

from bot.handlers.part_items import receive_quantity_and_price
from bot.states import AddPartItemStates


def _fsm_context() -> FSMContext:
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=1, user_id=1)
    return FSMContext(storage=storage, key=key)


async def test_receive_quantity_and_price_creates_part_item():
    message = AsyncMock()
    message.text = "2 350"
    state = _fsm_context()
    await state.update_data(visit_id="visit1", work_item_id="wi1", name="Фильтр")
    api = AsyncMock()
    api.add_part_item.return_value = {"id": "p1", "name": "Фильтр"}

    await receive_quantity_and_price(message, state, api=api)

    api.add_part_item.assert_awaited_once_with(
        visit_id="visit1", work_item_id="wi1", name="Фильтр", quantity=2, unit_price=350.0
    )
    assert (await state.get_state()) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/bot/test_part_items_handler.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bot.handlers.part_items'`

- [ ] **Step 3: Add part-item method to `ApiClient`**

In `bot/api_client.py`, add:

```python
    async def add_part_item(self, visit_id: str, work_item_id: str, name: str, quantity: int, unit_price: float) -> dict:
        return await self.post(
            f"/visits/{visit_id}/part-items",
            json={"work_item_id": work_item_id, "name": name, "quantity": quantity, "unit_price": unit_price},
        )
```

- [ ] **Step 4: Implement `bot/handlers/part_items.py`**

```python
from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.api_client import ApiClient
from bot.states import AddPartItemStates

router = Router()


@router.message(AddPartItemStates.waiting_for_quantity_and_price)
async def receive_quantity_and_price(message: Message, state: FSMContext, api: ApiClient, **kwargs) -> None:
    quantity_str, _, price_str = message.text.partition(" ")
    data = await state.get_data()
    part = await api.add_part_item(
        visit_id=data["visit_id"],
        work_item_id=data["work_item_id"],
        name=data["name"],
        quantity=int(quantity_str),
        unit_price=float(price_str),
    )
    await state.clear()
    await message.answer(f"Запчасть добавлена: {part['name']}")
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/bot/test_part_items_handler.py -v`
Expected: PASS

- [ ] **Step 6: Register the router in `bot/main.py`**

Add `from bot.handlers import part_items` and `dp.include_router(part_items.router)`.

- [ ] **Step 7: Run full bot test suite**

Run: `uv run pytest tests/bot/ -v`
Expected: all pass

- [ ] **Step 8: Commit**

```bash
git add bot/api_client.py bot/handlers/part_items.py bot/main.py tests/bot/test_part_items_handler.py
git commit -m "feat: bot part-item creation"
```

---

## Task 13: Bot — documents handler

**Files:**
- Modify: `bot/api_client.py`
- Create: `bot/handlers/documents.py`
- Modify: `bot/main.py`
- Test: `tests/bot/test_documents_handler.py`

**Interfaces:**
- Consumes: `ApiClient`.
- Produces: `ApiClient.generate_document(visit_id: str) -> dict` (returns `{"document_url": ...}`), `bot.handlers.documents.router` with a callback handler triggered by a "Сформировать PDF" inline button (`callback_data=f"gen_doc:{visit_id}"`, added to `send_visit_card`'s keyboard in this task).

- [ ] **Step 1: Write the failing test**

Create `tests/bot/test_documents_handler.py`:

```python
from unittest.mock import AsyncMock

from bot.handlers.documents import generate_document_callback


async def test_generate_document_callback_sends_url():
    callback = AsyncMock()
    callback.data = "gen_doc:visit1"
    api = AsyncMock()
    api.generate_document.return_value = {"document_url": "/storage/visits/visit1.pdf"}

    await generate_document_callback(callback, api=api)

    api.generate_document.assert_awaited_once_with("visit1")
    callback.message.answer.assert_awaited_once()
    callback.answer.assert_awaited_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/bot/test_documents_handler.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bot.handlers.documents'`

- [ ] **Step 3: Add document method to `ApiClient`**

In `bot/api_client.py`, add:

```python
    async def generate_document(self, visit_id: str) -> dict:
        return await self.post(f"/visits/{visit_id}/document")
```

- [ ] **Step 4: Implement `bot/handlers/documents.py`**

```python
from aiogram import Router
from aiogram.types import CallbackQuery

from bot.api_client import ApiClient

router = Router()


@router.callback_query(lambda c: c.data.startswith("gen_doc:"))
async def generate_document_callback(callback: CallbackQuery, api: ApiClient, **kwargs) -> None:
    _, visit_id = callback.data.split(":")
    result = await api.generate_document(visit_id)
    await callback.message.answer(f"Документ готов: {result['document_url']}")
    await callback.answer()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/bot/test_documents_handler.py -v`
Expected: PASS

- [ ] **Step 6: Add the "Сформировать PDF" button to `send_visit_card`**

In `bot/handlers/visits.py`, in `send_visit_card`, after the status-transition buttons loop, add:

```python
    builder.button(text="Сформировать PDF", callback_data=f"gen_doc:{visit['id']}")
```

(before the final `builder.adjust(1)` call)

- [ ] **Step 7: Register the router in `bot/main.py`**

Add `from bot.handlers import documents` and `dp.include_router(documents.router)`.

- [ ] **Step 8: Run full bot test suite**

Run: `uv run pytest tests/bot/ -v`
Expected: all pass

- [ ] **Step 9: Commit**

```bash
git add bot/api_client.py bot/handlers/documents.py bot/handlers/visits.py bot/main.py tests/bot/test_documents_handler.py
git commit -m "feat: bot PDF document generation from the visit card"
```

---

## Task 14: Bot — search handler

**Files:**
- Create: `bot/handlers/search.py`
- Modify: `bot/main.py`
- Test: `tests/bot/test_search_handler.py`

**Interfaces:**
- Consumes: `ApiClient.search` (already added in Task 8).
- Produces: `bot.handlers.search.router` — pressing the "Поиск" menu button asks for a query, then renders result cards as text (client/vehicle matches from `GET /search`).

- [ ] **Step 1: Write the failing test**

Create `tests/bot/test_search_handler.py`:

```python
from unittest.mock import AsyncMock

from bot.handlers.search import receive_search_query


async def test_receive_search_query_lists_results():
    message = AsyncMock()
    message.text = "Иванов"
    api = AsyncMock()
    api.search.return_value = [{"client": {"full_name": "Иван Иванов", "phone": "79991234567"}}]

    await receive_search_query(message, api=api)

    api.search.assert_awaited_once_with("Иванов")
    message.answer.assert_awaited_once()
    assert "Иванов" in message.answer.await_args.args[0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/bot/test_search_handler.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bot.handlers.search'`

- [ ] **Step 3: Implement `bot/handlers/search.py`**

```python
from aiogram import Router, F
from aiogram.types import Message

from bot.api_client import ApiClient

router = Router()


@router.message(F.text == "Поиск")
async def start_search(message: Message, **kwargs) -> None:
    await message.answer("Введите телефон, VIN, гос.номер или имя клиента:")


@router.message(F.text)
async def receive_search_query(message: Message, api: ApiClient, **kwargs) -> None:
    results = await api.search(message.text)
    if not results:
        await message.answer("Ничего не найдено.")
        return
    lines = []
    for r in results:
        client = r.get("client")
        if client:
            lines.append(f"{client['full_name']} — {client['phone']}")
    await message.answer("\n".join(lines) or "Ничего не найдено.")
```

**Note for the implementer:** this handler's bare `@router.message(F.text)` catch-all must be registered on a `Router` included *last* in `bot/main.py` (after every other handler's more specific filters), otherwise it will swallow messages meant for other wizards' plain-text steps (e.g. `NewClientStates.waiting_for_phone`). Confirm ordering when wiring `bot/main.py` in Step 5.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/bot/test_search_handler.py -v`
Expected: PASS

- [ ] **Step 5: Register the router in `bot/main.py` — last**

Add `from bot.handlers import search` and `dp.include_router(search.router)` as the **final** `include_router` call, after all other handler routers (aiogram tries routers in registration order; FSM-state-scoped handlers in other routers only match when that state is active, so they still take priority within their own router, but this catch-all must not be checked before routers whose state-filtered handlers should get first refusal — placing it last is the simplest correct ordering).

- [ ] **Step 6: Run full bot test suite**

Run: `uv run pytest tests/bot/ -v`
Expected: all pass

- [ ] **Step 7: Commit**

```bash
git add bot/handlers/search.py bot/main.py tests/bot/test_search_handler.py
git commit -m "feat: bot search handler"
```

---

## Task 15: Bot — consent (paper registration) handler

**Files:**
- Modify: `bot/api_client.py`
- Create: `bot/handlers/consent.py`
- Modify: `bot/main.py`
- Test: `tests/bot/test_consent_handler.py`

**Interfaces:**
- Consumes: `ApiClient`.
- Produces: `ApiClient.register_paper_consent(full_name: str, phone: str) -> dict`, `bot.handlers.consent.router` — a two-step wizard reusing the same phone→full_name shape as Task 8's client wizard but calling `POST /consent/paper` instead of `POST /clients`.

- [ ] **Step 1: Write the failing test**

Create `tests/bot/test_consent_handler.py`:

```python
from unittest.mock import AsyncMock

from bot.handlers.consent import receive_paper_full_name


async def test_receive_paper_full_name_registers_via_api():
    message = AsyncMock()
    message.text = "Пётр Петров"
    api = AsyncMock()
    api.register_paper_consent.return_value = {"id": "c1", "full_name": "Пётр Петров"}

    from aiogram.fsm.context import FSMContext
    from aiogram.fsm.storage.memory import MemoryStorage
    from aiogram.fsm.storage.base import StorageKey

    state = FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=1, user_id=1))
    await state.update_data(phone="79997654321")

    await receive_paper_full_name(message, state, api=api)

    api.register_paper_consent.assert_awaited_once_with(full_name="Пётр Петров", phone="79997654321")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/bot/test_consent_handler.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bot.handlers.consent'`

- [ ] **Step 3: Add consent method to `ApiClient`**

In `bot/api_client.py`, add:

```python
    async def register_paper_consent(self, full_name: str, phone: str) -> dict:
        return await self.post("/consent/paper", json={"full_name": full_name, "phone": phone})
```

- [ ] **Step 4: Implement `bot/handlers/consent.py`**

```python
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from bot.api_client import ApiClient

router = Router()


class PaperConsentStates(StatesGroup):
    waiting_for_phone = State()
    waiting_for_full_name = State()


@router.message(F.text == "Регистрация клиента (бумага)")
async def start_paper_consent(message: Message, state: FSMContext, **kwargs) -> None:
    await state.set_state(PaperConsentStates.waiting_for_phone)
    await message.answer("Введите телефон клиента:")


@router.message(PaperConsentStates.waiting_for_phone)
async def receive_paper_phone(message: Message, state: FSMContext, **kwargs) -> None:
    await state.update_data(phone=message.text)
    await state.set_state(PaperConsentStates.waiting_for_full_name)
    await message.answer("Введите ФИО клиента:")


@router.message(PaperConsentStates.waiting_for_full_name)
async def receive_paper_full_name(message: Message, state: FSMContext, api: ApiClient, **kwargs) -> None:
    data = await state.get_data()
    client = await api.register_paper_consent(full_name=message.text, phone=data["phone"])
    await state.clear()
    await message.answer(f"Клиент зарегистрирован (бумажное согласие): {client['full_name']}")
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/bot/test_consent_handler.py -v`
Expected: PASS

- [ ] **Step 6: Register the router in `bot/main.py`**

Add `from bot.handlers import consent` and `dp.include_router(consent.router)` — before `search.router` (Task 14's catch-all must stay last).

- [ ] **Step 7: Run full bot test suite**

Run: `uv run pytest tests/bot/ -v`
Expected: all pass

- [ ] **Step 8: Commit**

```bash
git add bot/api_client.py bot/handlers/consent.py bot/main.py tests/bot/test_consent_handler.py
git commit -m "feat: bot paper-consent client registration"
```

---

## Task 16: Bot — admin handler (create staff)

**Files:**
- Modify: `bot/api_client.py`
- Create: `bot/handlers/admin.py`
- Modify: `bot/main.py`
- Test: `tests/bot/test_admin_handler.py`

**Interfaces:**
- Consumes: `ApiClient`, `NewStaffStates`.
- Produces: `ApiClient.create_staff_user(role: str, full_name: str, telegram_id: int | None) -> dict`, `bot.handlers.admin.router` — role-picker (inline buttons: ADMIN/MASTER/MECHANIC) → full name → telegram_id (optional, "-" to skip) → `POST /users`.

- [ ] **Step 1: Write the failing test**

Create `tests/bot/test_admin_handler.py`:

```python
from unittest.mock import AsyncMock

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.base import StorageKey

from bot.handlers.admin import receive_telegram_id
from bot.states import NewStaffStates


def _fsm_context() -> FSMContext:
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=1, user_id=1)
    return FSMContext(storage=storage, key=key)


async def test_receive_telegram_id_creates_staff_user():
    message = AsyncMock()
    message.text = "555222"
    state = _fsm_context()
    await state.update_data(role="mechanic", full_name="Механик Вася")
    api = AsyncMock()
    api.create_staff_user.return_value = {"id": "u2", "full_name": "Механик Вася"}

    await receive_telegram_id(message, state, api=api)

    api.create_staff_user.assert_awaited_once_with(role="mechanic", full_name="Механик Вася", telegram_id=555222)
    assert (await state.get_state()) is None


async def test_receive_telegram_id_dash_means_skip():
    message = AsyncMock()
    message.text = "-"
    state = _fsm_context()
    await state.update_data(role="mechanic", full_name="Механик Вася")
    api = AsyncMock()
    api.create_staff_user.return_value = {"id": "u2", "full_name": "Механик Вася"}

    await receive_telegram_id(message, state, api=api)

    api.create_staff_user.assert_awaited_once_with(role="mechanic", full_name="Механик Вася", telegram_id=None)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/bot/test_admin_handler.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bot.handlers.admin'`

- [ ] **Step 3: Add staff-creation method to `ApiClient`**

In `bot/api_client.py`, add:

```python
    async def create_staff_user(self, role: str, full_name: str, telegram_id: int | None) -> dict:
        return await self.post(
            "/users", json={"role": role, "full_name": full_name, "telegram_id": telegram_id}
        )
```

- [ ] **Step 4: Implement `bot/handlers/admin.py`**

```python
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.api_client import ApiClient
from bot.states import NewStaffStates

router = Router()


@router.message(F.text == "Добавить сотрудника")
async def start_new_staff(message: Message, state: FSMContext, **kwargs) -> None:
    builder = InlineKeyboardBuilder()
    for role in ("admin", "master", "mechanic"):
        builder.button(text=role, callback_data=f"staff_role:{role}")
    builder.adjust(1)
    await state.set_state(NewStaffStates.choosing_role)
    await message.answer("Выберите роль:", reply_markup=builder.as_markup())


@router.message(NewStaffStates.waiting_for_full_name)
async def receive_staff_full_name(message: Message, state: FSMContext, **kwargs) -> None:
    await state.update_data(full_name=message.text)
    await state.set_state(NewStaffStates.waiting_for_telegram_id)
    await message.answer("Введите Telegram ID сотрудника (или «-», если пока неизвестен):")


@router.message(NewStaffStates.waiting_for_telegram_id)
async def receive_telegram_id(message: Message, state: FSMContext, api: ApiClient, **kwargs) -> None:
    telegram_id = None if message.text.strip() == "-" else int(message.text)
    data = await state.get_data()
    user = await api.create_staff_user(role=data["role"], full_name=data["full_name"], telegram_id=telegram_id)
    await state.clear()
    await message.answer(f"Сотрудник создан: {user['full_name']}")
```

Add the callback handler that connects the role picker to the full-name step:

```python
@router.callback_query(lambda c: c.data.startswith("staff_role:"))
async def choose_staff_role(callback, state: FSMContext, **kwargs) -> None:
    _, role = callback.data.split(":")
    await state.update_data(role=role)
    await state.set_state(NewStaffStates.waiting_for_full_name)
    await callback.message.answer("Введите ФИО сотрудника:")
    await callback.answer()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/bot/test_admin_handler.py -v`
Expected: PASS

- [ ] **Step 6: Register the router in `bot/main.py`**

Add `from bot.handlers import admin` and `dp.include_router(admin.router)` — before `search.router`.

- [ ] **Step 7: Run full bot test suite**

Run: `uv run pytest tests/bot/ -v`
Expected: all pass

- [ ] **Step 8: Commit**

```bash
git add bot/api_client.py bot/handlers/admin.py bot/main.py tests/bot/test_admin_handler.py
git commit -m "feat: bot admin staff-creation wizard"
```

---

## Task 17: Bot — mechanic handler ("Мои работы")

**Files:**
- Modify: `bot/api_client.py`
- Create: `bot/handlers/mechanic.py`
- Modify: `bot/main.py`
- Test: `tests/bot/test_mechanic_handler.py`

**Interfaces:**
- Consumes: `ApiClient`, `ApiClient.update_work_item_status` (Task 11).
- Produces: `ApiClient.list_my_work_items() -> list[dict]` (calls `GET /work-items/mine`, Task 2's backend route), `bot.handlers.mechanic.router` — "Мои работы" button lists assigned items with an inline status-change button per item.

- [ ] **Step 1: Write the failing test**

Create `tests/bot/test_mechanic_handler.py`:

```python
from unittest.mock import AsyncMock

from bot.handlers.mechanic import show_my_work_items


async def test_show_my_work_items_lists_items():
    message = AsyncMock()
    api = AsyncMock()
    api.list_my_work_items.return_value = [
        {"id": "wi1", "visit_id": "visit1", "status": "not_ready", "free_text_name": "Замена масла", "catalog_item_id": None}
    ]

    await show_my_work_items(message, api=api)

    api.list_my_work_items.assert_awaited_once()
    message.answer.assert_awaited_once()
    assert "Замена масла" in message.answer.await_args.args[0]


async def test_show_my_work_items_handles_empty_list():
    message = AsyncMock()
    api = AsyncMock()
    api.list_my_work_items.return_value = []

    await show_my_work_items(message, api=api)

    message.answer.assert_awaited_once_with("У вас нет назначенных работ.")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/bot/test_mechanic_handler.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bot.handlers.mechanic'`

- [ ] **Step 3: Add method to `ApiClient`**

In `bot/api_client.py`, add:

```python
    async def list_my_work_items(self) -> list[dict]:
        return await self.get("/work-items/mine")
```

- [ ] **Step 4: Implement `bot/handlers/mechanic.py`**

```python
from aiogram import Router, F
from aiogram.types import Message

from bot.api_client import ApiClient

router = Router()


@router.message(F.text == "Мои работы")
async def show_my_work_items(message: Message, api: ApiClient, **kwargs) -> None:
    items = await api.list_my_work_items()
    if not items:
        await message.answer("У вас нет назначенных работ.")
        return
    lines = [f"{i['free_text_name'] or i['catalog_item_id']} — {i['status']} (заезд {i['visit_id']})" for i in items]
    await message.answer("\n".join(lines))
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/bot/test_mechanic_handler.py -v`
Expected: PASS

- [ ] **Step 6: Register the router in `bot/main.py`**

Add `from bot.handlers import mechanic` and `dp.include_router(mechanic.router)` — before `search.router`.

- [ ] **Step 7: Run full bot test suite**

Run: `uv run pytest tests/bot/ -v`
Expected: all pass

- [ ] **Step 8: Commit**

```bash
git add bot/api_client.py bot/handlers/mechanic.py bot/main.py tests/bot/test_mechanic_handler.py
git commit -m "feat: bot mechanic 'my work items' list"
```

---

## Task 18: Final integration pass

**Files:**
- Modify: `bot/main.py` (router-order audit only, per Task 14's ordering note)
- No new production files — verification and cleanup only.

**Interfaces:**
- Consumes: everything built in Tasks 1–17.
- Produces: nothing new — confirms the whole system imports, boots, and passes its full test suite together.

- [ ] **Step 1: Audit `bot/main.py` router registration order**

Read the final `bot/main.py`. Confirm `search.router` (Task 14's catch-all `@router.message(F.text)`) is registered last, after `start`, `clients`, `vehicles`, `visits`, `work_items`, `part_items`, `documents`, `consent`, `admin`, `mechanic`. Reorder the `include_router` calls if any handler task appended itself in the wrong position relative to this rule.

- [ ] **Step 2: Verify the bot module tree imports cleanly**

Run: `uv run python -c "import bot.main; print('bot imports OK')"`
Expected: `bot imports OK` (no `ImportError`/`ModuleNotFoundError`; this will fail fast if `BOT_TOKEN` parsing or any circular import was missed — it should not require a live Telegram token since `Bot(token=...)` doesn't make a network call at construction time)

- [ ] **Step 3: Verify the backend still boots and lists its new routes**

Run:
```bash
uv run python -c "
from app.main import app
paths = sorted(r.path for r in app.routes)
assert '/users/by-telegram/{telegram_id}' in paths
assert '/work-items/mine' in paths
print('backend routes OK:', len(paths))
"
```
Expected: `backend routes OK: <N>` with no assertion error

- [ ] **Step 4: Run the entire test suite (backend + bot)**

Run: `uv run pytest -q`
Expected: all tests pass (backend's pre-existing 52 + this plan's new backend tests from Tasks 1–3 + all `tests/bot/` tests from Tasks 4–17)

- [ ] **Step 5: Manual smoke test (documented, not automated)**

Not scriptable in this repo (needs a real Telegram bot token and a real chat) — record this as a manual pre-merge step: set `BOT_TOKEN`/`TELEGRAM_BOT_TOKEN` to a real token in `.env`, run `uv run python -m bot.main`, message the bot from a Telegram account whose `telegram_id` was set on a test `User` row, and walk through: `/start` → new visit → add work item → change status to `ready` (confirm a Telegram message arrives, proving `TelegramNotificationSender` fired end-to-end) → generate PDF.

- [ ] **Step 6: Commit**

```bash
git add bot/main.py
git commit -m "chore: final bot router-order audit after full-coverage build-out"
```

(If Step 1 found nothing to reorder, this commit is empty — skip it and note in the task report that the audit found the order already correct.)
