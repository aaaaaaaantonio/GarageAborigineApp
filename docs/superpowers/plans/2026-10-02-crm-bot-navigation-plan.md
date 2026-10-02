# CRM-бот: навигация — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Сделать бота пригодным для ежедневной работы: кликабельный поиск с карточками клиента/машины, списки заездов («в работе» и история), заезды от ADMIN с выбором мастера, «Новый заезд» из карточки машины, карточка машины и история работ для механика без ПДн и денег, команды в меню Telegram.

**Architecture:** Backend получает read-эндпоинты со «сводками» (один SQL с JOIN, без N+1) и точечные расширения прав для MECHANIC (только данные машины). Бот остаётся тонким клиентом: новый роутер `bot/handlers/navigation.py` рисует карточки/списки из готовых ответов API; визард заезда получает шаг выбора мастера и вход из карточки машины.

**Tech Stack:** Python 3.14, FastAPI, SQLAlchemy 2 async, PostgreSQL 15, aiogram 3, httpx, pytest (+pytest-asyncio auto mode, respx).

**Spec:** `docs/superpowers/specs/2026-10-02-crm-bot-navigation-design.md`

## Global Constraints

- Работать в ветке `bot-navigation` (уже создана, содержит спек).
- Тесты: `docker compose up -d postgres` должен быть запущен; база `crm_test` существует. Команда: `.venv/bin/pytest`.
- Схема БД не меняется, миграций нет.
- Мягко удалённые записи (`deleted_at IS NOT NULL`) исключаются из всех новых списков.
- Лимит списков — 30 (`VISIT_LIST_LIMIT`, `WORK_HISTORY_LIMIT`), запрос берёт 31 строку, `has_more = len(rows) > 30`.
- MECHANIC: доступны только `GET /search` (только машины), `GET /vehicles/{id}`, `GET /vehicles/{id}/work-history`. `GET /clients/{id}`, `GET /clients/{id}/vehicles`, `GET /vehicles/{id}/owner`, `GET /visits*` → 403.
- В ответах `GET /vehicles/{id}/work-history` нет полей с ценами (`norm_hours`, `hourly_rate`, сумм) и клиента.
- `callback_data` ≤ 64 байт; UUID в новых callback'ах — через `bot.callback_ids.encode_id` (22 символа).
- Даты в боте — по Москве: фиксированный `timezone(timedelta(hours=3))`, без `tzdata`.
- Русские статусы заезда: received «Принят», diagnostics «Диагностика», approval «Согласование», in_progress «Ремонт», waiting_parts «Ждём запчасти», ready «Готов», issued «Выдан», cancelled «Отменён».
- Русские статусы работ: not_ready «Не начата», in_progress «В работе», waiting_parts «Ждёт запчасти», ready «Готово».
- Коммиты — Conventional Commits, в конце сообщения строка `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

- **Несколько визитов в одной транзакции имеют одинаковый `created_at`** (server_default `now()` = время транзакции) — сортировка «новые сверху» в тестах недетерминирована, если не проставить `created_at` явно. Тесты Task 1 и Task 5 проставляют его явно; порядок дополнительно стабилизирован `Visit.id`.
- **ADMIN, у которого нет своих заездов,** должен видеть все заезды по дате, без ⭐ — тест в Task 7 (`test_active_visits_admin_sees_no_stars`).
- **Механик ищет по ФИО/телефону** — должен получить «Ничего не найдено…» без утечки клиентов: тест на уровне API (Task 4) и бота (Task 8).
- **Откат пробега у ADMIN после выбора мастера** — повторный ввод/подтверждение пробега не должен заново спрашивать мастера и должен создать заезд с выбранным мастером: тест в Task 9 (`test_admin_mileage_rollback_keeps_chosen_master`).
- **Старая кнопка `master_pick` вне визарда** — должна ответить «Кнопка устарела», а не создать заезд: тест в Task 9 (параметр в `test_state_bound_wizard_callbacks_do_not_fire_without_state`).

---

## File Structure

| Файл | Ответственность |
|---|---|
| `app/modules/visits/schemas.py` (mod) | `VisitOut` со сводкой, `VisitListOut` |
| `app/modules/visits/repository.py` (mod) | SQL сводки заезда, список с фильтрами |
| `app/modules/visits/service.py` (mod) | `get_summary`, `list_visits`, лимит |
| `app/modules/visits/router.py` (mod) | `GET /visits`, сводка в GET/POST/PATCH |
| `app/modules/vehicles/repository.py`, `service.py`, `router.py` (mod) | текущие машины клиента, текущий владелец, доступ MECHANIC к `GET /vehicles/{id}`, `GET /vehicles/{id}/owner` |
| `app/modules/clients/router.py` (mod) | `GET /clients/{id}/vehicles` |
| `app/modules/users/service.py`, `router.py` (mod) | `GET /users/masters` |
| `app/modules/search/service.py`, `router.py` (mod) | фильтр сущностей, только машины для MECHANIC |
| `app/modules/visits/work_items_schemas.py`, `work_items_service.py` (mod) | история работ по машине |
| `app/modules/visits/vehicle_history_router.py` (new) | `GET /vehicles/{id}/work-history` |
| `app/main.py` (mod) | подключить новый роутер |
| `bot/formatting.py` (new) | даты по МСК |
| `bot/visit_status.py` (new) | русские статусы заезда |
| `bot/work_item_status.py` (mod) | русские статусы работ, подписи кнопок |
| `bot/api_client.py` (mod) | методы новых эндпоинтов |
| `bot/handlers/visits.py` (mod) | шапка карточки, выбор мастера, заезд из карточки машины |
| `bot/handlers/mechanic.py` (mod) | русский статус в «Моих работах» |
| `bot/handlers/navigation.py` (new) | «Заезды в работе», карточки клиента/машины/заезда, истории |
| `bot/handlers/search.py` (mod) | кнопки результатов, режим механика |
| `bot/keyboards.py`, `bot/handlers/menu.py` (mod) | меню по ролям |
| `bot/states.py` (mod) | `NewVisitStates.choosing_master` |
| `bot/main.py` (mod) | роутер навигации, команды Telegram |
| `README.md` (mod) | что умеет бот по ролям |

---

### Task 1: Сводка заезда и `GET /visits`

**Files:**
- Modify: `app/modules/visits/schemas.py`
- Modify: `app/modules/visits/repository.py`
- Modify: `app/modules/visits/service.py`
- Modify: `app/modules/visits/router.py`
- Test: `tests/modules/visits/test_visit_routes.py` (new)

**Interfaces:**
- Produces: `VisitOut` (поля: `id, status, mileage_at_intake, total_amount, created_at, client_id, client_name, vehicle_id, plate_number, make_model, assigned_master_id, master_name`); `VisitListOut(items: list[VisitOut], has_more: bool)`; `VisitService.get_summary(visit_id) -> VisitOut | None`; `VisitService.list_visits(acting_user, *, active=False, client_id=None, vehicle_id=None) -> VisitListOut`; HTTP `GET /visits?active=&client_id=&vehicle_id=` → `VisitListOut`.

- [ ] **Step 1: Write the failing tests**

Create `tests/modules/visits/test_visit_routes.py`:

```python
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.db import get_session
from app.core.enums import UserRole, VisitStatus
from app.main import app
from app.modules.clients.schemas import ClientCreate
from app.modules.clients.service import ClientService
from app.modules.users.models import User
from app.modules.vehicles.schemas import VehicleCreate
from app.modules.vehicles.service import VehicleService
from app.modules.visits.schemas import VisitCreate
from app.modules.visits.service import VISIT_LIST_LIMIT, VisitService

BASE = datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc)


@pytest.fixture
def api_app(session):
    async def override_get_session():
        yield session

    app.dependency_overrides[get_session] = override_get_session
    yield app
    app.dependency_overrides.clear()


async def _get(api_app, path, user):
    transport = ASGITransport(app=api_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(path, headers={"X-User-Id": str(user.id)})


async def _world(session):
    admin = User(role=UserRole.ADMIN, full_name="Админ", branch_id=uuid.uuid4())
    me = User(role=UserRole.MASTER, full_name="Мастер Я", branch_id=uuid.uuid4())
    other = User(role=UserRole.MASTER, full_name="Мастер Другой", branch_id=uuid.uuid4())
    mechanic = User(role=UserRole.MECHANIC, full_name="Механик", branch_id=uuid.uuid4())
    session.add_all([admin, me, other, mechanic])
    await session.flush()
    client = await ClientService(session).create_client(
        ClientCreate(full_name="Иванов Пётр", phone="79990000001"), admin
    )
    vehicle = await VehicleService(session).create_vehicle(
        VehicleCreate(vin="A" * 17, plate_number="А123ВС77", make="Toyota", model="Camry"), admin
    )
    return admin, me, other, mechanic, client, vehicle


async def _visit(session, admin, client, vehicle, master, hours, status=VisitStatus.RECEIVED):
    visit = await VisitService(session).create_visit(
        VisitCreate(
            client_id=client.id,
            vehicle_id=vehicle.id,
            assigned_master_id=master.id,
            mileage_at_intake=1000,
            mileage_manually_confirmed=True,
        ),
        admin,
    )
    visit.created_at = BASE + timedelta(hours=hours)
    visit.status = status
    await session.flush()
    return visit


async def test_list_active_puts_viewer_visits_first_then_newest(api_app, session):
    admin, me, other, mechanic, client, vehicle = await _world(session)
    mine_old = await _visit(session, admin, client, vehicle, me, hours=1)
    theirs_new = await _visit(session, admin, client, vehicle, other, hours=3)
    mine_new = await _visit(session, admin, client, vehicle, me, hours=2)

    resp = await _get(api_app, "/visits?active=true", me)

    assert resp.status_code == 200
    ids = [item["id"] for item in resp.json()["items"]]
    assert ids == [str(mine_new.id), str(mine_old.id), str(theirs_new.id)]
    assert resp.json()["has_more"] is False


async def test_list_active_excludes_issued_and_cancelled(api_app, session):
    admin, me, other, mechanic, client, vehicle = await _world(session)
    open_visit = await _visit(session, admin, client, vehicle, me, hours=1)
    await _visit(session, admin, client, vehicle, me, hours=2, status=VisitStatus.ISSUED)
    await _visit(session, admin, client, vehicle, me, hours=3, status=VisitStatus.CANCELLED)

    active = await _get(api_app, "/visits?active=true", me)
    everything = await _get(api_app, "/visits", me)

    assert [i["id"] for i in active.json()["items"]] == [str(open_visit.id)]
    assert len(everything.json()["items"]) == 3


async def test_list_filters_by_client_and_vehicle(api_app, session):
    admin, me, other, mechanic, client, vehicle = await _world(session)
    client2 = await ClientService(session).create_client(
        ClientCreate(full_name="Петрова Анна", phone="79990000002"), admin
    )
    vehicle2 = await VehicleService(session).create_vehicle(
        VehicleCreate(vin="B" * 17, plate_number="В001ОР50", make="Lada", model="Vesta"), admin
    )
    first = await _visit(session, admin, client, vehicle, me, hours=1)
    second = await _visit(session, admin, client2, vehicle2, me, hours=2)

    by_client = await _get(api_app, f"/visits?client_id={client.id}", me)
    by_vehicle = await _get(api_app, f"/visits?vehicle_id={vehicle2.id}", me)

    assert [i["id"] for i in by_client.json()["items"]] == [str(first.id)]
    assert [i["id"] for i in by_vehicle.json()["items"]] == [str(second.id)]


async def test_list_excludes_soft_deleted_visits_clients_vehicles(api_app, session):
    admin, me, other, mechanic, client, vehicle = await _world(session)
    deleted_visit = await _visit(session, admin, client, vehicle, me, hours=1)
    deleted_visit.deleted_at = BASE
    client2 = await ClientService(session).create_client(
        ClientCreate(full_name="Удалённый", phone="79990000003"), admin
    )
    await _visit(session, admin, client2, vehicle, me, hours=2)
    client2.deleted_at = BASE
    vehicle2 = await VehicleService(session).create_vehicle(
        VehicleCreate(vin="C" * 17, plate_number="Х999ХХ99", make="Kia", model="Rio"), admin
    )
    await _visit(session, admin, client, vehicle2, me, hours=3)
    vehicle2.deleted_at = BASE
    kept = await _visit(session, admin, client, vehicle, me, hours=4)
    await session.flush()

    resp = await _get(api_app, "/visits", me)

    assert [i["id"] for i in resp.json()["items"]] == [str(kept.id)]


async def test_list_reports_has_more_over_limit(api_app, session):
    admin, me, other, mechanic, client, vehicle = await _world(session)
    for hours in range(VISIT_LIST_LIMIT + 1):
        await _visit(session, admin, client, vehicle, me, hours=hours)

    resp = await _get(api_app, "/visits", me)

    assert len(resp.json()["items"]) == VISIT_LIST_LIMIT
    assert resp.json()["has_more"] is True


async def test_list_items_carry_summary_fields(api_app, session):
    admin, me, other, mechanic, client, vehicle = await _world(session)
    visit = await _visit(session, admin, client, vehicle, me, hours=1)

    item = (await _get(api_app, "/visits", admin)).json()["items"][0]

    assert item["id"] == str(visit.id)
    assert item["status"] == "received"
    assert item["client_id"] == str(client.id)
    assert item["client_name"] == "Иванов Пётр"
    assert item["vehicle_id"] == str(vehicle.id)
    assert item["plate_number"] == vehicle.plate_number
    assert item["make_model"] == "Toyota Camry"
    assert item["assigned_master_id"] == str(me.id)
    assert item["master_name"] == "Мастер Я"
    assert item["created_at"].startswith("2026-10-01T10:00:00")


async def test_list_forbidden_for_mechanic(api_app, session):
    admin, me, other, mechanic, client, vehicle = await _world(session)

    resp = await _get(api_app, "/visits", mechanic)

    assert resp.status_code == 403


async def test_get_visit_returns_summary(api_app, session):
    admin, me, other, mechanic, client, vehicle = await _world(session)
    visit = await _visit(session, admin, client, vehicle, me, hours=1)

    body = (await _get(api_app, f"/visits/{visit.id}", me)).json()

    assert body["client_name"] == "Иванов Пётр"
    assert body["master_name"] == "Мастер Я"
    assert body["make_model"] == "Toyota Camry"


async def test_create_and_change_status_routes_return_summary(api_app, session):
    admin, me, other, mechanic, client, vehicle = await _world(session)
    transport = ASGITransport(app=api_app)
    headers = {"X-User-Id": str(me.id)}
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        created = await http.post(
            "/visits",
            json={
                "client_id": str(client.id),
                "vehicle_id": str(vehicle.id),
                "assigned_master_id": str(me.id),
                "mileage_at_intake": 2000,
            },
            headers=headers,
        )
        changed = await http.patch(
            f"/visits/{created.json()['id']}/status", json={"new_status": "diagnostics"}, headers=headers
        )

    assert created.status_code == 201
    assert created.json()["plate_number"] == vehicle.plate_number
    assert changed.status_code == 200
    assert changed.json()["status"] == "diagnostics"
    assert changed.json()["client_name"] == "Иванов Пётр"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/modules/visits/test_visit_routes.py -q`
Expected: collection ERROR `ImportError: cannot import name 'VISIT_LIST_LIMIT'`.

- [ ] **Step 3: Extend the schemas**

Replace `VisitOut` in `app/modules/visits/schemas.py` and add `VisitListOut` (add `from datetime import datetime` to imports):

```python
class VisitOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: VisitStatus
    mileage_at_intake: int
    total_amount: float
    created_at: datetime
    client_id: uuid.UUID
    client_name: str
    vehicle_id: uuid.UUID
    plate_number: str
    make_model: str
    assigned_master_id: uuid.UUID
    master_name: str


class VisitListOut(BaseModel):
    items: list[VisitOut]
    has_more: bool
```

- [ ] **Step 4: Add the summary queries to the repository**

Replace `app/modules/visits/repository.py` with:

```python
import uuid

from sqlalchemy import Row, Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import VisitStatus
from app.modules.clients.models import Client
from app.modules.users.models import User
from app.modules.vehicles.models import Vehicle
from app.modules.visits.models import Visit

CLOSED_STATUSES = (VisitStatus.ISSUED, VisitStatus.CANCELLED)


def _summary_select() -> Select:
    """One row per visit with the names a list or card header needs (no N+1)."""
    return (
        select(
            Visit.id,
            Visit.status,
            Visit.mileage_at_intake,
            Visit.total_amount,
            Visit.created_at,
            Visit.client_id,
            Client.full_name.label("client_name"),
            Visit.vehicle_id,
            Vehicle.plate_number,
            Vehicle.make,
            Vehicle.model,
            Visit.assigned_master_id,
            User.full_name.label("master_name"),
        )
        .join(Client, Client.id == Visit.client_id)
        .join(Vehicle, Vehicle.id == Visit.vehicle_id)
        .join(User, User.id == Visit.assigned_master_id)
    )


class VisitRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, visit: Visit) -> Visit:
        self.session.add(visit)
        await self.session.flush()
        return visit

    async def get(self, visit_id: uuid.UUID) -> Visit | None:
        return await self.session.get(Visit, visit_id)

    async def get_summary(self, visit_id: uuid.UUID) -> Row | None:
        result = await self.session.execute(_summary_select().where(Visit.id == visit_id))
        return result.first()

    async def list_summaries(
        self,
        *,
        viewer_id: uuid.UUID,
        active: bool,
        client_id: uuid.UUID | None,
        vehicle_id: uuid.UUID | None,
        limit: int,
    ) -> list[Row]:
        stmt = _summary_select().where(
            Visit.deleted_at.is_(None), Client.deleted_at.is_(None), Vehicle.deleted_at.is_(None)
        )
        if active:
            stmt = stmt.where(Visit.status.not_in(CLOSED_STATUSES))
        if client_id is not None:
            stmt = stmt.where(Visit.client_id == client_id)
        if vehicle_id is not None:
            stmt = stmt.where(Visit.vehicle_id == vehicle_id)
        stmt = stmt.order_by(
            (Visit.assigned_master_id == viewer_id).desc(), Visit.created_at.desc(), Visit.id
        ).limit(limit)
        return list((await self.session.execute(stmt)).all())
```

- [ ] **Step 5: Add service methods**

In `app/modules/visits/service.py`: change the schemas import to `from app.modules.visits.schemas import VisitCreate, VisitListOut, VisitOut`, add below the imports:

```python
VISIT_LIST_LIMIT = 30


def _summary_out(row) -> VisitOut:
    return VisitOut(
        id=row.id,
        status=row.status,
        mileage_at_intake=row.mileage_at_intake,
        total_amount=row.total_amount,
        created_at=row.created_at,
        client_id=row.client_id,
        client_name=row.client_name,
        vehicle_id=row.vehicle_id,
        plate_number=row.plate_number,
        make_model=f"{row.make} {row.model}",
        assigned_master_id=row.assigned_master_id,
        master_name=row.master_name,
    )
```

and add to `VisitService` (after `get`):

```python
    async def get_summary(self, visit_id) -> VisitOut | None:
        row = await self.repo.get_summary(visit_id)
        return None if row is None else _summary_out(row)

    async def list_visits(
        self,
        acting_user: User,
        *,
        active: bool = False,
        client_id: uuid.UUID | None = None,
        vehicle_id: uuid.UUID | None = None,
    ) -> VisitListOut:
        rows = await self.repo.list_summaries(
            viewer_id=acting_user.id,
            active=active,
            client_id=client_id,
            vehicle_id=vehicle_id,
            limit=VISIT_LIST_LIMIT + 1,
        )
        return VisitListOut(
            items=[_summary_out(r) for r in rows[:VISIT_LIST_LIMIT]],
            has_more=len(rows) > VISIT_LIST_LIMIT,
        )
```

- [ ] **Step 6: Wire the routes**

In `app/modules/visits/router.py`: import `VisitListOut` alongside `VisitCreate, VisitOut, VisitStatusChange`. Add the list route directly after `create_visit`:

```python
@router.get("", response_model=VisitListOut)
async def list_visits(
    active: bool = False,
    client_id: uuid.UUID | None = None,
    vehicle_id: uuid.UUID | None = None,
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MASTER)),
):
    service = VisitService(session)
    return await service.list_visits(acting_user, active=active, client_id=client_id, vehicle_id=vehicle_id)
```

Return the summary from the three existing routes:
- `create_visit`: replace the final `return visit` with `return await service.get_summary(visit.id)`.
- `get_visit`: replace `visit = await service.get(visit_id)` with `visit = await service.get_summary(visit_id)` (the `None` → 404 check stays).
- `change_status`: replace the final `return visit` with `return await service.get_summary(visit.id)`.

- [ ] **Step 7: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/modules/visits/test_visit_routes.py -q`
Expected: `10 passed`.
Run: `.venv/bin/pytest -q`
Expected: all pass (existing `tests/test_end_to_end.py` keeps working because `VisitOut` is a superset).

- [ ] **Step 8: Commit**

```bash
git add app/modules/visits/schemas.py app/modules/visits/repository.py app/modules/visits/service.py app/modules/visits/router.py tests/modules/visits/test_visit_routes.py
git commit -m "feat: GET /visits with summaries; visit responses carry client/vehicle/master

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Машины клиента, владелец машины, доступ механика к машине

**Files:**
- Modify: `app/modules/vehicles/repository.py`
- Modify: `app/modules/vehicles/service.py`
- Modify: `app/modules/vehicles/router.py`
- Modify: `app/modules/clients/router.py`
- Test: `tests/modules/vehicles/test_routes.py` (new)

**Interfaces:**
- Produces: HTTP `GET /clients/{client_id}/vehicles` → `list[VehicleOut]`; `GET /vehicles/{vehicle_id}/owner` → `ClientOut | null`; `GET /vehicles/{vehicle_id}` открыт MECHANIC. `VehicleService.list_current_for_client(client_id) -> list[Vehicle]`, `VehicleService.get_current_owner(vehicle_id) -> Client | None`.

- [ ] **Step 1: Write the failing tests**

Create `tests/modules/vehicles/test_routes.py`:

```python
import uuid
from datetime import date, datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.db import get_session
from app.core.enums import UserRole
from app.main import app
from app.modules.clients.schemas import ClientCreate
from app.modules.clients.service import ClientService
from app.modules.users.models import User
from app.modules.vehicles.schemas import OwnershipCreate, VehicleCreate
from app.modules.vehicles.service import VehicleService


@pytest.fixture
def api_app(session):
    async def override_get_session():
        yield session

    app.dependency_overrides[get_session] = override_get_session
    yield app
    app.dependency_overrides.clear()


async def _get(api_app, path, user):
    transport = ASGITransport(app=api_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(path, headers={"X-User-Id": str(user.id)})


async def _world(session):
    admin = User(role=UserRole.ADMIN, full_name="Админ", branch_id=uuid.uuid4())
    mechanic = User(role=UserRole.MECHANIC, full_name="Механик", branch_id=uuid.uuid4())
    session.add_all([admin, mechanic])
    await session.flush()
    client = await ClientService(session).create_client(
        ClientCreate(full_name="Иванов Пётр", phone="79990000011"), admin
    )
    return admin, mechanic, client


async def _vehicle(session, admin, vin_char, plate):
    return await VehicleService(session).create_vehicle(
        VehicleCreate(vin=vin_char * 17, plate_number=plate, make="Toyota", model="Camry"), admin
    )


async def _own(session, admin, vehicle, client, date_to=None):
    ownership = await VehicleService(session).attach_owner(
        vehicle.id, OwnershipCreate(client_id=client.id, date_from=date(2026, 1, 1)), admin
    )
    ownership.date_to = date_to
    await session.flush()
    return ownership


async def test_client_vehicles_lists_current_ownerships_sorted_by_plate(api_app, session):
    admin, mechanic, client = await _world(session)
    second = await _vehicle(session, admin, "B", "О555ОО77")
    first = await _vehicle(session, admin, "A", "А111АА77")
    sold = await _vehicle(session, admin, "C", "Е222ЕЕ77")
    gone = await _vehicle(session, admin, "D", "К333КК77")
    for v in (second, first):
        await _own(session, admin, v, client)
    await _own(session, admin, sold, client, date_to=date(2026, 5, 1))
    await _own(session, admin, gone, client)
    gone.deleted_at = datetime.now(timezone.utc)
    await session.flush()

    resp = await _get(api_app, f"/clients/{client.id}/vehicles", admin)

    assert resp.status_code == 200
    assert [v["id"] for v in resp.json()] == [str(first.id), str(second.id)]


async def test_client_vehicles_404_for_unknown_client(api_app, session):
    admin, mechanic, client = await _world(session)

    resp = await _get(api_app, f"/clients/{uuid.uuid4()}/vehicles", admin)

    assert resp.status_code == 404


async def test_vehicle_owner_returns_current_owner(api_app, session):
    admin, mechanic, client = await _world(session)
    previous = await ClientService(session).create_client(
        ClientCreate(full_name="Прежний", phone="79990000012"), admin
    )
    vehicle = await _vehicle(session, admin, "A", "А111АА77")
    await _own(session, admin, vehicle, previous, date_to=date(2026, 3, 1))
    await _own(session, admin, vehicle, client)

    resp = await _get(api_app, f"/vehicles/{vehicle.id}/owner", admin)

    assert resp.status_code == 200
    assert resp.json()["id"] == str(client.id)
    assert resp.json()["full_name"] == "Иванов Пётр"


async def test_vehicle_owner_is_null_without_current_owner(api_app, session):
    admin, mechanic, client = await _world(session)
    vehicle = await _vehicle(session, admin, "A", "А111АА77")

    resp = await _get(api_app, f"/vehicles/{vehicle.id}/owner", admin)

    assert resp.status_code == 200
    assert resp.json() is None


async def test_vehicle_owner_404_for_unknown_vehicle(api_app, session):
    admin, mechanic, client = await _world(session)

    resp = await _get(api_app, f"/vehicles/{uuid.uuid4()}/owner", admin)

    assert resp.status_code == 404


async def test_mechanic_can_read_vehicle_but_not_owner_or_client_data(api_app, session):
    admin, mechanic, client = await _world(session)
    vehicle = await _vehicle(session, admin, "A", "А111АА77")
    await _own(session, admin, vehicle, client)

    vehicle_resp = await _get(api_app, f"/vehicles/{vehicle.id}", mechanic)
    owner_resp = await _get(api_app, f"/vehicles/{vehicle.id}/owner", mechanic)
    client_resp = await _get(api_app, f"/clients/{client.id}", mechanic)
    vehicles_resp = await _get(api_app, f"/clients/{client.id}/vehicles", mechanic)

    assert vehicle_resp.status_code == 200
    assert set(vehicle_resp.json()) == {"id", "vin", "plate_number", "make", "model", "mileage_current"}
    assert owner_resp.status_code == 403
    assert client_resp.status_code == 403
    assert vehicles_resp.status_code == 403
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/modules/vehicles/test_routes.py -q`
Expected: FAIL — `/clients/{id}/vehicles` and `/vehicles/{id}/owner` return 404/405, mechanic gets 403 on `GET /vehicles/{id}`.

- [ ] **Step 3: Repository queries**

Append to `VehicleRepository` in `app/modules/vehicles/repository.py` (add `from app.modules.clients.models import Client` to imports):

```python
    async def list_current_for_client(self, client_id: uuid.UUID) -> list[Vehicle]:
        result = await self.session.execute(
            select(Vehicle)
            .join(VehicleOwnership, VehicleOwnership.vehicle_id == Vehicle.id)
            .where(
                VehicleOwnership.client_id == client_id,
                VehicleOwnership.date_to.is_(None),
                Vehicle.deleted_at.is_(None),
            )
            .order_by(Vehicle.plate_number)
        )
        return list(result.scalars().unique())

    async def get_current_owner(self, vehicle_id: uuid.UUID) -> Client | None:
        result = await self.session.execute(
            select(Client)
            .join(VehicleOwnership, VehicleOwnership.client_id == Client.id)
            .where(
                VehicleOwnership.vehicle_id == vehicle_id,
                VehicleOwnership.date_to.is_(None),
                Client.deleted_at.is_(None),
            )
            .order_by(VehicleOwnership.date_from.desc())
        )
        return result.scalars().first()
```

- [ ] **Step 4: Service methods**

Append to `VehicleService` in `app/modules/vehicles/service.py` (add `from app.modules.clients.models import Client`):

```python
    async def list_current_for_client(self, client_id: uuid.UUID) -> list[Vehicle]:
        return await self.repo.list_current_for_client(client_id)

    async def get_current_owner(self, vehicle_id: uuid.UUID) -> Client | None:
        return await self.repo.get_current_owner(vehicle_id)
```

- [ ] **Step 5: Routes**

In `app/modules/vehicles/router.py`: add `from app.modules.clients.schemas import ClientOut`; change `get_vehicle`'s dependency to `require_role(UserRole.ADMIN, UserRole.MASTER, UserRole.MECHANIC)`; add after `get_vehicle`:

```python
@router.get("/{vehicle_id}/owner", response_model=ClientOut | None)
async def get_vehicle_owner(
    vehicle_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MASTER)),
):
    service = VehicleService(session)
    if await service.get(vehicle_id) is None:
        raise HTTPException(404, "Vehicle not found")
    return await service.get_current_owner(vehicle_id)
```

In `app/modules/clients/router.py`: add imports `from app.modules.vehicles.schemas import VehicleOut` and `from app.modules.vehicles.service import VehicleService`; add after `get_client`:

```python
@router.get("/{client_id}/vehicles", response_model=list[VehicleOut])
async def list_client_vehicles(
    client_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MASTER)),
):
    if await ClientService(session).get(client_id) is None:
        raise HTTPException(404, "Client not found")
    return await VehicleService(session).list_current_for_client(client_id)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/modules/vehicles/test_routes.py -q` → `6 passed`.
Run: `.venv/bin/pytest -q` → all pass.

- [ ] **Step 7: Commit**

```bash
git add app/modules/vehicles app/modules/clients/router.py tests/modules/vehicles/test_routes.py
git commit -m "feat: client's current vehicles, vehicle's current owner; mechanics may read vehicles

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: `GET /users/masters`

**Files:**
- Modify: `app/modules/users/service.py`
- Modify: `app/modules/users/router.py`
- Test: `tests/modules/users/test_routes.py` (append)

**Interfaces:**
- Produces: HTTP `GET /users/masters` (ADMIN) → `list[UserOut]`; `UserService.list_masters() -> list[User]`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/modules/users/test_routes.py` (uses its existing `api_app` fixture and `_user` helper):

```python
async def test_list_masters_returns_active_masters_sorted_by_name(api_app, session):
    admin = _user(UserRole.ADMIN, "Админ")
    boris = _user(UserRole.MASTER, "Борис")
    anna = _user(UserRole.MASTER, "Анна")
    fired = _user(UserRole.MASTER, "Уволенный")
    fired.deleted_at = datetime.now(timezone.utc)
    session.add_all([admin, boris, anna, fired, _user(UserRole.MECHANIC, "Механик")])
    await session.flush()

    transport = ASGITransport(app=api_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/users/masters", headers={"X-User-Id": str(admin.id)})

    assert resp.status_code == 200
    assert [u["full_name"] for u in resp.json()] == ["Анна", "Борис"]


async def test_list_masters_forbidden_for_master(api_app, session):
    master = _user(UserRole.MASTER, "Мастер")
    session.add(master)
    await session.flush()

    transport = ASGITransport(app=api_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/users/masters", headers={"X-User-Id": str(master.id)})

    assert resp.status_code == 403
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/modules/users/test_routes.py -q -k masters`
Expected: FAIL — 404/405 (route missing).

- [ ] **Step 3: Implement**

`app/modules/users/service.py`, after `list_mechanics`:

```python
    async def list_masters(self) -> list[User]:
        return await self.repo.list_active_by_role(UserRole.MASTER)
```

`app/modules/users/router.py`, directly after `list_mechanics`:

```python
@router.get("/masters", response_model=list[UserOut])
async def list_masters(
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_role(UserRole.ADMIN)),
):
    service = UserService(session)
    return await service.list_masters()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/modules/users -q` → all pass.

- [ ] **Step 5: Commit**

```bash
git add app/modules/users tests/modules/users/test_routes.py
git commit -m "feat: GET /users/masters for choosing a visit's master

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Поиск механика — только машины

**Files:**
- Modify: `app/modules/search/service.py`
- Modify: `app/modules/search/router.py`
- Test: `tests/modules/search/test_routes.py` (new)

**Interfaces:**
- Produces: `SearchService.search(query: str, entities: set[str] | None = None) -> list[dict]` (`None` = все типы); `GET /search` от MECHANIC возвращает только `entity == "vehicle"`.

- [ ] **Step 1: Write the failing tests**

Create `tests/modules/search/test_routes.py`:

```python
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.db import get_session
from app.core.enums import UserRole
from app.main import app
from app.modules.clients.schemas import ClientCreate
from app.modules.clients.service import ClientService
from app.modules.users.models import User
from app.modules.vehicles.schemas import VehicleCreate
from app.modules.vehicles.service import VehicleService


@pytest.fixture
def api_app(session):
    async def override_get_session():
        yield session

    app.dependency_overrides[get_session] = override_get_session
    yield app
    app.dependency_overrides.clear()


async def _search(api_app, query, user):
    transport = ASGITransport(app=api_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get("/search", params={"q": query}, headers={"X-User-Id": str(user.id)})


async def _world(session):
    master = User(role=UserRole.MASTER, full_name="Мастер", branch_id=uuid.uuid4())
    mechanic = User(role=UserRole.MECHANIC, full_name="Механик", branch_id=uuid.uuid4())
    session.add_all([master, mechanic])
    await session.flush()
    await ClientService(session).create_client(ClientCreate(full_name="Сидоров Олег", phone="79990000021"), master)
    vehicle = await VehicleService(session).create_vehicle(
        VehicleCreate(vin="M" * 17, plate_number="М777ММ77", make="Mazda", model="CX-5"), master
    )
    return master, mechanic, vehicle


async def test_mechanic_search_by_client_phone_or_name_finds_nothing(api_app, session):
    master, mechanic, vehicle = await _world(session)

    by_phone = await _search(api_app, "79990000021", mechanic)
    by_name = await _search(api_app, "Сидоров Олег", mechanic)

    assert by_phone.status_code == 200
    assert by_phone.json() == []
    assert by_name.json() == []


async def test_mechanic_search_by_plate_finds_vehicle(api_app, session):
    master, mechanic, vehicle = await _world(session)

    resp = await _search(api_app, "М777ММ77", mechanic)

    assert [(r["entity"], r["id"]) for r in resp.json()] == [("vehicle", str(vehicle.id))]


async def test_master_search_by_phone_still_finds_client(api_app, session):
    master, mechanic, vehicle = await _world(session)

    resp = await _search(api_app, "79990000021", master)

    assert [r["entity"] for r in resp.json()] == ["client"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/modules/search/test_routes.py -q`
Expected: `test_mechanic_search_by_client_phone_or_name_finds_nothing` FAILS (client returned).

- [ ] **Step 3: Implement**

`app/modules/search/service.py` — change the signature and skip excluded entities at the top of the loop:

```python
    async def search(self, query: str, entities: set[str] | None = None) -> list[dict]:
        results: list[dict] = []
        seen: set[tuple[str, uuid.UUID]] = set()

        for field in SEARCH_FIELDS:
            if entities is not None and field.entity not in entities:
                continue
            model = ENTITY_MODELS[field.entity]
```

(rest of the method unchanged).

`app/modules/search/router.py` — replace the body of `search`:

```python
    service = SearchService(session)
    # Mechanics see vehicle data only: client results would expose personal data.
    entities = {"vehicle"} if acting_user.role == UserRole.MECHANIC else None
    return await service.search(q, entities=entities)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/modules/search -q` → all pass.

- [ ] **Step 5: Commit**

```bash
git add app/modules/search tests/modules/search/test_routes.py
git commit -m "feat: mechanics search vehicles only, never clients

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: История работ по машине

**Files:**
- Modify: `app/modules/visits/work_items_schemas.py`
- Modify: `app/modules/visits/work_items_service.py`
- Create: `app/modules/visits/vehicle_history_router.py`
- Modify: `app/main.py`
- Test: `tests/modules/visits/test_vehicle_history_routes.py` (new)

**Interfaces:**
- Produces: HTTP `GET /vehicles/{vehicle_id}/work-history` (ADMIN, MASTER, MECHANIC) → `VehicleWorkHistoryOut{items: list[VehicleWorkHistoryItemOut{visit_id, visit_at, mileage, name, status}], has_more}`; `WorkItemService.list_vehicle_history(vehicle_id) -> VehicleWorkHistoryOut`; константа `WORK_HISTORY_LIMIT = 30` в `work_items_service.py`.

- [ ] **Step 1: Write the failing tests**

Create `tests/modules/visits/test_vehicle_history_routes.py`:

```python
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.db import get_session
from app.core.enums import UserRole, VisitStatus, WorkCategory
from app.main import app
from app.modules.catalog.models import WorkCatalog
from app.modules.clients.schemas import ClientCreate
from app.modules.clients.service import ClientService
from app.modules.users.models import User
from app.modules.vehicles.schemas import VehicleCreate
from app.modules.vehicles.service import VehicleService
from app.modules.visits.schemas import VisitCreate
from app.modules.visits.service import VisitService
from app.modules.visits.work_items_schemas import WorkItemCreate
from app.modules.visits.work_items_service import WORK_HISTORY_LIMIT, WorkItemService

BASE = datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc)


@pytest.fixture
def api_app(session):
    async def override_get_session():
        yield session

    app.dependency_overrides[get_session] = override_get_session
    yield app
    app.dependency_overrides.clear()


async def _get(api_app, path, user):
    transport = ASGITransport(app=api_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(path, headers={"X-User-Id": str(user.id)})


async def _world(session):
    admin = User(role=UserRole.ADMIN, full_name="Админ", branch_id=uuid.uuid4())
    master = User(role=UserRole.MASTER, full_name="Мастер", branch_id=uuid.uuid4())
    mechanic = User(role=UserRole.MECHANIC, full_name="Механик", branch_id=uuid.uuid4())
    session.add_all([admin, master, mechanic])
    await session.flush()
    client = await ClientService(session).create_client(
        ClientCreate(full_name="Иванов", phone="79990000031"), admin
    )
    vehicle = await VehicleService(session).create_vehicle(
        VehicleCreate(vin="H" * 17, plate_number="Н123НН77", make="Toyota", model="Camry"), admin
    )
    return admin, master, mechanic, client, vehicle


async def _visit(session, admin, master, client, vehicle, hours, mileage, status=VisitStatus.RECEIVED):
    visit = await VisitService(session).create_visit(
        VisitCreate(
            client_id=client.id,
            vehicle_id=vehicle.id,
            assigned_master_id=master.id,
            mileage_at_intake=mileage,
            mileage_manually_confirmed=True,
        ),
        admin,
    )
    visit.created_at = BASE + timedelta(hours=hours)
    visit.status = status
    await session.flush()
    return visit


async def _work(session, admin, visit, *, name=None, catalog_item_id=None):
    return await WorkItemService(session).add_item(
        visit.id,
        WorkItemCreate(
            free_text_name=name,
            catalog_item_id=catalog_item_id,
            category=WorkCategory.MAINTENANCE,
            norm_hours=1.5,
            hourly_rate=2000,
        ),
        admin,
    )


async def test_history_lists_works_newest_visit_first_with_catalog_names(api_app, session):
    admin, master, mechanic, client, vehicle = await _world(session)
    catalog = WorkCatalog(
        name="Замена масла ДВС", category=WorkCategory.MAINTENANCE, default_norm_hours=1, created_by_user_id=admin.id
    )
    session.add(catalog)
    await session.flush()
    old = await _visit(session, admin, master, client, vehicle, hours=1, mileage=76_200)
    await _work(session, admin, old, name="Диагностика подвески")
    new = await _visit(session, admin, master, client, vehicle, hours=48, mileage=84_500)
    await _work(session, admin, new, catalog_item_id=catalog.id)
    await _work(session, admin, new, name="Замена фильтра салона")

    resp = await _get(api_app, f"/vehicles/{vehicle.id}/work-history", master)

    assert resp.status_code == 200
    items = resp.json()["items"]
    assert [i["visit_id"] for i in items] == [str(new.id), str(new.id), str(old.id)]
    assert {i["name"] for i in items[:2]} == {"Замена масла ДВС", "Замена фильтра салона"}
    assert items[2] == {
        "visit_id": str(old.id),
        "visit_at": items[2]["visit_at"],
        "mileage": 76_200,
        "name": "Диагностика подвески",
        "status": "not_ready",
    }
    assert items[2]["visit_at"].startswith("2026-09-01T10:00:00")
    assert resp.json()["has_more"] is False


async def test_history_excludes_cancelled_and_deleted_visits(api_app, session):
    admin, master, mechanic, client, vehicle = await _world(session)
    cancelled = await _visit(session, admin, master, client, vehicle, hours=1, mileage=1000, status=VisitStatus.CANCELLED)
    await _work(session, admin, cancelled, name="Отменённая работа")
    deleted = await _visit(session, admin, master, client, vehicle, hours=2, mileage=1000)
    await _work(session, admin, deleted, name="Удалённая работа")
    deleted.deleted_at = BASE
    kept = await _visit(session, admin, master, client, vehicle, hours=3, mileage=1000)
    await _work(session, admin, kept, name="Нормальная работа")
    await session.flush()

    resp = await _get(api_app, f"/vehicles/{vehicle.id}/work-history", master)

    assert [i["name"] for i in resp.json()["items"]] == ["Нормальная работа"]


async def test_history_has_no_price_or_client_fields_and_is_open_to_mechanic(api_app, session):
    admin, master, mechanic, client, vehicle = await _world(session)
    visit = await _visit(session, admin, master, client, vehicle, hours=1, mileage=1000)
    await _work(session, admin, visit, name="Работа")

    resp = await _get(api_app, f"/vehicles/{vehicle.id}/work-history", mechanic)

    assert resp.status_code == 200
    assert set(resp.json()) == {"items", "has_more"}
    assert set(resp.json()["items"][0]) == {"visit_id", "visit_at", "mileage", "name", "status"}


async def test_history_reports_has_more_over_limit(api_app, session):
    admin, master, mechanic, client, vehicle = await _world(session)
    visit = await _visit(session, admin, master, client, vehicle, hours=1, mileage=1000)
    for n in range(WORK_HISTORY_LIMIT + 1):
        await _work(session, admin, visit, name=f"Работа {n}")

    resp = await _get(api_app, f"/vehicles/{vehicle.id}/work-history", master)

    assert len(resp.json()["items"]) == WORK_HISTORY_LIMIT
    assert resp.json()["has_more"] is True


async def test_history_404_for_unknown_vehicle(api_app, session):
    admin, master, mechanic, client, vehicle = await _world(session)

    resp = await _get(api_app, f"/vehicles/{uuid.uuid4()}/work-history", master)

    assert resp.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/modules/visits/test_vehicle_history_routes.py -q`
Expected: collection ERROR `cannot import name 'WORK_HISTORY_LIMIT'`.

- [ ] **Step 3: Schemas**

Append to `app/modules/visits/work_items_schemas.py` (add `from datetime import datetime`):

```python
class VehicleWorkHistoryItemOut(BaseModel):
    """Deliberately no prices, hours or client data: mechanics read this."""

    visit_id: uuid.UUID
    visit_at: datetime
    mileage: int
    name: str
    status: WorkItemStatus


class VehicleWorkHistoryOut(BaseModel):
    items: list[VehicleWorkHistoryItemOut]
    has_more: bool
```

- [ ] **Step 4: Service method**

In `app/modules/visits/work_items_service.py` (check its existing imports first — `uuid`, `select` and `VisitWorkItem` may already be there) add imports `from sqlalchemy import func, select`, `from app.core.enums import VisitStatus`, `from app.modules.catalog.models import WorkCatalog`, `from app.modules.visits.models import Visit` (keep existing imports; merge with ones already present), and `VehicleWorkHistoryItemOut, VehicleWorkHistoryOut` from `work_items_schemas`. Add a module constant and a method on `WorkItemService`:

```python
WORK_HISTORY_LIMIT = 30
```

```python
    async def list_vehicle_history(self, vehicle_id: uuid.UUID) -> VehicleWorkHistoryOut:
        stmt = (
            select(
                Visit.id.label("visit_id"),
                Visit.created_at.label("visit_at"),
                Visit.mileage_at_intake.label("mileage"),
                func.coalesce(WorkCatalog.name, VisitWorkItem.free_text_name).label("name"),
                VisitWorkItem.status,
            )
            .join(Visit, Visit.id == VisitWorkItem.visit_id)
            .outerjoin(WorkCatalog, WorkCatalog.id == VisitWorkItem.catalog_item_id)
            .where(
                Visit.vehicle_id == vehicle_id,
                Visit.deleted_at.is_(None),
                Visit.status != VisitStatus.CANCELLED,
            )
            .order_by(Visit.created_at.desc(), Visit.id, VisitWorkItem.created_at, VisitWorkItem.id)
            .limit(WORK_HISTORY_LIMIT + 1)
        )
        rows = (await self.session.execute(stmt)).all()
        return VehicleWorkHistoryOut(
            items=[
                VehicleWorkHistoryItemOut(
                    visit_id=r.visit_id, visit_at=r.visit_at, mileage=r.mileage, name=r.name or "—", status=r.status
                )
                for r in rows[:WORK_HISTORY_LIMIT]
            ],
            has_more=len(rows) > WORK_HISTORY_LIMIT,
        )
```

- [ ] **Step 5: Router**

Create `app/modules/visits/vehicle_history_router.py`:

```python
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.enums import UserRole
from app.modules.users.auth import require_role
from app.modules.users.models import User
from app.modules.vehicles.service import VehicleService
from app.modules.visits.work_items_schemas import VehicleWorkHistoryOut
from app.modules.visits.work_items_service import WorkItemService

router = APIRouter(prefix="/vehicles/{vehicle_id}/work-history", tags=["vehicle-work-history"])


@router.get("", response_model=VehicleWorkHistoryOut)
async def get_vehicle_work_history(
    vehicle_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MASTER, UserRole.MECHANIC)),
):
    if await VehicleService(session).get(vehicle_id) is None:
        raise HTTPException(404, "Vehicle not found")
    return await WorkItemService(session).list_vehicle_history(vehicle_id)
```

In `app/main.py` add `from app.modules.visits.vehicle_history_router import router as vehicle_history_router` next to the other visits routers and `app.include_router(vehicle_history_router)` after `app.include_router(part_items_router)`.

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/modules/visits -q` → all pass. Then `.venv/bin/pytest -q` → all pass.

- [ ] **Step 7: Commit**

```bash
git add app/modules/visits app/main.py tests/modules/visits/test_vehicle_history_routes.py
git commit -m "feat: GET /vehicles/{id}/work-history without prices or client data

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Бот — API-клиент, даты, русские статусы, шапка карточки заезда

**Files:**
- Create: `bot/formatting.py`
- Create: `bot/visit_status.py`
- Modify: `bot/work_item_status.py`
- Modify: `bot/api_client.py`
- Modify: `bot/handlers/visits.py` (`send_visit_card` only)
- Modify: `bot/handlers/mechanic.py`
- Test: `tests/bot/test_formatting.py` (new), `tests/bot/test_api_client.py` (append), `tests/bot/test_visits_handler.py` (append)

**Interfaces:**
- Consumes: HTTP contracts from Tasks 1–5.
- Produces:
  - `bot.formatting.format_date(value: str) -> str` (`"02.10.2026"`), `format_day(value: str) -> str` (`"02.10"`); input — ISO-8601 строка из API.
  - `bot.visit_status.VISIT_STATUS_LABELS: dict[str, str]`, `visit_status_label(code: str) -> str`.
  - `bot.work_item_status.WORK_ITEM_STATUS_LABELS`, `work_item_status_label(code: str) -> str`.
  - `ApiClient.list_visits(active: bool = False, client_id: str | None = None, vehicle_id: str | None = None) -> dict` (`{"items": [...], "has_more": bool}`), `list_client_vehicles(client_id) -> list[dict]`, `get_vehicle_owner(vehicle_id) -> dict | None`, `list_masters() -> list[dict]`, `get_vehicle_work_history(vehicle_id) -> dict`.
  - `bot.handlers.visits.visit_header(visit: dict) -> list[str]` — строки шапки карточки.

- [ ] **Step 1: Write the failing tests**

Create `tests/bot/test_formatting.py`:

```python
from bot.formatting import format_date, format_day
from bot.visit_status import visit_status_label
from bot.work_item_status import work_item_status_label


def test_dates_are_shown_in_moscow_time():
    # 22:30 UTC on Oct 1 is 01:30 MSK on Oct 2
    assert format_date("2026-10-01T22:30:00+00:00") == "02.10.2026"
    assert format_day("2026-10-01T22:30:00+00:00") == "02.10"


def test_status_labels_are_russian_and_fall_back_to_code():
    assert visit_status_label("in_progress") == "Ремонт"
    assert visit_status_label("waiting_parts") == "Ждём запчасти"
    assert visit_status_label("unknown") == "unknown"
    assert work_item_status_label("ready") == "Готово"
    assert work_item_status_label("not_ready") == "Не начата"
```

Append to `tests/bot/test_api_client.py`:

```python
@respx.mock
async def test_list_visits_passes_filters_as_query():
    route = respx.route(method="GET", host="localhost", path="/visits").mock(
        return_value=httpx.Response(200, json={"items": [], "has_more": False})
    )
    result = await ApiClient(user_id="u1").list_visits(active=True, client_id="c1")
    assert result == {"items": [], "has_more": False}
    assert dict(route.calls.last.request.url.params) == {"active": "true", "client_id": "c1"}


@respx.mock
async def test_navigation_endpoints_hit_expected_paths():
    respx.get("http://localhost:8000/clients/c1/vehicles").mock(return_value=httpx.Response(200, json=[]))
    respx.get("http://localhost:8000/vehicles/v1/owner").mock(return_value=httpx.Response(200, json=None))
    respx.get("http://localhost:8000/users/masters").mock(return_value=httpx.Response(200, json=[]))
    respx.get("http://localhost:8000/vehicles/v1/work-history").mock(
        return_value=httpx.Response(200, json={"items": [], "has_more": False})
    )
    api = ApiClient(user_id="u1")
    assert await api.list_client_vehicles("c1") == []
    assert await api.get_vehicle_owner("v1") is None
    assert await api.list_masters() == []
    assert await api.get_vehicle_work_history("v1") == {"items": [], "has_more": False}
```

Append to `tests/bot/test_visits_handler.py`:

```python
async def test_send_visit_card_header_is_human_readable_and_statuses_russian():
    message = AsyncMock()
    visit = {
        "id": "11111111-1111-1111-1111-111111111111",
        "status": "in_progress",
        "total_amount": 12400.0,
        "plate_number": "А123ВС77",
        "make_model": "Toyota Camry",
        "client_name": "Иванов Пётр",
        "master_name": "Петров",
    }
    work_items = [
        {"id": "22222222-2222-2222-2222-222222222222", "name": "Замена масла", "status": "in_progress",
         "approved_by_client": True},
    ]

    await send_visit_card(message, visit, work_items)

    text = message.answer.await_args.args[0]
    assert text.splitlines()[0] == "А123ВС77 · Toyota Camry · Иванов Пётр"
    assert "Статус: Ремонт · Мастер: Петров" in text
    assert "1. Замена масла — В работе" in text
    markup = message.answer.await_args.kwargs["reply_markup"]
    texts = [b.text for row in markup.inline_keyboard for b in row]
    assert "Ждём запчасти" in texts
    assert "🔄 Замена масла → Готово" in texts
    assert "11111111-1111-1111-1111-111111111111" not in text


async def test_send_visit_card_without_summary_falls_back_to_generic_title():
    message = AsyncMock()

    await send_visit_card(message, {"id": "visit1", "status": "received", "total_amount": "0.00"}, [])

    assert message.answer.await_args.args[0].splitlines()[0] == "Заезд"
```

Append to `tests/bot/test_mechanic_handler.py`:

```python
async def test_show_my_work_items_shows_russian_status():
    message = AsyncMock()
    api = AsyncMock()
    api.list_my_work_items.return_value = [_item("waiting_parts")]

    await show_my_work_items(message, _fsm_context(), api=api)

    assert "Ждёт запчасти" in message.answer.await_args.args[0]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/bot -q`
Expected: collection ERROR `No module named 'bot.formatting'`.

- [ ] **Step 3: Formatting and status labels**

Create `bot/formatting.py`:

```python
"""Date display for staff in Moscow (UTC+3 all year; no DST since 2014).

A fixed offset avoids depending on the tzdata package in the slim image.
"""
from datetime import datetime, timedelta, timezone

MSK = timezone(timedelta(hours=3))


def _msk(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(MSK)


def format_date(value: str) -> str:
    return _msk(value).strftime("%d.%m.%Y")


def format_day(value: str) -> str:
    return _msk(value).strftime("%d.%m")
```

Create `bot/visit_status.py`:

```python
"""Russian labels for visit statuses (API codes stay in callback_data)."""

VISIT_STATUS_LABELS: dict[str, str] = {
    "received": "Принят",
    "diagnostics": "Диагностика",
    "approval": "Согласование",
    "in_progress": "Ремонт",
    "waiting_parts": "Ждём запчасти",
    "ready": "Готов",
    "issued": "Выдан",
    "cancelled": "Отменён",
}


def visit_status_label(code: str) -> str:
    return VISIT_STATUS_LABELS.get(code, code)
```

In `bot/work_item_status.py` add after `NEXT_WORK_ITEM_STATUSES`:

```python
WORK_ITEM_STATUS_LABELS: dict[str, str] = {
    "not_ready": "Не начата",
    "in_progress": "В работе",
    "waiting_parts": "Ждёт запчасти",
    "ready": "Готово",
}


def work_item_status_label(code: str) -> str:
    return WORK_ITEM_STATUS_LABELS.get(code, code)
```

and in `add_work_status_buttons` change the button text to `text=f"{label_prefix}→ {work_item_status_label(status)}",`.

- [ ] **Step 4: API client methods**

In `bot/api_client.py` add `from urllib.parse import quote, urlencode` (replace the existing `quote` import) and append to `ApiClient`:

```python
    async def list_visits(
        self, active: bool = False, client_id: str | None = None, vehicle_id: str | None = None
    ) -> dict:
        params: dict[str, str] = {}
        if active:
            params["active"] = "true"
        if client_id is not None:
            params["client_id"] = client_id
        if vehicle_id is not None:
            params["vehicle_id"] = vehicle_id
        path = f"/visits?{urlencode(params)}" if params else "/visits"
        return await self.get(path)

    async def list_client_vehicles(self, client_id: str) -> list[dict]:
        return await self.get(f"/clients/{client_id}/vehicles")

    async def get_vehicle_owner(self, vehicle_id: str) -> dict | None:
        return await self.get(f"/vehicles/{vehicle_id}/owner")

    async def list_masters(self) -> list[dict]:
        return await self.get("/users/masters")

    async def get_vehicle_work_history(self, vehicle_id: str) -> dict:
        return await self.get(f"/vehicles/{vehicle_id}/work-history")
```

- [ ] **Step 5: Visit card header and Russian statuses**

In `bot/handlers/visits.py` add imports `from bot.visit_status import visit_status_label` and extend the work_item_status import with `work_item_status_label`. Add above `send_visit_card`:

```python
def visit_header(visit: dict) -> list[str]:
    """Card title from the visit summary; tolerant of a partial dict."""
    title = " · ".join(
        part for part in (visit.get("plate_number"), visit.get("make_model"), visit.get("client_name")) if part
    )
    status_line = f"Статус: {visit_status_label(visit['status'])}"
    if visit.get("master_name"):
        status_line += f" · Мастер: {visit['master_name']}"
    return [title or "Заезд", status_line, f"Сумма: {visit.get('total_amount', '—')}"]
```

In `send_visit_card`:
- status buttons: `builder.button(text=visit_status_label(status), callback_data=f"visit_status:{visit['id']}:{status}")`
- replace the `lines = [...]` line with `lines = visit_header(visit)`
- work line: `lines.append(f"{index}. {name} — {work_item_status_label(item['status'])}")`

In `bot/handlers/mechanic.py` import `work_item_status_label` from `bot.work_item_status` and change the message text to:

```python
            f"{item['name']} — {work_item_status_label(item['status'])} (заезд {item['visit_id']})",
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/bot -q` → all pass (existing tests assert `callback_data`, not labels).

- [ ] **Step 7: Commit**

```bash
git add bot/formatting.py bot/visit_status.py bot/work_item_status.py bot/api_client.py bot/handlers/visits.py bot/handlers/mechanic.py tests/bot
git commit -m "feat(bot): readable visit card header, Russian statuses, MSK dates, API client for navigation

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Бот — меню по ролям, «Заезды в работе», открытие заезда

**Files:**
- Modify: `bot/keyboards.py`
- Create: `bot/handlers/navigation.py`
- Modify: `bot/handlers/menu.py`
- Modify: `bot/main.py` (`setup_routers`)
- Test: `tests/bot/test_keyboards.py` (rewrite), `tests/bot/test_navigation_handler.py` (new), `tests/bot/test_routing.py` (fixture tweak)

**Interfaces:**
- Consumes: `ApiClient.list_visits`, `ApiClient.get_visit`, `ApiClient.list_work_items`; `bot.handlers.visits.send_visit_card`; `bot.formatting.format_day`; `bot.visit_status.visit_status_label`.
- Produces: `keyboards.ACTIVE_VISITS = "Заезды в работе"`; `navigation.router`; `navigation.show_active_visits(message, state, api, user, **kwargs)`; `navigation.visit_list_markup(visits: list[dict], user_id: str, with_date: bool) -> InlineKeyboardMarkup`; `navigation.send_visit_list(message, result: dict, user_id: str, title: str, empty_text: str, with_date: bool)`; callback `visit_open:<b64>` handled by `navigation.open_visit_callback`; constant `navigation.LIST_TRUNCATED = "Показаны последние 30."`.

- [ ] **Step 1: Write the failing tests**

Replace `tests/bot/test_keyboards.py` with:

```python
from app.core.enums import UserRole
from bot.keyboards import main_menu


def _texts(role):
    return [button.text for row in main_menu(role).keyboard for button in row]


def test_mechanic_menu_has_my_work_items_and_search():
    assert _texts(UserRole.MECHANIC) == ["Мои работы", "Поиск"]


def test_master_menu():
    assert _texts(UserRole.MASTER) == ["Новый заезд", "Заезды в работе", "Поиск", "Регистрация клиента (бумага)"]


def test_admin_menu_has_everything_master_has_plus_add_staff():
    assert _texts(UserRole.ADMIN) == [
        "Новый заезд", "Заезды в работе", "Поиск", "Регистрация клиента (бумага)", "Добавить сотрудника",
    ]
```

Create `tests/bot/test_navigation_handler.py`:

```python
from unittest.mock import AsyncMock

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from bot.callback_ids import encode_id
from bot.handlers.navigation import open_visit_callback, show_active_visits

ME = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
OTHER = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
V1 = "11111111-1111-1111-1111-111111111111"
V2 = "22222222-2222-2222-2222-222222222222"


def _fsm_context() -> FSMContext:
    return FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=1, user_id=1))


def _visit(visit_id, master_id, status="in_progress", plate="А123ВС77", client="Иванов Пётр"):
    return {
        "id": visit_id, "status": status, "plate_number": plate, "client_name": client,
        "assigned_master_id": master_id, "created_at": "2026-10-02T07:00:00+00:00",
        "make_model": "Toyota Camry", "master_name": "Мастер", "total_amount": 0,
    }


def _buttons(message):
    markup = message.answer.await_args.kwargs["reply_markup"]
    return [(b.text, b.callback_data) for row in markup.inline_keyboard for b in row]


async def test_active_visits_marks_own_with_star_and_links_to_card():
    message = AsyncMock()
    api = AsyncMock()
    api.list_visits.return_value = {
        "items": [_visit(V1, ME), _visit(V2, OTHER, status="diagnostics", plate="В001ОР50", client="Петрова")],
        "has_more": False,
    }

    await show_active_visits(message, _fsm_context(), api=api, user={"id": ME, "role": "master"})

    api.list_visits.assert_awaited_once_with(active=True)
    assert message.answer.await_args.args[0] == "Заезды в работе (2)"
    assert _buttons(message) == [
        ("⭐ А123ВС77 · Иванов Пётр · Ремонт", f"visit_open:{encode_id(V1)}"),
        ("В001ОР50 · Петрова · Диагностика", f"visit_open:{encode_id(V2)}"),
    ]


async def test_active_visits_admin_sees_no_stars():
    message = AsyncMock()
    api = AsyncMock()
    api.list_visits.return_value = {"items": [_visit(V1, OTHER)], "has_more": False}

    await show_active_visits(message, _fsm_context(), api=api, user={"id": ME, "role": "admin"})

    assert not _buttons(message)[0][0].startswith("⭐")


async def test_active_visits_empty():
    message = AsyncMock()
    api = AsyncMock()
    api.list_visits.return_value = {"items": [], "has_more": False}

    await show_active_visits(message, _fsm_context(), api=api, user={"id": ME, "role": "master"})

    message.answer.assert_awaited_once_with("Незакрытых заездов нет.")


async def test_active_visits_warns_when_truncated():
    message = AsyncMock()
    api = AsyncMock()
    api.list_visits.return_value = {"items": [_visit(V1, ME)], "has_more": True}

    await show_active_visits(message, _fsm_context(), api=api, user={"id": ME, "role": "master"})

    assert message.answer.await_args.args[0] == "Заезды в работе (1)\nПоказаны последние 30."


async def test_active_visits_clears_wizard_state():
    message = AsyncMock()
    api = AsyncMock()
    api.list_visits.return_value = {"items": [], "has_more": False}
    state = _fsm_context()
    await state.update_data(visit_id="stale")

    await show_active_visits(message, state, api=api, user={"id": ME, "role": "master"})

    assert await state.get_data() == {}


async def test_open_visit_sends_card():
    callback = AsyncMock()
    callback.data = f"visit_open:{encode_id(V1)}"
    api = AsyncMock()
    api.get_visit.return_value = _visit(V1, ME)
    api.list_work_items.return_value = []

    await open_visit_callback(callback, api=api)

    api.get_visit.assert_awaited_once_with(V1)
    api.list_work_items.assert_awaited_once_with(V1)
    assert callback.message.answer.await_args.args[0].startswith("А123ВС77 · Toyota Camry · Иванов Пётр")
    callback.answer.assert_awaited_once()
```

In `tests/bot/test_routing.py`, inside the `env` fixture after `api = AsyncMock()` add:

```python
    api.list_visits.return_value = {"items": [], "has_more": False}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/bot/test_keyboards.py tests/bot/test_navigation_handler.py -q`
Expected: FAIL / collection ERROR `No module named 'bot.handlers.navigation'`.

- [ ] **Step 3: Menu by role**

Replace the constants and `main_menu` in `bot/keyboards.py`:

```python
NEW_VISIT = "Новый заезд"
ACTIVE_VISITS = "Заезды в работе"
SEARCH = "Поиск"
PAPER_CONSENT = "Регистрация клиента (бумага)"
ADD_STAFF = "Добавить сотрудника"
MY_WORK_ITEMS = "Мои работы"

MASTER_BUTTONS = [NEW_VISIT, ACTIVE_VISITS, SEARCH, PAPER_CONSENT]
ADMIN_BUTTONS = MASTER_BUTTONS + [ADD_STAFF]
MECHANIC_BUTTONS = [MY_WORK_ITEMS, SEARCH]
ALL_MENU_BUTTONS = ADMIN_BUTTONS + [MY_WORK_ITEMS]


def main_menu(role: UserRole) -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    if role == UserRole.MECHANIC:
        buttons = MECHANIC_BUTTONS
    elif role == UserRole.ADMIN:
        buttons = ADMIN_BUTTONS
    else:
        buttons = MASTER_BUTTONS
    for text in buttons:
        builder.button(text=text)
    builder.adjust(1)
    return builder.as_markup(resize_keyboard=True)
```

- [ ] **Step 4: Navigation router**

Create `bot/handlers/navigation.py`:

```python
"""Read-only navigation: visit lists, client/vehicle cards, histories.

Callbacks here are not bound to an FSM state, so buttons in old messages
keep working; a deleted entity surfaces as the API's 404 ("Не найдено").
"""
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.api_client import ApiClient
from bot.callback_ids import decode_id, encode_id
from bot.formatting import format_day
from bot.handlers.visits import send_visit_card
from bot.visit_status import visit_status_label

router = Router()

LIST_TRUNCATED = "Показаны последние 30."


def visit_list_markup(visits: list[dict], user_id: str, with_date: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for visit in visits:
        if with_date:
            parts = [format_day(visit["created_at"]), visit["plate_number"]]
        else:
            parts = [visit["plate_number"], visit["client_name"]]
        parts.append(visit_status_label(visit["status"]))
        star = "⭐ " if str(visit["assigned_master_id"]) == str(user_id) else ""
        builder.button(text=star + " · ".join(parts), callback_data=f"visit_open:{encode_id(visit['id'])}")
    builder.adjust(1)
    return builder.as_markup()


async def send_visit_list(
    message: Message, result: dict, user_id: str, title: str, empty_text: str, with_date: bool
) -> None:
    visits = result["items"]
    if not visits:
        await message.answer(empty_text)
        return
    text = f"{title} ({len(visits)})"
    if result["has_more"]:
        text += f"\n{LIST_TRUNCATED}"
    await message.answer(text, reply_markup=visit_list_markup(visits, user_id, with_date))


async def show_active_visits(message: Message, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    """Menu entry point (registered in bot/handlers/menu.py)."""
    await state.clear()
    result = await api.list_visits(active=True)
    await send_visit_list(message, result, user["id"], "Заезды в работе", "Незакрытых заездов нет.", with_date=False)


@router.callback_query(F.data.startswith("visit_open:"))
async def open_visit_callback(callback: CallbackQuery, api: ApiClient, **kwargs) -> None:
    visit_id = decode_id(callback.data.split(":", 1)[1])
    visit = await api.get_visit(visit_id)
    items = await api.list_work_items(visit_id)
    await send_visit_card(callback.message, visit, items)
    await callback.answer()
```

- [ ] **Step 5: Register menu entry and router**

`bot/handlers/menu.py`: import `navigation` alongside the other handlers and add `keyboards.ACTIVE_VISITS: navigation.show_active_visits,` to `_ENTRY_POINTS`.

`bot/main.py`: add `navigation` to the `from bot.handlers import (...)` list and in `setup_routers` insert `dp.include_router(navigation.router)` immediately before `dp.include_router(fallback.router)`.

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/bot -q` → all pass.

- [ ] **Step 7: Commit**

```bash
git add bot/keyboards.py bot/handlers/navigation.py bot/handlers/menu.py bot/main.py tests/bot
git commit -m "feat(bot): 'Заезды в работе' list, admin gets the master's menu, mechanic gets search

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Бот — поиск с карточками, карточки клиента и машины, истории

**Files:**
- Modify: `bot/handlers/search.py`
- Modify: `bot/handlers/navigation.py`
- Test: `tests/bot/test_search_handler.py` (rewrite), `tests/bot/test_navigation_handler.py` (append)

**Interfaces:**
- Consumes: Task 6 API methods; Task 7 `send_visit_list`, `LIST_TRUNCATED`.
- Produces: callbacks `client_open:<b64>`, `vehicle_open:<b64>`, `visits_by_client:<b64>`, `visits_by_vehicle:<b64>`, `work_history:<b64>`; the vehicle card emits `new_visit_for:<b64>` (handled in Task 9); `navigation.send_client_card(message, api, client_id)`, `navigation.send_vehicle_card(message, api, user, vehicle_id)`; `search.SEARCH_RESULTS_LIMIT = 10`.

- [ ] **Step 1: Write the failing tests**

Replace `tests/bot/test_search_handler.py` with:

```python
from unittest.mock import AsyncMock

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from bot.callback_ids import encode_id
from bot.handlers.search import SEARCH_RESULTS_LIMIT, receive_search_query, start_search

C1 = "11111111-1111-1111-1111-111111111111"
V1 = "22222222-2222-2222-2222-222222222222"
MASTER = {"id": "m1", "role": "master"}
MECHANIC = {"id": "k1", "role": "mechanic"}


def _buttons(message):
    markup = message.answer.await_args.kwargs["reply_markup"]
    return [(b.text, b.callback_data) for row in markup.inline_keyboard for b in row]


async def test_search_results_are_buttons_to_cards():
    message = AsyncMock()
    message.text = "Иванов"
    api = AsyncMock()
    api.search.return_value = [
        {"entity": "client", "id": C1, "matched_field": "full_name"},
        {"entity": "vehicle", "id": V1, "matched_field": "plate_number"},
    ]
    api.get_client.return_value = {"id": C1, "full_name": "Иван Иванов", "phone_display": "+7 999 123-45-67"}
    api.get_vehicle.return_value = {"id": V1, "make": "Toyota", "model": "Camry", "plate_number": "А123ВС77"}

    await receive_search_query(message, api=api, user=MASTER)

    assert message.answer.await_args.args[0] == "Найдено: 2"
    assert _buttons(message) == [
        ("👤 Иван Иванов — +7 999 123-45-67", f"client_open:{encode_id(C1)}"),
        ("🚗 Toyota Camry (А123ВС77)", f"vehicle_open:{encode_id(V1)}"),
    ]


async def test_search_shows_first_results_and_asks_to_refine():
    message = AsyncMock()
    message.text = "Toyota"
    ids = [f"{n:08d}-0000-0000-0000-000000000000" for n in range(SEARCH_RESULTS_LIMIT + 3)]
    api = AsyncMock()
    api.search.return_value = [{"entity": "vehicle", "id": i, "matched_field": "make"} for i in ids]
    api.get_vehicle.return_value = {"make": "Toyota", "model": "Camry", "plate_number": "А1"}

    await receive_search_query(message, api=api, user=MASTER)

    assert api.get_vehicle.await_count == SEARCH_RESULTS_LIMIT
    assert message.answer.await_args.args[0] == "Найдено: 13\nПоказаны первые 10 — уточните запрос."


async def test_search_handles_no_matches():
    message = AsyncMock()
    message.text = "неизвестно"
    api = AsyncMock()
    api.search.return_value = []

    await receive_search_query(message, api=api, user=MASTER)

    message.answer.assert_awaited_once_with("Ничего не найдено.")


async def test_mechanic_no_matches_hint_mentions_vin_and_plate():
    message = AsyncMock()
    message.text = "Сидоров"
    api = AsyncMock()
    api.search.return_value = []

    await receive_search_query(message, api=api, user=MECHANIC)

    message.answer.assert_awaited_once_with("Ничего не найдено. Механик может искать машину по VIN или госномеру.")


async def test_start_search_prompt_depends_on_role():
    state = FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=1, user_id=1))
    master_msg, mechanic_msg = AsyncMock(), AsyncMock()

    await start_search(master_msg, state, user=MASTER)
    await start_search(mechanic_msg, state, user=MECHANIC)

    master_msg.answer.assert_awaited_once_with("Введите телефон, VIN, гос.номер или имя клиента:")
    mechanic_msg.answer.assert_awaited_once_with("Введите VIN или гос.номер:")
```

Append to `tests/bot/test_navigation_handler.py`:

```python
from bot.handlers.navigation import (
    client_open_callback,
    vehicle_open_callback,
    visits_by_client_callback,
    visits_by_vehicle_callback,
    work_history_callback,
)

C1 = "33333333-3333-3333-3333-333333333333"
VH = "44444444-4444-4444-4444-444444444444"
CLIENT = {"id": C1, "full_name": "Иванов Пётр", "phone_display": "+7 999 123-45-67", "client_type": "individual"}
VEHICLE = {"id": VH, "vin": "JTNB0000000000001", "plate_number": "А123ВС77", "make": "Toyota",
           "model": "Camry", "mileage_current": 84500}


def _callback(data):
    callback = AsyncMock()
    callback.data = data
    return callback


def _cb_buttons(callback):
    markup = callback.message.answer.await_args.kwargs["reply_markup"]
    return [(b.text, b.callback_data) for row in markup.inline_keyboard for b in row]


async def test_client_card_lists_vehicles_and_visits_button():
    callback = _callback(f"client_open:{encode_id(C1)}")
    api = AsyncMock()
    api.get_client.return_value = CLIENT
    api.list_client_vehicles.return_value = [VEHICLE]

    await client_open_callback(callback, api=api)

    assert callback.message.answer.await_args.args[0] == "👤 Иванов Пётр\n+7 999 123-45-67"
    assert _cb_buttons(callback) == [
        ("🚗 Toyota Camry (А123ВС77)", f"vehicle_open:{encode_id(VH)}"),
        ("📋 Заезды клиента", f"visits_by_client:{encode_id(C1)}"),
    ]


async def test_vehicle_card_for_master_has_owner_visits_new_visit_and_history():
    callback = _callback(f"vehicle_open:{encode_id(VH)}")
    api = AsyncMock()
    api.get_vehicle.return_value = VEHICLE
    api.get_vehicle_owner.return_value = CLIENT

    await vehicle_open_callback(callback, api=api, user={"id": ME, "role": "master"})

    assert callback.message.answer.await_args.args[0] == (
        "🚗 Toyota Camry · А123ВС77\nVIN: JTNB0000000000001 · Пробег: 84 500 км"
    )
    assert _cb_buttons(callback) == [
        ("👤 Владелец: Иванов Пётр", f"client_open:{encode_id(C1)}"),
        ("📋 Заезды по машине", f"visits_by_vehicle:{encode_id(VH)}"),
        ("➕ Новый заезд", f"new_visit_for:{encode_id(VH)}"),
        ("🔧 История работ", f"work_history:{encode_id(VH)}"),
    ]


async def test_vehicle_card_without_owner_hides_owner_and_new_visit():
    callback = _callback(f"vehicle_open:{encode_id(VH)}")
    api = AsyncMock()
    api.get_vehicle.return_value = VEHICLE
    api.get_vehicle_owner.return_value = None

    await vehicle_open_callback(callback, api=api, user={"id": ME, "role": "admin"})

    assert [t for t, _ in _cb_buttons(callback)] == ["📋 Заезды по машине", "🔧 История работ"]


async def test_vehicle_card_for_mechanic_has_only_history_and_never_asks_owner():
    callback = _callback(f"vehicle_open:{encode_id(VH)}")
    api = AsyncMock()
    api.get_vehicle.return_value = VEHICLE

    await vehicle_open_callback(callback, api=api, user={"id": ME, "role": "mechanic"})

    api.get_vehicle_owner.assert_not_awaited()
    assert [t for t, _ in _cb_buttons(callback)] == ["🔧 История работ"]


async def test_visits_by_client_and_vehicle_show_dated_history():
    api = AsyncMock()
    api.list_visits.return_value = {"items": [_visit(V1, OTHER, status="issued")], "has_more": True}
    by_client = _callback(f"visits_by_client:{encode_id(C1)}")
    by_vehicle = _callback(f"visits_by_vehicle:{encode_id(VH)}")

    await visits_by_client_callback(by_client, api=api, user={"id": ME, "role": "master"})
    await visits_by_vehicle_callback(by_vehicle, api=api, user={"id": ME, "role": "master"})

    assert api.list_visits.await_args_list[0].kwargs == {"client_id": C1}
    assert api.list_visits.await_args_list[1].kwargs == {"vehicle_id": VH}
    assert by_client.message.answer.await_args.args[0] == "Заезды (1)\nПоказаны последние 30."
    assert _cb_buttons(by_client)[0][0] == "02.10 · А123ВС77 · Выдан"


async def test_visits_history_empty():
    api = AsyncMock()
    api.list_visits.return_value = {"items": [], "has_more": False}
    callback = _callback(f"visits_by_client:{encode_id(C1)}")

    await visits_by_client_callback(callback, api=api, user={"id": ME, "role": "master"})

    callback.message.answer.assert_awaited_once_with("Заездов ещё не было.")


async def test_work_history_groups_by_visit():
    api = AsyncMock()
    api.get_vehicle.return_value = VEHICLE
    api.get_vehicle_work_history.return_value = {
        "items": [
            {"visit_id": V1, "visit_at": "2026-09-12T07:00:00+00:00", "mileage": 84500,
             "name": "Замена масла ДВС", "status": "ready"},
            {"visit_id": V1, "visit_at": "2026-09-12T07:00:00+00:00", "mileage": 84500,
             "name": "Замена фильтра салона", "status": "in_progress"},
            {"visit_id": V2, "visit_at": "2026-04-03T07:00:00+00:00", "mileage": 76200,
             "name": "Диагностика подвески", "status": "ready"},
        ],
        "has_more": False,
    }
    callback = _callback(f"work_history:{encode_id(VH)}")

    await work_history_callback(callback, api=api)

    callback.message.answer.assert_awaited_once_with(
        "🔧 История работ · А123ВС77\n"
        "12.09.2026 · 84 500 км\n"
        "  • Замена масла ДВС — Готово\n"
        "  • Замена фильтра салона — В работе\n"
        "03.04.2026 · 76 200 км\n"
        "  • Диагностика подвески — Готово"
    )


async def test_work_history_empty_and_truncated():
    api = AsyncMock()
    api.get_vehicle.return_value = VEHICLE
    api.get_vehicle_work_history.return_value = {"items": [], "has_more": False}
    empty = _callback(f"work_history:{encode_id(VH)}")

    await work_history_callback(empty, api=api)

    empty.message.answer.assert_awaited_once_with("Работ по машине ещё не было.")

    api.get_vehicle_work_history.return_value = {
        "items": [{"visit_id": V1, "visit_at": "2026-09-12T07:00:00+00:00", "mileage": 1,
                   "name": "Работа", "status": "ready"}],
        "has_more": True,
    }
    truncated = _callback(f"work_history:{encode_id(VH)}")

    await work_history_callback(truncated, api=api)

    assert truncated.message.answer.await_args.args[0].endswith("Показаны последние 30 работ.")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/bot/test_search_handler.py tests/bot/test_navigation_handler.py -q`
Expected: ERROR — `cannot import name 'SEARCH_RESULTS_LIMIT'` / `cannot import name 'client_open_callback'`.

- [ ] **Step 3: Search with buttons**

Replace `bot/handlers/search.py` with:

```python
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.api_client import ApiClient
from bot.callback_ids import encode_id

router = Router()

SEARCH_RESULTS_LIMIT = 10


def _is_mechanic(user: dict) -> bool:
    return user["role"] == "mechanic"


async def start_search(message: Message, state: FSMContext, user: dict, **kwargs) -> None:
    """Menu entry point (registered in bot/handlers/menu.py)."""
    await state.clear()
    if _is_mechanic(user):
        await message.answer("Введите VIN или гос.номер:")
    else:
        await message.answer("Введите телефон, VIN, гос.номер или имя клиента:")


@router.message(F.text)
async def receive_search_query(message: Message, api: ApiClient, user: dict, **kwargs) -> None:
    # For mechanics the API returns vehicles only (no client personal data).
    results = await api.search(message.text)
    if not results:
        if _is_mechanic(user):
            await message.answer("Ничего не найдено. Механик может искать машину по VIN или госномеру.")
        else:
            await message.answer("Ничего не найдено.")
        return
    builder = InlineKeyboardBuilder()
    for r in results[:SEARCH_RESULTS_LIMIT]:
        if r["entity"] == "client":
            client = await api.get_client(r["id"])
            builder.button(
                text=f"👤 {client['full_name']} — {client['phone_display']}",
                callback_data=f"client_open:{encode_id(r['id'])}",
            )
        elif r["entity"] == "vehicle":
            vehicle = await api.get_vehicle(r["id"])
            builder.button(
                text=f"🚗 {vehicle['make']} {vehicle['model']} ({vehicle['plate_number']})",
                callback_data=f"vehicle_open:{encode_id(r['id'])}",
            )
    builder.adjust(1)
    text = f"Найдено: {len(results)}"
    if len(results) > SEARCH_RESULTS_LIMIT:
        text += f"\nПоказаны первые {SEARCH_RESULTS_LIMIT} — уточните запрос."
    await message.answer(text, reply_markup=builder.as_markup())
```

- [ ] **Step 4: Cards and histories**

Append to `bot/handlers/navigation.py` (add `from bot.formatting import format_date, format_day` — replace the existing `format_day` import — and `from bot.work_item_status import work_item_status_label`):

```python
STAFF_ROLES = {"admin", "master"}


def _km(value: int) -> str:
    return f"{value:,}".replace(",", " ")


async def send_client_card(message: Message, api: ApiClient, client_id: str) -> None:
    client = await api.get_client(client_id)
    vehicles = await api.list_client_vehicles(client_id)
    builder = InlineKeyboardBuilder()
    for v in vehicles:
        builder.button(
            text=f"🚗 {v['make']} {v['model']} ({v['plate_number']})",
            callback_data=f"vehicle_open:{encode_id(v['id'])}",
        )
    builder.button(text="📋 Заезды клиента", callback_data=f"visits_by_client:{encode_id(client_id)}")
    builder.adjust(1)
    await message.answer(f"👤 {client['full_name']}\n{client['phone_display']}", reply_markup=builder.as_markup())


async def send_vehicle_card(message: Message, api: ApiClient, user: dict, vehicle_id: str) -> None:
    vehicle = await api.get_vehicle(vehicle_id)
    vid = encode_id(vehicle_id)
    builder = InlineKeyboardBuilder()
    if user["role"] in STAFF_ROLES:
        # Owner is personal data: mechanics never request it (the API would 403).
        owner = await api.get_vehicle_owner(vehicle_id)
        if owner is not None:
            builder.button(text=f"👤 Владелец: {owner['full_name']}", callback_data=f"client_open:{encode_id(owner['id'])}")
        builder.button(text="📋 Заезды по машине", callback_data=f"visits_by_vehicle:{vid}")
        if owner is not None:
            builder.button(text="➕ Новый заезд", callback_data=f"new_visit_for:{vid}")
    builder.button(text="🔧 История работ", callback_data=f"work_history:{vid}")
    builder.adjust(1)
    text = (
        f"🚗 {vehicle['make']} {vehicle['model']} · {vehicle['plate_number']}\n"
        f"VIN: {vehicle['vin']} · Пробег: {_km(vehicle['mileage_current'])} км"
    )
    await message.answer(text, reply_markup=builder.as_markup())


def _id_from(callback: CallbackQuery) -> str:
    return decode_id(callback.data.split(":", 1)[1])


@router.callback_query(F.data.startswith("client_open:"))
async def client_open_callback(callback: CallbackQuery, api: ApiClient, **kwargs) -> None:
    await send_client_card(callback.message, api, _id_from(callback))
    await callback.answer()


@router.callback_query(F.data.startswith("vehicle_open:"))
async def vehicle_open_callback(callback: CallbackQuery, api: ApiClient, user: dict, **kwargs) -> None:
    await send_vehicle_card(callback.message, api, user, _id_from(callback))
    await callback.answer()


async def _send_history(callback: CallbackQuery, api: ApiClient, user: dict, **filters) -> None:
    result = await api.list_visits(**filters)
    await send_visit_list(callback.message, result, user["id"], "Заезды", "Заездов ещё не было.", with_date=True)
    await callback.answer()


@router.callback_query(F.data.startswith("visits_by_client:"))
async def visits_by_client_callback(callback: CallbackQuery, api: ApiClient, user: dict, **kwargs) -> None:
    await _send_history(callback, api, user, client_id=_id_from(callback))


@router.callback_query(F.data.startswith("visits_by_vehicle:"))
async def visits_by_vehicle_callback(callback: CallbackQuery, api: ApiClient, user: dict, **kwargs) -> None:
    await _send_history(callback, api, user, vehicle_id=_id_from(callback))


@router.callback_query(F.data.startswith("work_history:"))
async def work_history_callback(callback: CallbackQuery, api: ApiClient, **kwargs) -> None:
    vehicle_id = _id_from(callback)
    vehicle = await api.get_vehicle(vehicle_id)
    history = await api.get_vehicle_work_history(vehicle_id)
    if not history["items"]:
        await callback.message.answer("Работ по машине ещё не было.")
        await callback.answer()
        return
    lines = [f"🔧 История работ · {vehicle['plate_number']}"]
    current_visit = None
    for item in history["items"]:
        if item["visit_id"] != current_visit:
            current_visit = item["visit_id"]
            lines.append(f"{format_date(item['visit_at'])} · {_km(item['mileage'])} км")
        lines.append(f"  • {item['name']} — {work_item_status_label(item['status'])}")
    if history["has_more"]:
        lines.append("Показаны последние 30 работ.")
    await callback.message.answer("\n".join(lines))
    await callback.answer()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/bot -q` → all pass.

- [ ] **Step 6: Commit**

```bash
git add bot/handlers/search.py bot/handlers/navigation.py tests/bot
git commit -m "feat(bot): clickable search, client and vehicle cards, visit and work histories

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Бот — выбор мастера у ADMIN и «Новый заезд» из карточки машины

**Files:**
- Modify: `bot/states.py`
- Modify: `bot/handlers/visits.py`
- Test: `tests/bot/test_visits_handler.py` (append), `tests/bot/test_routing.py` (parametrize list)

**Interfaces:**
- Consumes: `ApiClient.list_masters`, `ApiClient.get_vehicle_owner`, `ApiClient.create_visit`; callback `new_visit_for:<b64>` emitted by Task 8's vehicle card.
- Produces: `NewVisitStates.choosing_master`; callbacks `master_pick:<b64>` (state-bound) and `new_visit_for:<b64>`; handlers `choose_master_callback`, `new_visit_for_vehicle_callback`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/bot/test_visits_handler.py` (add `choose_master_callback, new_visit_for_vehicle_callback` to the `from bot.handlers.visits import (...)` list at the top of the file):

```python
MASTER_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
VEHICLE_ID = "44444444-4444-4444-4444-444444444444"
ADMIN = {"id": "admin1", "role": "admin"}


async def test_admin_is_asked_to_choose_master_after_mileage():
    message = AsyncMock()
    message.text = "45000"
    state = _fsm_context()
    await state.set_state(NewVisitStates.waiting_for_mileage)
    await state.update_data(client_id="c1", vehicle_id="v1")
    api = AsyncMock()
    api.list_masters.return_value = [{"id": MASTER_A, "full_name": "Анна"}]

    await receive_mileage(message, state, api=api, user=ADMIN)

    api.create_visit.assert_not_awaited()
    assert await state.get_state() == NewVisitStates.choosing_master.state
    markup = message.answer.await_args.kwargs["reply_markup"]
    assert [(b.text, b.callback_data) for row in markup.inline_keyboard for b in row] == [
        ("Анна", f"master_pick:{_encode_id(MASTER_A)}")
    ]


async def test_admin_master_pick_creates_visit_with_that_master():
    callback = AsyncMock()
    callback.data = f"master_pick:{_encode_id(MASTER_A)}"
    state = _fsm_context()
    await state.set_state(NewVisitStates.choosing_master)
    await state.update_data(client_id="c1", vehicle_id="v1", mileage=45000, mileage_confirmed=False)
    api = AsyncMock()
    api.create_visit.return_value = {"id": "visit1", "status": "received"}

    await choose_master_callback(callback, state, api=api, user=ADMIN)

    api.create_visit.assert_awaited_once_with(
        client_id="c1", vehicle_id="v1", assigned_master_id=MASTER_A, mileage_at_intake=45000,
        mileage_manually_confirmed=False,
    )
    assert await state.get_state() is None


async def test_admin_without_masters_is_told_to_add_one():
    message = AsyncMock()
    message.text = "45000"
    state = _fsm_context()
    await state.set_state(NewVisitStates.waiting_for_mileage)
    await state.update_data(client_id="c1", vehicle_id="v1")
    api = AsyncMock()
    api.list_masters.return_value = []

    await receive_mileage(message, state, api=api, user=ADMIN)

    message.answer.assert_awaited_once_with("Сначала добавьте мастера через «Добавить сотрудника».")
    assert await state.get_state() is None
    api.create_visit.assert_not_awaited()


async def test_admin_mileage_rollback_keeps_chosen_master():
    from bot.api_client import ApiMileageRollback

    callback = AsyncMock()
    callback.data = f"master_pick:{_encode_id(MASTER_A)}"
    state = _fsm_context()
    await state.set_state(NewVisitStates.choosing_master)
    await state.update_data(client_id="c1", vehicle_id="v1", mileage=100, mileage_confirmed=False)
    api = AsyncMock()
    api.create_visit.side_effect = [ApiMileageRollback("Пробег меньше"), {"id": "visit1", "status": "received"}]

    await choose_master_callback(callback, state, api=api, user=ADMIN)
    assert await state.get_state() == NewVisitStates.confirming_mileage.state

    confirm = AsyncMock()
    await confirm_mileage_callback(confirm, state, api=api, user=ADMIN)

    api.list_masters.assert_not_awaited()
    assert api.create_visit.await_args_list[1].kwargs["assigned_master_id"] == MASTER_A
    assert api.create_visit.await_args_list[1].kwargs["mileage_manually_confirmed"] is True


async def test_new_visit_from_vehicle_card_starts_at_mileage():
    callback = AsyncMock()
    callback.data = f"new_visit_for:{_encode_id(VEHICLE_ID)}"
    state = _fsm_context()
    await state.update_data(stale="x")
    api = AsyncMock()
    api.get_vehicle_owner.return_value = {"id": "c9", "full_name": "Иванов"}

    await new_visit_for_vehicle_callback(callback, state, api=api, user={"id": "m1", "role": "master"})

    assert await state.get_state() == NewVisitStates.waiting_for_mileage.state
    assert await state.get_data() == {"client_id": "c9", "vehicle_id": VEHICLE_ID}
    callback.message.answer.assert_awaited_once_with("Новый заезд: Иванов. Введите пробег на приёмке (/cancel — отмена):")


async def test_new_visit_from_vehicle_without_owner_is_refused():
    callback = AsyncMock()
    callback.data = f"new_visit_for:{_encode_id(VEHICLE_ID)}"
    state = _fsm_context()
    api = AsyncMock()
    api.get_vehicle_owner.return_value = None

    await new_visit_for_vehicle_callback(callback, state, api=api, user={"id": "m1", "role": "master"})

    assert await state.get_state() is None
    callback.message.answer.assert_awaited_once_with("У машины нет владельца — заведите заезд через «Новый заезд».")


async def test_new_visit_from_vehicle_refused_for_mechanic():
    callback = AsyncMock()
    callback.data = f"new_visit_for:{_encode_id(VEHICLE_ID)}"
    state = _fsm_context()
    api = AsyncMock()

    await new_visit_for_vehicle_callback(callback, state, api=api, user={"id": "k1", "role": "mechanic"})

    api.get_vehicle_owner.assert_not_awaited()
    callback.answer.assert_awaited_once_with("Недостаточно прав")
```

In `tests/bot/test_routing.py`, add `"master_pick:AAAAAAAAAAAAAAAAAAAAAA"` to the `@pytest.mark.parametrize("data", [...])` list of `test_state_bound_wizard_callbacks_do_not_fire_without_state`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/bot/test_visits_handler.py tests/bot/test_routing.py -q`
Expected: collection ERROR `cannot import name 'choose_master_callback'`.

- [ ] **Step 3: State**

In `bot/states.py` add to `NewVisitStates`, after `confirming_mileage`:

```python
    choosing_master = State()
```

- [ ] **Step 4: Wizard changes**

In `bot/handlers/visits.py` replace `_create_visit`, `receive_mileage` and `confirm_mileage_callback` with the code below, and add the two new handlers after them:

```python
async def _create_visit(message: Message, state: FSMContext, api: ApiClient, user: dict) -> None:
    """Create the visit from FSM data: client_id, vehicle_id, mileage, mileage_confirmed,
    and assigned_master_id (ADMIN's pick; a MASTER is always the master)."""
    data = await state.get_data()
    try:
        visit = await api.create_visit(
            client_id=data["client_id"],
            vehicle_id=data["vehicle_id"],
            assigned_master_id=data.get("assigned_master_id", user["id"]),
            mileage_at_intake=data["mileage"],
            mileage_manually_confirmed=data["mileage_confirmed"],
        )
    except ApiMileageRollback as e:
        # Keep everything (incl. the chosen master) until the mileage is confirmed
        # or a different mileage is typed — also accepted in this state.
        await state.set_state(NewVisitStates.confirming_mileage)
        builder = InlineKeyboardBuilder()
        builder.button(text="Подтвердить пробег", callback_data=MILEAGE_CONFIRM)
        await message.answer(f"{e.message}\nИли введите другой пробег.", reply_markup=builder.as_markup())
        return
    await state.clear()
    await send_visit_card(message, visit, [])


async def _continue_after_mileage(message: Message, state: FSMContext, api: ApiClient, user: dict) -> None:
    data = await state.get_data()
    if user["role"] == "admin" and "assigned_master_id" not in data:
        masters = await api.list_masters()
        if not masters:
            await state.clear()
            await message.answer("Сначала добавьте мастера через «Добавить сотрудника».")
            return
        builder = InlineKeyboardBuilder()
        for master in masters:
            builder.button(text=master["full_name"], callback_data=f"master_pick:{encode_id(master['id'])}")
        builder.adjust(1)
        await state.set_state(NewVisitStates.choosing_master)
        await message.answer("Выберите мастера:", reply_markup=builder.as_markup())
        return
    await _create_visit(message, state, api, user)


@router.message(NewVisitStates.waiting_for_mileage)
@router.message(NewVisitStates.confirming_mileage)
async def receive_mileage(message: Message, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    try:
        mileage = int(message.text)
    except (ValueError, TypeError):
        await message.answer("Введите число (пробег в км).")
        return
    await state.update_data(mileage=mileage, mileage_confirmed=False)
    await _continue_after_mileage(message, state, api, user)


@router.callback_query(NewVisitStates.confirming_mileage, F.data == MILEAGE_CONFIRM)
async def confirm_mileage_callback(callback: CallbackQuery, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    await state.update_data(mileage_confirmed=True)
    await _continue_after_mileage(callback.message, state, api, user)
    await callback.answer()


@router.callback_query(NewVisitStates.choosing_master, F.data.startswith("master_pick:"))
async def choose_master_callback(callback: CallbackQuery, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    await state.update_data(assigned_master_id=decode_id(callback.data.split(":", 1)[1]))
    await _create_visit(callback.message, state, api, user)
    await callback.answer()


@router.callback_query(F.data.startswith("new_visit_for:"))
async def new_visit_for_vehicle_callback(
    callback: CallbackQuery, state: FSMContext, api: ApiClient, user: dict, **kwargs
) -> None:
    if user["role"] not in ("admin", "master"):
        await callback.answer("Недостаточно прав")
        return
    vehicle_id = decode_id(callback.data.split(":", 1)[1])
    owner = await api.get_vehicle_owner(vehicle_id)
    if owner is None:
        await callback.message.answer("У машины нет владельца — заведите заезд через «Новый заезд».")
        await callback.answer()
        return
    await state.clear()
    await state.update_data(client_id=owner["id"], vehicle_id=vehicle_id)
    await state.set_state(NewVisitStates.waiting_for_mileage)
    await callback.message.answer(f"Новый заезд: {owner['full_name']}. Введите пробег на приёмке {CANCEL_HINT}:")
    await callback.answer()
```

Note: the existing test `test_receive_mileage_uses_acting_user_as_master` keeps passing — a MASTER skips the master step and `assigned_master_id` falls back to `user["id"]`. Update its `user` to `{"id": "m1", "role": "master"}` (role is now read). Do the same for any other existing test in `tests/bot/test_visits_handler.py` that calls `receive_mileage` or `confirm_mileage_callback` with a `user` dict lacking `"role"`: add `"role": "master"`. Also, any existing test calling `confirm_mileage_callback` must pre-seed `mileage` in state data (it already does — the old handler read `data["mileage"]` too).

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/bot -q` → all pass.

- [ ] **Step 6: Commit**

```bash
git add bot/states.py bot/handlers/visits.py tests/bot
git commit -m "feat(bot): admins pick the visit's master; start a visit from the vehicle card

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: Бот — команды в меню Telegram

**Files:**
- Modify: `bot/main.py`
- Test: `tests/bot/test_main.py` (append)

**Interfaces:**
- Produces: `bot.main.BOT_COMMANDS: list[BotCommand]`; `async def set_commands(bot: Bot) -> None` (never raises on Telegram errors).

- [ ] **Step 1: Write the failing tests**

Append to `tests/bot/test_main.py`:

```python
from aiogram.exceptions import TelegramNetworkError
from aiogram.methods import SetMyCommands

from bot.main import BOT_COMMANDS, set_commands


async def test_set_commands_registers_menu_commands():
    bot = AsyncMock()

    await set_commands(bot)

    bot.set_my_commands.assert_awaited_once_with(BOT_COMMANDS)
    assert [c.command for c in BOT_COMMANDS] == ["start", "cancel", "new_client", "new_vehicle"]


async def test_set_commands_failure_does_not_stop_startup(caplog):
    bot = AsyncMock()
    bot.set_my_commands.side_effect = TelegramNetworkError(method=SetMyCommands(commands=[]), message="timeout")

    await set_commands(bot)

    assert "Could not register bot commands" in caplog.text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/bot/test_main.py -q`
Expected: ImportError `cannot import name 'BOT_COMMANDS'`.

- [ ] **Step 3: Implement**

In `bot/main.py`: change `from aiogram.exceptions import TelegramUnauthorizedError` to `from aiogram.exceptions import TelegramAPIError, TelegramUnauthorizedError` (`TelegramNetworkError` subclasses `TelegramAPIError`), add `from aiogram.types import BotCommand`, and add after `create_bot`:

```python
BOT_COMMANDS = [
    BotCommand(command="start", description="Главное меню"),
    BotCommand(command="cancel", description="Отменить текущее действие"),
    BotCommand(command="new_client", description="Новый клиент"),
    BotCommand(command="new_vehicle", description="Новая машина"),
]


async def set_commands(bot: Bot) -> None:
    """Show commands in Telegram's menu button; a failure must not block polling."""
    try:
        await bot.set_my_commands(BOT_COMMANDS)
    except TelegramAPIError:
        logger.warning("Could not register bot commands", exc_info=True)
```

In `main()` add `await set_commands(bot)` right after `bot = await create_bot(settings.bot_token)`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/bot -q` → all pass.

- [ ] **Step 5: Commit**

```bash
git add bot/main.py tests/bot/test_main.py
git commit -m "feat(bot): register /start, /cancel, /new_client, /new_vehicle in Telegram's menu

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 11: README, спек, проверка на живом стеке

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-10-02-crm-bot-navigation-design.md` (status line)

- [ ] **Step 1: README — what the bot does per role**

In `README.md`, insert a new section after «## Первый администратор» (before «## Повседневные команды») and add `- [Что умеет бот](#что-умеет-бот)` to the table of contents after «Первый администратор»:

```markdown
## Что умеет бот

| Роль | Меню | Что внутри |
|---|---|---|
| Администратор | Новый заезд, Заезды в работе, Поиск, Регистрация клиента (бумага), Добавить сотрудника | всё, что у мастера; в «Новом заезде» выбирает ответственного мастера |
| Мастер | Новый заезд, Заезды в работе, Поиск, Регистрация клиента (бумага) | карточка заезда: статусы, работы, запчасти, согласование, PDF; поиск → карточки клиента и машины → их заезды, «Новый заезд» прямо из карточки машины |
| Механик | Мои работы, Поиск | свои работы и их статусы; поиск машины по VIN/госномеру → карточка машины и история работ (без данных клиента и цен) |

Команды (кнопка «Меню» в Telegram): `/start`, `/cancel`, `/new_client`, `/new_vehicle`.
```

- [ ] **Step 2: Mark the spec implemented**

In the spec change `Статус: на ревью` to `Статус: реализовано`.

- [ ] **Step 3: Full suite**

Run: `.venv/bin/pytest -q`
Expected: all pass, 0 failures.

- [ ] **Step 4: Live smoke on Docker**

```bash
docker compose up -d --build --wait api
docker compose up -d bot
docker compose logs bot | tail -5
```
Expected: bot log shows `Authorized as @...` and `Start polling`, no tracebacks.

Then, with a MASTER user (`docker compose exec postgres psql -U crm crm -c "SELECT id, role, telegram_id FROM users;"`):

```bash
MASTER_ID=<uuid of a master>
curl -s -H "X-User-Id: $MASTER_ID" "localhost:8000/visits?active=true"
```
Expected: JSON `{"items": [...], "has_more": false}`.

- [ ] **Step 5: Commit**

```bash
git add README.md docs/superpowers/specs/2026-10-02-crm-bot-navigation-design.md
git commit -m "docs: bot features by role; mark navigation spec implemented

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
