# CRM Bot — Gap Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the new-visit entry wizard, complete the work-item creation flow (category selection), and add the approve/status-change buttons the original spec called for but the 2026-09-19 plan's literal Steps never built.

**Architecture:** One small backend addition (`GET /visits/{id}/work-items`) plus six bot-side additions layered on the existing thin-client `ApiClient` pattern — no new architectural concepts, everything reuses pieces already built in Tasks 1–10 of the prior plan (`ApiClient.search`, `GET /clients|vehicles/{id}`, `GET /catalog/suggest`'s category field, `AuthMiddleware`'s injected `user`).

**Tech Stack:** aiogram 3 (FSM wizards, inline keyboards), httpx (`ApiClient`), FastAPI/SQLAlchemy (backend), pytest + pytest-asyncio + respx.

**Spec:** `docs/superpowers/specs/2026-09-23-crm-bot-gaps-design.md` (extends `docs/superpowers/specs/2026-09-19-crm-bot-design.md`)

## Global Constraints

- Бот не имеет прямого доступа к БД, только HTTP к CRM API (backend — единый источник правды).
- Мастер заезда всегда = текущий пользователь бота (`user["id"]` из `AuthMiddleware`) — переназначение на другого мастера не реализуется.
- Поиск клиента/авто в визарде заезда показывает не более 5 совпадений inline-кнопками; 0 совпадений — автопереход в визард создания.
- `is_extra_work` не выставляется из бот-UI (остаётся `False` по умолчанию схемы) — вне охвата.
- Смена статуса работы у механика — одна кнопка "следующий статус" по порядку `WorkItemStatus` (`not_ready → in_progress → waiting_parts → ready`), без ветвящегося графа переходов, аналогичного `_NEXT_STATUS_BY_CURRENT` у заезда.
- Каждая задача заканчивается запуском полного набора тестов (`python -m pytest -q` из корня worktree с активным `.venv` этого worktree — см. `.superpowers/sdd/2026-09-19-crm-bot-plan/progress.md` про ловушку с `VIRTUAL_ENV`, указывающим на основной чекаут).

---

## Task 1: Backend — `GET /visits/{visit_id}/work-items`

**Files:**
- Modify: `app/modules/visits/work_items_router.py`
- Modify: `app/modules/visits/work_items_service.py`
- Modify: `app/modules/visits/work_items_schemas.py`
- Test: `tests/modules/visits/test_work_items.py`

**Interfaces:**
- Consumes: `Visit`, `VisitWorkItem` models (existing), `VisitNotFound` exception (existing).
- Produces: `WorkItemService.list_for_visit(visit_id: uuid.UUID) -> list[VisitWorkItem]`, route `GET /visits/{visit_id}/work-items` (response model `list[WorkItemOut]`), `WorkItemOut` extended with `free_text_name: str | None` and `catalog_item_id: uuid.UUID | None`.

- [ ] **Step 1: Write the failing test**

Add to `tests/modules/visits/test_work_items.py`:

```python
async def test_list_for_visit_returns_items_for_that_visit(session):
    admin, mechanic_a, mechanic_b, item = await _setup_visit_with_mechanic(session)

    items = await WorkItemService(session).list_for_visit(item.visit_id)

    assert [i.id for i in items] == [item.id]


async def test_list_for_visit_unknown_visit_raises_not_found(session):
    with pytest.raises(VisitNotFound):
        await WorkItemService(session).list_for_visit(uuid.uuid4())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/modules/visits/test_work_items.py -v -k list_for_visit`
Expected: FAIL with `AttributeError: 'WorkItemService' object has no attribute 'list_for_visit'`

- [ ] **Step 3: Implement `WorkItemService.list_for_visit`**

In `app/modules/visits/work_items_service.py`, add to the `WorkItemService` class (after `list_mine`):

```python
    async def list_for_visit(self, visit_id: uuid.UUID) -> list[VisitWorkItem]:
        visit = await self.session.get(Visit, visit_id)
        if visit is None:
            raise VisitNotFound()
        result = await self.session.execute(
            select(VisitWorkItem).where(VisitWorkItem.visit_id == visit_id)
        )
        return list(result.scalars())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/modules/visits/test_work_items.py -v -k list_for_visit`
Expected: PASS

- [ ] **Step 5: Extend `WorkItemOut` and add the route**

In `app/modules/visits/work_items_schemas.py`, replace the `WorkItemOut` class:

```python
class WorkItemOut(BaseModel):
    id: uuid.UUID
    status: WorkItemStatus
    approved_by_client: bool
    free_text_name: str | None
    catalog_item_id: uuid.UUID | None

    class Config:
        from_attributes = True
```

In `app/modules/visits/work_items_router.py`, add (after the `add_work_item` route):

```python
@router.get("", response_model=list[WorkItemOut])
async def list_work_items(
    visit_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    acting_user: User = Depends(require_role(UserRole.ADMIN, UserRole.MASTER, UserRole.MECHANIC)),
):
    service = WorkItemService(session)
    try:
        return await service.list_for_visit(visit_id)
    except VisitNotFound:
        raise HTTPException(404, "Visit not found")
```

- [ ] **Step 6: Run full backend test suite**

Run: `python -m pytest -q`
Expected: all pass

- [ ] **Step 7: Commit**

```bash
git add app/modules/visits/work_items_router.py app/modules/visits/work_items_service.py app/modules/visits/work_items_schemas.py tests/modules/visits/test_work_items.py
git commit -m "feat: add GET /visits/{id}/work-items for bot card and approve-button rendering"
```

---

## Task 2: Bot — visit card gains "Согласовать работу" buttons

**Files:**
- Modify: `bot/api_client.py`
- Modify: `bot/handlers/visits.py`
- Test: `tests/bot/test_visits_handler.py`

**Interfaces:**
- Consumes: `GET /visits/{visit_id}/work-items` (Task 1), existing `VisitOut`/`WorkItemOut` shapes.
- Produces: `ApiClient.get_visit(visit_id) -> dict`, `ApiClient.list_work_items(visit_id) -> list[dict]`, `ApiClient.approve_work_item(visit_id, item_id) -> dict`, `send_visit_card(message, visit: dict, work_items: list[dict]) -> None` (signature change: now takes `work_items` — every future caller, including Task 13 of the original plan, must pass it), `bot.handlers.visits.approve_work_callback`.

- [ ] **Step 1: Write the failing tests**

Replace the contents of `tests/bot/test_visits_handler.py` with:

```python
from unittest.mock import AsyncMock

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.base import StorageKey

from bot.handlers.visits import approve_work_callback, receive_mileage, send_visit_card
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

    await send_visit_card(message, visit, [])

    message.answer.assert_awaited_once()
    _, kwargs = message.answer.await_args
    assert kwargs["reply_markup"] is not None


async def test_send_visit_card_shows_approve_button_for_unapproved_item():
    message = AsyncMock()
    visit = {"id": "visit1", "status": "in_progress", "total_amount": "0.00"}
    work_items = [{"id": "wi1", "free_text_name": "Замена масла", "approved_by_client": False}]

    await send_visit_card(message, visit, work_items)

    _, kwargs = message.answer.await_args
    markup = kwargs["reply_markup"]
    texts = [button.text for row in markup.inline_keyboard for button in row]
    assert "✅ Замена масла" in texts


async def test_send_visit_card_skips_approve_button_for_approved_item():
    message = AsyncMock()
    visit = {"id": "visit1", "status": "in_progress", "total_amount": "0.00"}
    work_items = [{"id": "wi1", "free_text_name": "Замена масла", "approved_by_client": True}]

    await send_visit_card(message, visit, work_items)

    _, kwargs = message.answer.await_args
    markup = kwargs["reply_markup"]
    texts = [button.text for row in markup.inline_keyboard for button in row]
    assert not any(t.startswith("✅") for t in texts)


async def test_approve_work_callback_approves_and_refreshes_card():
    callback = AsyncMock()
    callback.data = "approve_work:visit1:wi1"
    api = AsyncMock()
    api.get_visit.return_value = {"id": "visit1", "status": "in_progress", "total_amount": "0.00"}
    api.list_work_items.return_value = []

    await approve_work_callback(callback, api=api)

    api.approve_work_item.assert_awaited_once_with("visit1", "wi1")
    api.get_visit.assert_awaited_once_with("visit1")
    callback.message.answer.assert_awaited_once()
    callback.answer.assert_awaited_once()
```

Note: `test_receive_mileage_creates_visit_via_api` is unchanged from Task 10 — `receive_mileage` still reads `data["master_id"]` at this point; that logic changes in Task 4, not here. This task only widens `send_visit_card`'s signature, and `receive_mileage`'s own call site gets the mechanical third argument in Step 3 below.

- [ ] **Step 2: Run tests to verify the new ones fail**

Run: `python -m pytest tests/bot/test_visits_handler.py -v`
Expected: `test_send_visit_card_shows_status_buttons` FAILs with `TypeError: send_visit_card() takes 2 positional arguments but 3 were given`; the two new approve-button tests and the callback test FAIL with the same `TypeError` or `ImportError: cannot import name 'approve_work_callback'`.

- [ ] **Step 3: Add ApiClient methods**

In `bot/api_client.py`, add to `ApiClient` (after `change_visit_status`):

```python
    async def get_visit(self, visit_id: str) -> dict:
        return await self.get(f"/visits/{visit_id}")

    async def list_work_items(self, visit_id: str) -> list[dict]:
        return await self.get(f"/visits/{visit_id}/work-items")

    async def approve_work_item(self, visit_id: str, item_id: str) -> dict:
        return await self.post(f"/visits/{visit_id}/work-items/{item_id}/approve")
```

- [ ] **Step 4: Update `send_visit_card`, `receive_mileage`'s call site, and add `approve_work_callback`**

In `bot/handlers/visits.py`, replace `send_visit_card` and add the new callback (keep everything else, including `receive_mileage`'s `data["master_id"]` line, unchanged):

```python
async def send_visit_card(message: Message, visit: dict, work_items: list[dict]) -> None:
    builder = InlineKeyboardBuilder()
    for status in _NEXT_STATUS_BY_CURRENT.get(visit["status"], []):
        builder.button(text=status, callback_data=f"visit_status:{visit['id']}:{status}")
    for item in work_items:
        if item.get("approved_by_client") is False:
            name = item.get("free_text_name") or "работа"
            builder.button(text=f"✅ {name}", callback_data=f"approve_work:{visit['id']}:{item['id']}")
    builder.adjust(1)
    await message.answer(
        f"Заезд {visit['id']}\nСтатус: {visit['status']}\nСумма: {visit.get('total_amount', '—')}",
        reply_markup=builder.as_markup(),
    )
```

In `receive_mileage`, change the final line from `await send_visit_card(message, visit)` to `await send_visit_card(message, visit, [])` (a brand-new visit has no work items yet).

Add after `change_status_callback`:

```python
@router.callback_query(lambda c: c.data.startswith("approve_work:"))
async def approve_work_callback(callback: CallbackQuery, api: ApiClient, **kwargs) -> None:
    _, visit_id, item_id = callback.data.split(":")
    await api.approve_work_item(visit_id, item_id)
    visit = await api.get_visit(visit_id)
    items = await api.list_work_items(visit_id)
    await send_visit_card(callback.message, visit, items)
    await callback.answer()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/bot/test_visits_handler.py -v`
Expected: PASS

- [ ] **Step 6: Run full test suite**

Run: `python -m pytest -q`
Expected: all pass

- [ ] **Step 7: Commit**

```bash
git add bot/api_client.py bot/handlers/visits.py tests/bot/test_visits_handler.py
git commit -m "feat: bot visit card shows approve buttons for unapproved work items"
```

---

## Task 3: Bot — new-visit wizard, client step

**Files:**
- Modify: `bot/states.py`
- Modify: `bot/api_client.py`
- Modify: `bot/handlers/visits.py`
- Modify: `bot/handlers/clients.py`
- Test: `tests/bot/test_visits_handler.py`
- Test: `tests/bot/test_clients_handler.py`

**Interfaces:**
- Consumes: `ApiClient.search` (existing, unused until now), `NewClientStates` (existing).
- Produces: `NewVisitStates.waiting_for_client_query`/`choosing_client`/`waiting_for_vehicle_query` (replaces the unused `choosing_master`), `ApiClient.get_client(client_id) -> dict`, `bot.handlers.visits.start_new_visit`, `receive_client_query`, `choose_client_callback`. `bot.handlers.clients.receive_full_name` now branches on `data.get("return_flow") == "new_visit"`.

- [ ] **Step 1: Update `NewVisitStates`**

In `bot/states.py`, replace the `NewVisitStates` class:

```python
class NewVisitStates(StatesGroup):
    waiting_for_client_query = State()
    choosing_client = State()
    waiting_for_vehicle_query = State()
    choosing_vehicle = State()
    waiting_for_mileage = State()
```

(`choosing_master` is removed — the master is always the acting user, per Global Constraints.)

- [ ] **Step 2: Write the failing tests**

Add to `tests/bot/test_visits_handler.py` (add these imports to the existing `from bot.handlers.visits import ...` line: `choose_client_callback, receive_client_query, start_new_visit`; add `from bot.states import NewClientStates, NewVisitStates` — `NewClientStates` is new):

```python
async def test_start_new_visit_asks_for_client():
    message = AsyncMock()
    state = _fsm_context()

    await start_new_visit(message, state)

    assert (await state.get_state()) == NewVisitStates.waiting_for_client_query.state


async def test_receive_client_query_shows_candidates():
    message = AsyncMock()
    message.text = "Иван"
    state = _fsm_context()
    await state.set_state(NewVisitStates.waiting_for_client_query)
    api = AsyncMock()
    api.search.return_value = [{"entity": "client", "id": "c1", "matched_field": "full_name"}]
    api.get_client.return_value = {"id": "c1", "full_name": "Иван Иванов"}

    await receive_client_query(message, state, api=api)

    api.get_client.assert_awaited_once_with("c1")
    assert (await state.get_state()) == NewVisitStates.choosing_client.state


async def test_receive_client_query_falls_back_to_creation_when_no_matches():
    message = AsyncMock()
    message.text = "неизвестный"
    state = _fsm_context()
    await state.set_state(NewVisitStates.waiting_for_client_query)
    api = AsyncMock()
    api.search.return_value = []

    await receive_client_query(message, state, api=api)

    assert (await state.get_state()) == NewClientStates.waiting_for_phone.state
    data = await state.get_data()
    assert data["return_flow"] == "new_visit"


async def test_choose_client_callback_stores_client_id():
    callback = AsyncMock()
    callback.data = "client_pick:c1"
    state = _fsm_context()

    await choose_client_callback(callback, state)

    data = await state.get_data()
    assert data["client_id"] == "c1"
    assert (await state.get_state()) == NewVisitStates.waiting_for_vehicle_query.state
```

Add to `tests/bot/test_clients_handler.py` (add `from bot.states import NewVisitStates` to the imports):

```python
async def test_receive_full_name_continues_new_visit_wizard_when_return_flow_set():
    message = AsyncMock()
    message.text = "Иван Иванов"
    state = _fsm_context()
    await state.update_data(phone="79991234567", return_flow="new_visit")
    api = AsyncMock()
    api.create_client.return_value = {"id": "c1", "full_name": "Иван Иванов"}

    await receive_full_name(message, state, api=api)

    assert (await state.get_state()) == NewVisitStates.waiting_for_vehicle_query.state
    data = await state.get_data()
    assert data["client_id"] == "c1"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/bot/test_visits_handler.py tests/bot/test_clients_handler.py -v`
Expected: FAIL — `ImportError` for the three new `visits` names, and the new `clients` test asserts a state that the current `receive_full_name` never sets (it always clears state).

- [ ] **Step 4: Add `ApiClient.get_client`**

In `bot/api_client.py`, add (after `get_user_by_telegram`):

```python
    async def get_client(self, client_id: str) -> dict:
        return await self.get(f"/clients/{client_id}")
```

- [ ] **Step 5: Implement the client step in `bot/handlers/visits.py`**

Change the first import line to `from aiogram import F, Router` and add `NewClientStates` to the states import: `from bot.states import NewClientStates, NewVisitStates`.

Add (after the imports, before `_NEXT_STATUS_BY_CURRENT`, or anywhere in the module — order doesn't matter to Python, keep it near the top for readability):

```python
@router.message(F.text == "Новый заезд")
async def start_new_visit(message: Message, state: FSMContext, **kwargs) -> None:
    await state.set_state(NewVisitStates.waiting_for_client_query)
    await message.answer("Введите телефон или ФИО клиента:")


@router.message(NewVisitStates.waiting_for_client_query)
async def receive_client_query(message: Message, state: FSMContext, api: ApiClient, **kwargs) -> None:
    results = await api.search(message.text)
    client_ids = [r["id"] for r in results if r["entity"] == "client"][:5]
    if not client_ids:
        await state.update_data(return_flow="new_visit")
        await state.set_state(NewClientStates.waiting_for_phone)
        await message.answer("Клиент не найден. Введите телефон клиента:")
        return
    builder = InlineKeyboardBuilder()
    for client_id in client_ids:
        client = await api.get_client(client_id)
        builder.button(text=client["full_name"], callback_data=f"client_pick:{client_id}")
    builder.adjust(1)
    await state.set_state(NewVisitStates.choosing_client)
    await message.answer("Выберите клиента:", reply_markup=builder.as_markup())


@router.callback_query(lambda c: c.data.startswith("client_pick:"))
async def choose_client_callback(callback: CallbackQuery, state: FSMContext, **kwargs) -> None:
    _, client_id = callback.data.split(":")
    await state.update_data(client_id=client_id)
    await state.set_state(NewVisitStates.waiting_for_vehicle_query)
    await callback.message.answer("Введите VIN или гос.номер авто:")
    await callback.answer()
```

- [ ] **Step 6: Wire `return_flow` into `bot/handlers/clients.py`**

Add `NewVisitStates` to the states import: `from bot.states import NewClientStates, NewVisitStates`.

Replace `receive_full_name`:

```python
@router.message(NewClientStates.waiting_for_full_name)
async def receive_full_name(message: Message, state: FSMContext, api: ApiClient, **kwargs) -> None:
    data = await state.get_data()
    client = await api.create_client(full_name=message.text, phone=data["phone"])
    if data.get("return_flow") == "new_visit":
        await state.update_data(client_id=client["id"])
        await state.set_state(NewVisitStates.waiting_for_vehicle_query)
        await message.answer(f"Клиент создан: {client['full_name']}\nВведите VIN или гос.номер авто:")
        return
    await state.clear()
    await message.answer(f"Клиент создан: {client['full_name']}")
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `python -m pytest tests/bot/test_visits_handler.py tests/bot/test_clients_handler.py -v`
Expected: PASS

- [ ] **Step 8: Run full test suite**

Run: `python -m pytest -q`
Expected: all pass

- [ ] **Step 9: Commit**

```bash
git add bot/states.py bot/api_client.py bot/handlers/visits.py bot/handlers/clients.py tests/bot/test_visits_handler.py tests/bot/test_clients_handler.py
git commit -m "feat: new-visit wizard client step (search-or-create)"
```

---

## Task 4: Bot — new-visit wizard, vehicle step + master auto-assignment

**Files:**
- Modify: `bot/api_client.py`
- Modify: `bot/handlers/visits.py`
- Modify: `bot/handlers/vehicles.py`
- Test: `tests/bot/test_visits_handler.py`
- Test: `tests/bot/test_vehicles_handler.py`

**Interfaces:**
- Consumes: `ApiClient.search` (existing), `NewVehicleStates` (existing), `user: dict` (injected by `AuthMiddleware`, already available to every handler that declares it).
- Produces: `ApiClient.get_vehicle(vehicle_id) -> dict`, `bot.handlers.visits.receive_vehicle_query`, `choose_vehicle_callback`; `receive_mileage` now takes `user: dict` and no longer reads `data["master_id"]`. `bot.handlers.vehicles.receive_make_model` now branches on `data.get("return_flow") == "new_visit"`.

- [ ] **Step 1: Write the failing tests**

In `tests/bot/test_visits_handler.py`:
- Add `choose_vehicle_callback, receive_vehicle_query` to the `from bot.handlers.visits import ...` line.
- Replace `test_receive_mileage_creates_visit_via_api` with:

```python
async def test_receive_mileage_uses_acting_user_as_master():
    message = AsyncMock()
    message.text = "45000"
    state = _fsm_context()
    await state.set_state(NewVisitStates.waiting_for_mileage)
    await state.update_data(client_id="c1", vehicle_id="v1")
    api = AsyncMock()
    api.create_visit.return_value = {"id": "visit1", "status": "received"}
    user = {"id": "m1"}

    await receive_mileage(message, state, api=api, user=user)

    api.create_visit.assert_awaited_once_with(
        client_id="c1", vehicle_id="v1", assigned_master_id="m1", mileage_at_intake=45000
    )
    assert (await state.get_state()) is None
```

Add:

```python
async def test_receive_vehicle_query_shows_candidates():
    message = AsyncMock()
    message.text = "А123"
    state = _fsm_context()
    await state.set_state(NewVisitStates.waiting_for_vehicle_query)
    api = AsyncMock()
    api.search.return_value = [{"entity": "vehicle", "id": "v1", "matched_field": "plate_number"}]
    api.get_vehicle.return_value = {"id": "v1", "plate_number": "А123"}

    await receive_vehicle_query(message, state, api=api)

    api.get_vehicle.assert_awaited_once_with("v1")
    assert (await state.get_state()) == NewVisitStates.choosing_vehicle.state


async def test_receive_vehicle_query_falls_back_to_creation_when_no_matches():
    message = AsyncMock()
    message.text = "неизвестный VIN"
    state = _fsm_context()
    await state.set_state(NewVisitStates.waiting_for_vehicle_query)
    api = AsyncMock()
    api.search.return_value = []

    await receive_vehicle_query(message, state, api=api)

    assert (await state.get_state()) == NewVehicleStates.waiting_for_vin.state
    data = await state.get_data()
    assert data["return_flow"] == "new_visit"


async def test_choose_vehicle_callback_stores_vehicle_id():
    callback = AsyncMock()
    callback.data = "vehicle_pick:v1"
    state = _fsm_context()

    await choose_vehicle_callback(callback, state)

    data = await state.get_data()
    assert data["vehicle_id"] == "v1"
    assert (await state.get_state()) == NewVisitStates.waiting_for_mileage.state
```

This needs `from bot.states import NewClientStates, NewVehicleStates, NewVisitStates` (add `NewVehicleStates`).

In `tests/bot/test_vehicles_handler.py`, add `from bot.states import NewVisitStates` and:

```python
async def test_receive_make_model_continues_new_visit_wizard_when_return_flow_set():
    message = AsyncMock()
    message.text = "Toyota Camry"
    state = _fsm_context()
    await state.update_data(vin="X" * 17, plate_number="А123", return_flow="new_visit")
    api = AsyncMock()
    api.create_vehicle.return_value = {"id": "v1", "vin": "X" * 17}

    await receive_make_model(message, state, api=api)

    assert (await state.get_state()) == NewVisitStates.waiting_for_mileage.state
    data = await state.get_data()
    assert data["vehicle_id"] == "v1"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/bot/test_visits_handler.py tests/bot/test_vehicles_handler.py -v`
Expected: FAIL — `ImportError` for the new `visits` names; `test_receive_mileage_uses_acting_user_as_master` fails because `receive_mileage` doesn't accept `user` yet; the new `vehicles` test fails because `receive_make_model` always clears state.

- [ ] **Step 3: Add `ApiClient.get_vehicle`**

In `bot/api_client.py`, add (after `get_client`):

```python
    async def get_vehicle(self, vehicle_id: str) -> dict:
        return await self.get(f"/vehicles/{vehicle_id}")
```

- [ ] **Step 4: Implement the vehicle step and master fix in `bot/handlers/visits.py`**

Add `NewVehicleStates` to the states import: `from bot.states import NewClientStates, NewVehicleStates, NewVisitStates`.

Add (near `receive_client_query`/`choose_client_callback`):

```python
@router.message(NewVisitStates.waiting_for_vehicle_query)
async def receive_vehicle_query(message: Message, state: FSMContext, api: ApiClient, **kwargs) -> None:
    results = await api.search(message.text)
    vehicle_ids = [r["id"] for r in results if r["entity"] == "vehicle"][:5]
    if not vehicle_ids:
        await state.update_data(return_flow="new_visit")
        await state.set_state(NewVehicleStates.waiting_for_vin)
        await message.answer("Автомобиль не найден. Введите VIN:")
        return
    builder = InlineKeyboardBuilder()
    for vehicle_id in vehicle_ids:
        vehicle = await api.get_vehicle(vehicle_id)
        builder.button(text=vehicle["plate_number"], callback_data=f"vehicle_pick:{vehicle_id}")
    builder.adjust(1)
    await state.set_state(NewVisitStates.choosing_vehicle)
    await message.answer("Выберите автомобиль:", reply_markup=builder.as_markup())


@router.callback_query(lambda c: c.data.startswith("vehicle_pick:"))
async def choose_vehicle_callback(callback: CallbackQuery, state: FSMContext, **kwargs) -> None:
    _, vehicle_id = callback.data.split(":")
    await state.update_data(vehicle_id=vehicle_id)
    await state.set_state(NewVisitStates.waiting_for_mileage)
    await callback.message.answer("Введите пробег на приёмке:")
    await callback.answer()
```

Replace `receive_mileage`:

```python
@router.message(NewVisitStates.waiting_for_mileage)
async def receive_mileage(message: Message, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    data = await state.get_data()
    visit = await api.create_visit(
        client_id=data["client_id"],
        vehicle_id=data["vehicle_id"],
        assigned_master_id=user["id"],
        mileage_at_intake=int(message.text),
    )
    await state.clear()
    await send_visit_card(message, visit, [])
```

- [ ] **Step 5: Wire `return_flow` into `bot/handlers/vehicles.py`**

Add `from bot.states import NewVehicleStates, NewVisitStates` (replacing the single-import line).

Replace `receive_make_model`:

```python
@router.message(NewVehicleStates.waiting_for_make_model)
async def receive_make_model(message: Message, state: FSMContext, api: ApiClient, **kwargs) -> None:
    make, _, model = message.text.partition(" ")
    data = await state.get_data()
    vehicle = await api.create_vehicle(vin=data["vin"], plate_number=data["plate_number"], make=make, model=model)
    if data.get("return_flow") == "new_visit":
        await state.update_data(vehicle_id=vehicle["id"])
        await state.set_state(NewVisitStates.waiting_for_mileage)
        await message.answer(f"Автомобиль создан: {vehicle['vin']}\nВведите пробег на приёмке:")
        return
    await state.clear()
    await message.answer(f"Автомобиль создан: {vehicle['vin']}")
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/bot/test_visits_handler.py tests/bot/test_vehicles_handler.py -v`
Expected: PASS

- [ ] **Step 7: Run full test suite**

Run: `python -m pytest -q`
Expected: all pass

- [ ] **Step 8: Commit**

```bash
git add bot/api_client.py bot/handlers/visits.py bot/handlers/vehicles.py tests/bot/test_visits_handler.py tests/bot/test_vehicles_handler.py
git commit -m "feat: new-visit wizard vehicle step, master defaults to acting user"
```

---

## Task 5: Bot — work-item creation wizard (category completion)

**Files:**
- Modify: `bot/states.py`
- Modify: `bot/api_client.py`
- Create: `bot/handlers/work_items.py`
- Modify: `bot/main.py`
- Test: `tests/bot/test_work_items_handler.py`

**Interfaces:**
- Consumes: `ApiClient`, `AddWorkItemStates`, `send_visit_card` (Task 2), `ApiClient.get_visit`/`list_work_items` (Task 2), `GET /catalog/suggest`'s `category`/`default_norm_hours` fields (existing backend).
- Produces: `ApiClient.suggest_catalog(text) -> list[dict]`, `ApiClient.add_work_item(visit_id, **fields) -> dict`, `bot.handlers.work_items.router`.

- [ ] **Step 1: Add `choosing_category` state**

In `bot/states.py`, replace `AddWorkItemStates`:

```python
class AddWorkItemStates(StatesGroup):
    waiting_for_name = State()
    choosing_suggestion = State()
    choosing_category = State()
    waiting_for_hours_and_rate = State()
```

- [ ] **Step 2: Write the failing tests**

Create `tests/bot/test_work_items_handler.py`:

```python
from unittest.mock import AsyncMock

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.base import StorageKey

from bot.handlers.work_items import (
    choose_catalog_callback,
    choose_category_callback,
    receive_hours_and_rate,
    receive_work_name,
)
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
    api.suggest_catalog.return_value = [
        {"id": "cat1", "name": "Замена масла", "category": "maintenance", "default_norm_hours": 1.0}
    ]

    await receive_work_name(message, state, api=api)

    api.suggest_catalog.assert_awaited_once_with("замена масла")
    assert (await state.get_state()) == AddWorkItemStates.choosing_suggestion.state
    data = await state.get_data()
    assert data["suggestions"]["cat1"]["category"] == "maintenance"


async def test_choose_catalog_callback_carries_category_and_hours():
    callback = AsyncMock()
    callback.data = "catalog_pick:cat1"
    state = _fsm_context()
    await state.update_data(
        visit_id="visit1",
        suggestions={"cat1": {"id": "cat1", "category": "maintenance", "default_norm_hours": 1.0}},
    )

    await choose_catalog_callback(callback, state)

    data = await state.get_data()
    assert data["category"] == "maintenance"
    assert data["norm_hours"] == 1.0
    assert (await state.get_state()) == AddWorkItemStates.waiting_for_hours_and_rate.state


async def test_choose_catalog_callback_none_asks_for_category():
    callback = AsyncMock()
    callback.data = "catalog_pick:none"
    state = _fsm_context()

    await choose_catalog_callback(callback, state)

    assert (await state.get_state()) == AddWorkItemStates.choosing_category.state


async def test_choose_category_callback_stores_category():
    callback = AsyncMock()
    callback.data = "category_pick:body"
    state = _fsm_context()

    await choose_category_callback(callback, state)

    data = await state.get_data()
    assert data["category"] == "body"
    assert (await state.get_state()) == AddWorkItemStates.waiting_for_hours_and_rate.state


async def test_receive_hours_and_rate_from_catalog_path_asks_only_rate():
    message = AsyncMock()
    message.text = "800"
    state = _fsm_context()
    await state.update_data(visit_id="visit1", catalog_item_id="cat1", category="maintenance", norm_hours=1.0)
    api = AsyncMock()
    api.get_visit.return_value = {"id": "visit1", "status": "received", "total_amount": "0.00"}
    api.list_work_items.return_value = []

    await receive_hours_and_rate(message, state, api=api)

    api.add_work_item.assert_awaited_once_with(
        "visit1", catalog_item_id="cat1", free_text_name=None, category="maintenance",
        norm_hours=1.0, hourly_rate=800.0,
    )
    assert (await state.get_state()) is None


async def test_receive_hours_and_rate_from_free_text_path_parses_both():
    message = AsyncMock()
    message.text = "1.5 900"
    state = _fsm_context()
    await state.update_data(visit_id="visit1", free_text_name="Своя работа", category="body")
    api = AsyncMock()
    api.get_visit.return_value = {"id": "visit1", "status": "received", "total_amount": "0.00"}
    api.list_work_items.return_value = []

    await receive_hours_and_rate(message, state, api=api)

    api.add_work_item.assert_awaited_once_with(
        "visit1", catalog_item_id=None, free_text_name="Своя работа", category="body",
        norm_hours=1.5, hourly_rate=900.0,
    )
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/bot/test_work_items_handler.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bot.handlers.work_items'`

- [ ] **Step 4: Add ApiClient methods**

In `bot/api_client.py`, add (after `get_vehicle`):

```python
    async def suggest_catalog(self, text: str) -> list[dict]:
        return await self.get(f"/catalog/suggest?text={text}")

    async def add_work_item(self, visit_id: str, **fields) -> dict:
        return await self.post(f"/visits/{visit_id}/work-items", json=fields)
```

- [ ] **Step 5: Implement `bot/handlers/work_items.py`**

```python
from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.api_client import ApiClient
from bot.handlers.visits import send_visit_card
from bot.states import AddWorkItemStates

router = Router()

_CATEGORY_LABELS = {
    "Диагностика": "diagnostics",
    "ТО": "maintenance",
    "Кузовные": "body",
    "Электрика": "electrical",
    "Ходовая": "chassis",
    "Прочее": "other",
}


@router.message(AddWorkItemStates.waiting_for_name)
async def receive_work_name(message: Message, state: FSMContext, api: ApiClient, **kwargs) -> None:
    suggestions = await api.suggest_catalog(message.text)
    await state.update_data(
        free_text_name=message.text,
        suggestions={item["id"]: item for item in suggestions},
    )
    builder = InlineKeyboardBuilder()
    for item in suggestions:
        builder.button(text=item["name"], callback_data=f"catalog_pick:{item['id']}")
    builder.button(text="Своя формулировка", callback_data="catalog_pick:none")
    builder.adjust(1)
    await state.set_state(AddWorkItemStates.choosing_suggestion)
    await message.answer("Выберите работу из справочника или укажите свою:", reply_markup=builder.as_markup())


@router.callback_query(lambda c: c.data.startswith("catalog_pick:"))
async def choose_catalog_callback(callback: CallbackQuery, state: FSMContext, **kwargs) -> None:
    _, picked = callback.data.split(":")
    if picked == "none":
        builder = InlineKeyboardBuilder()
        for label, value in _CATEGORY_LABELS.items():
            builder.button(text=label, callback_data=f"category_pick:{value}")
        builder.adjust(1)
        await state.set_state(AddWorkItemStates.choosing_category)
        await callback.message.answer("Выберите категорию работы:", reply_markup=builder.as_markup())
        await callback.answer()
        return
    data = await state.get_data()
    suggestion = data["suggestions"][picked]
    await state.update_data(
        catalog_item_id=picked,
        category=suggestion["category"],
        norm_hours=suggestion["default_norm_hours"],
    )
    await state.set_state(AddWorkItemStates.waiting_for_hours_and_rate)
    await callback.message.answer("Введите часовую ставку:")
    await callback.answer()


@router.callback_query(lambda c: c.data.startswith("category_pick:"))
async def choose_category_callback(callback: CallbackQuery, state: FSMContext, **kwargs) -> None:
    _, category = callback.data.split(":")
    await state.update_data(category=category)
    await state.set_state(AddWorkItemStates.waiting_for_hours_and_rate)
    await callback.message.answer("Введите нормо-часы и ставку через пробел (например: 1.5 800):")
    await callback.answer()


@router.message(AddWorkItemStates.waiting_for_hours_and_rate)
async def receive_hours_and_rate(message: Message, state: FSMContext, api: ApiClient, **kwargs) -> None:
    data = await state.get_data()
    if "norm_hours" in data:
        norm_hours = data["norm_hours"]
        hourly_rate = float(message.text)
    else:
        norm_hours_text, hourly_rate_text = message.text.split()
        norm_hours = float(norm_hours_text)
        hourly_rate = float(hourly_rate_text)

    await api.add_work_item(
        data["visit_id"],
        catalog_item_id=data.get("catalog_item_id"),
        free_text_name=None if data.get("catalog_item_id") else data["free_text_name"],
        category=data["category"],
        norm_hours=norm_hours,
        hourly_rate=hourly_rate,
    )
    visit_id = data["visit_id"]
    await state.clear()
    visit = await api.get_visit(visit_id)
    items = await api.list_work_items(visit_id)
    await send_visit_card(message, visit, items)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/bot/test_work_items_handler.py -v`
Expected: PASS

- [ ] **Step 7: Register the router in `bot/main.py`**

Change the handlers import to `from bot.handlers import start, clients, vehicles, visits, work_items` and add `dp.include_router(work_items.router)` after `dp.include_router(visits.router)`.

- [ ] **Step 8: Run full test suite**

Run: `python -m pytest -q`
Expected: all pass

- [ ] **Step 9: Commit**

```bash
git add bot/states.py bot/api_client.py bot/handlers/work_items.py bot/main.py tests/bot/test_work_items_handler.py
git commit -m "feat: bot work-item creation wizard with category selection"
```

---

## Task 6: Bot — mechanic "Мои работы" status button

**Files:**
- Modify: `bot/api_client.py`
- Create: `bot/handlers/mechanic.py`
- Modify: `bot/main.py`
- Test: `tests/bot/test_mechanic_handler.py`

**Interfaces:**
- Consumes: `ApiClient`.
- Produces: `ApiClient.list_my_work_items() -> list[dict]` (calls `GET /work-items/mine`), `ApiClient.update_work_item_status(visit_id, item_id, new_status) -> dict`, `bot.handlers.mechanic.router`.

- [ ] **Step 1: Write the failing tests**

Create `tests/bot/test_mechanic_handler.py`:

```python
from unittest.mock import AsyncMock

from bot.handlers.mechanic import change_work_status_callback, show_my_work_items


async def test_show_my_work_items_handles_empty_list():
    message = AsyncMock()
    api = AsyncMock()
    api.list_my_work_items.return_value = []

    await show_my_work_items(message, api=api)

    message.answer.assert_awaited_once_with("У вас нет назначенных работ.")


async def test_show_my_work_items_sends_status_button_per_item():
    message = AsyncMock()
    api = AsyncMock()
    api.list_my_work_items.return_value = [
        {"id": "wi1", "visit_id": "visit1", "status": "not_ready", "free_text_name": "Замена масла", "catalog_item_id": None}
    ]

    await show_my_work_items(message, api=api)

    message.answer.assert_awaited_once()
    args, kwargs = message.answer.await_args
    assert "Замена масла" in args[0]
    assert kwargs["reply_markup"] is not None


async def test_show_my_work_items_omits_button_when_no_next_status():
    message = AsyncMock()
    api = AsyncMock()
    api.list_my_work_items.return_value = [
        {"id": "wi1", "visit_id": "visit1", "status": "ready", "free_text_name": "Замена масла", "catalog_item_id": None}
    ]

    await show_my_work_items(message, api=api)

    _, kwargs = message.answer.await_args
    assert kwargs["reply_markup"] is None


async def test_change_work_status_callback_updates_status():
    callback = AsyncMock()
    callback.data = "work_status:visit1:wi1:in_progress"
    api = AsyncMock()
    api.update_work_item_status.return_value = {"id": "wi1", "status": "in_progress"}

    await change_work_status_callback(callback, api=api)

    api.update_work_item_status.assert_awaited_once_with("visit1", "wi1", "in_progress")
    callback.message.answer.assert_awaited_once()
    callback.answer.assert_awaited_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/bot/test_mechanic_handler.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bot.handlers.mechanic'`

- [ ] **Step 3: Add ApiClient methods**

In `bot/api_client.py`, add (after `add_work_item`):

```python
    async def list_my_work_items(self) -> list[dict]:
        return await self.get("/work-items/mine")

    async def update_work_item_status(self, visit_id: str, item_id: str, new_status: str) -> dict:
        return await self.patch(f"/visits/{visit_id}/work-items/{item_id}/status", json={"new_status": new_status})
```

- [ ] **Step 4: Implement `bot/handlers/mechanic.py`**

```python
from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.api_client import ApiClient

router = Router()

_STATUS_ORDER = ["not_ready", "in_progress", "waiting_parts", "ready"]


def _next_status(current: str) -> str | None:
    if current not in _STATUS_ORDER:
        return None
    index = _STATUS_ORDER.index(current)
    if index + 1 >= len(_STATUS_ORDER):
        return None
    return _STATUS_ORDER[index + 1]


@router.message(F.text == "Мои работы")
async def show_my_work_items(message: Message, api: ApiClient, **kwargs) -> None:
    items = await api.list_my_work_items()
    if not items:
        await message.answer("У вас нет назначенных работ.")
        return
    for item in items:
        name = item["free_text_name"] or item["catalog_item_id"]
        text = f"{name} — {item['status']} (заезд {item['visit_id']})"
        next_status = _next_status(item["status"])
        markup = None
        if next_status:
            builder = InlineKeyboardBuilder()
            builder.button(
                text=f"→ {next_status}",
                callback_data=f"work_status:{item['visit_id']}:{item['id']}:{next_status}",
            )
            markup = builder.as_markup()
        await message.answer(text, reply_markup=markup)


@router.callback_query(lambda c: c.data.startswith("work_status:"))
async def change_work_status_callback(callback: CallbackQuery, api: ApiClient, **kwargs) -> None:
    _, visit_id, item_id, new_status = callback.data.split(":")
    item = await api.update_work_item_status(visit_id, item_id, new_status)
    await callback.message.answer(f"Статус обновлён: {item['status']}")
    await callback.answer()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/bot/test_mechanic_handler.py -v`
Expected: PASS

- [ ] **Step 6: Register the router in `bot/main.py`**

Change the handlers import to `from bot.handlers import start, clients, vehicles, visits, work_items, mechanic` and add `dp.include_router(mechanic.router)` after `dp.include_router(work_items.router)`.

- [ ] **Step 7: Run full test suite**

Run: `python -m pytest -q`
Expected: all pass

- [ ] **Step 8: Commit**

```bash
git add bot/api_client.py bot/handlers/mechanic.py bot/main.py tests/bot/test_mechanic_handler.py
git commit -m "feat: bot mechanic work-item list with status-change button"
```

---
