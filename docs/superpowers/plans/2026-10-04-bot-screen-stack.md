# Bot Screen Stack Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the bot's "new message per screen + reply keyboard" UI with one live message redrawn in place, a back/home screen stack, compact visit cards, wizards with step-back/cancel, and Redis-backed FSM storage.

**Architecture:** `bot/nav.py` keeps a stack of `[screen_name, args]` plus the live message id in FSM data and redraws screens registered with `@nav.screen`. `bot/wizard.py` runs multi-step input on the existing FSM states, recording step history so "‹ Назад" re-shows the previous prompt. Feature modules in `bot/handlers/` register screens, wizard steps and `act:` handlers. FSM storage switches to `RedisStorage` when `REDIS_URL` is set.

**Tech Stack:** Python 3.14, aiogram 3.31 (FSM, InlineKeyboardBuilder, RedisStorage), redis-py ≥5, FastAPI/SQLAlchemy (one backend schema change), pytest + pytest-asyncio (`asyncio_mode = "auto"`), Docker Compose.

**Spec:** `docs/superpowers/specs/2026-10-04-bot-screen-stack-design.md`

## Global Constraints

- Branch: `search-fixes` (already contains search pagination this plan rewrites).
- Run tests with `.venv/bin/pytest`. Backend tests need Postgres: `docker compose up -d postgres` first.
- Telegram `callback_data` ≤ 64 bytes. UUIDs in callbacks go through `bot.callback_ids.encode_id` (22 chars).
- All user-facing strings are Russian and must match the plan text exactly (tests assert them).
- **Callback answering rule:** `nav.push/pop/home/refresh/replace_top` and `wizard.start/goto/reprompt` answer a `CallbackQuery` themselves. A handler must not call `callback.answer()` after calling one of them. Handlers that don't redraw answer the callback themselves.
- **Never call `state.clear()` in a handler** — use `nav.clear_wizard(state)`, which keeps `nav_stack` and `nav_msg_id`.
- FSM data must be JSON-serializable (Redis): only `str/int/float/bool/None/list/dict`; store UUIDs as `str`.
- A callback event redraws (edits) the message it came from; a text-message event sends a new message. There is no `new_message` flag.
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **"Назад" after a step that created something** (client/vehicle in the new-visit wizard) must not create it again — history is dropped at that step (`wizard.goto(..., commit=True)`); test in Task 8.
2. **Back from the hours step to the catalog choice, then "Своя формулировка"** must ask for both hours and rate, not reuse the catalog's norm hours — test in Task 9.
3. **An `act:` button pressed on an old message or on the wrong screen** must be answered "Кнопка устарела", never applied to whatever screen is on top now — tests in Tasks 3 and 7.
4. **Opening a card whose entity is gone** (deleted visit; mechanic opens a work item reassigned away) shows an alert and leaves the stack untouched — tests in Tasks 3 and 7.
5. **Wizard data survives a restart** only if it serializes to JSON (Redis) — `json.dumps(await state.get_data())` test in Task 8 after the choice steps.

---

## File Structure

| File | Responsibility |
|---|---|
| `bot/nav.py` (new) | screen registry, stack ops, live-message presentation, `go/back/home` router |
| `bot/wizard.py` (new) | step-prompt registry, start/goto/reprompt/finish, `wiz_back/wiz_cancel` router |
| `bot/actions.py` (new) | `act:*` / `wiz:*` callback constants shared by screens and handlers (avoids import cycles) |
| `bot/handlers/menu.py` (rewrite) | `menu` screen; temporary handler for old reply-keyboard texts |
| `bot/handlers/start.py` (rewrite) | `/start`, `/menu`, `/cancel` |
| `bot/handlers/navigation.py` (rewrite) | screens: `active_visits`, `client`, `vehicle`, `client_visits`, `vehicle_visits`, `work_history` |
| `bot/handlers/visits.py` (rewrite) | screens `visit`, `visit_status`; status action; cancel-reason wizard; new-visit wizard |
| `bot/handlers/work_items.py` (rewrite) | screens `work`, `reassign`; work actions; add-work wizard |
| `bot/handlers/mechanic.py` (rewrite) | screen `my_works` |
| `bot/handlers/part_items.py`, `clients.py`, `vehicles.py`, `admin.py`, `consent.py` (rewrite) | their wizards on `bot.wizard` |
| `bot/handlers/search.py` (rewrite) | screens `search`, `search_results`; free-text handler; page action |
| `bot/handlers/documents.py` (rewrite) | PDF action |
| `bot/handlers/work_status.py`, `bot/keyboards.py` | deleted |
| `bot/work_item_status.py` | + status icons; old button helper deleted in Task 9 |
| `bot/main.py`, `bot/config.py`, `docker-compose.yml`, `pyproject.toml`, `uv.lock` | Redis storage, router order, `/menu` command |
| `app/modules/visits/work_items_schemas.py`, `work_items_service.py` | `plate_number`, `make_model` on `/work-items/mine` |
| `tests/bot/helpers.py` (new), `tests/bot/conftest.py` (new) | event mocks; import `bot.main` so every screen/step is registered |

---

### Task 1: `/work-items/mine` returns the vehicle

**Files:**
- Modify: `app/modules/visits/work_items_schemas.py:48-56`
- Modify: `app/modules/visits/work_items_service.py:169-175`
- Test: `tests/modules/visits/test_work_items.py`

**Interfaces:**
- Produces: each item of `GET /work-items/mine` has `plate_number: str | None`, `make_model: str | None` (`"Toyota Camry"`). Bot code (`api.list_my_work_items()`) reads them in Task 7.

- [ ] **Step 1: Write the failing test** — append to `tests/modules/visits/test_work_items.py`:

```python
async def test_list_mine_includes_vehicle_plate_and_make_model(session):
    from app.modules.visits.work_items_schemas import WorkItemMineOut

    admin, mechanic_a, mechanic_b, item = await _setup_visit_with_mechanic(session)

    mine = await WorkItemService(session).list_mine(mechanic_a)

    out = WorkItemMineOut.model_validate(mine[0])
    assert out.plate_number == "А123"
    assert out.make_model == "Toyota Camry"
```

- [ ] **Step 2: Run it, expect FAIL**

Run: `docker compose up -d postgres && .venv/bin/pytest tests/modules/visits/test_work_items.py::test_list_mine_includes_vehicle_plate_and_make_model -v`
Expected: FAIL — `AttributeError: 'WorkItemMineOut' object has no attribute 'plate_number'`.

- [ ] **Step 3: Implement**

In `work_items_schemas.py`, `WorkItemMineOut` gets two fields after `catalog_item_id`:

```python
    plate_number: str | None = None
    make_model: str | None = None
```

In `work_items_service.py`, ensure `from app.modules.vehicles.models import Vehicle` is imported (add it next to the other model imports if missing), then replace `list_mine` with:

```python
    async def list_mine(self, acting_user: User) -> list[VisitWorkItem]:
        result = await self.session.execute(
            select(VisitWorkItem)
            .where(VisitWorkItem.assigned_mechanic_id == acting_user.id)
            .order_by(VisitWorkItem.created_at, VisitWorkItem.id)
        )
        items = await self._with_names(list(result.scalars()))
        # The mechanic can't read GET /visits/{id}; the bot labels work items by car.
        visit_ids = {i.visit_id for i in items}
        vehicles = {}
        if visit_ids:
            rows = await self.session.execute(
                select(Visit.id, Vehicle.plate_number, Vehicle.make, Vehicle.model)
                .join(Vehicle, Vehicle.id == Visit.vehicle_id)
                .where(Visit.id.in_(visit_ids))
            )
            vehicles = {visit_id: (plate, f"{make} {model}") for visit_id, plate, make, model in rows.all()}
        for item in items:
            item.plate_number, item.make_model = vehicles.get(item.visit_id, (None, None))
        return items
```

- [ ] **Step 4: Run the visits test package, expect PASS**

Run: `.venv/bin/pytest tests/modules/visits -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add app/modules/visits/work_items_schemas.py app/modules/visits/work_items_service.py tests/modules/visits/test_work_items.py
git commit -m "feat(api): include vehicle plate and model in /work-items/mine

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Redis FSM storage

**Files:**
- Modify: `pyproject.toml`, `uv.lock` (via `uv add`)
- Modify: `bot/config.py`
- Modify: `bot/main.py` (add `build_storage`, use it in `main`)
- Modify: `docker-compose.yml`
- Test: `tests/bot/test_main.py`

**Interfaces:**
- Produces: `bot.main.build_storage(redis_url: str) -> BaseStorage`; `bot.config.settings.redis_url: str`.

- [ ] **Step 1: Add the dependency**

Run: `uv add 'redis>=5' && uv sync --extra dev`
Expected: `pyproject.toml` dependencies include `"redis>=5"`, `uv.lock` updated, `.venv/bin/python -c "import redis"` succeeds.

- [ ] **Step 2: Write the failing tests** — append to `tests/bot/test_main.py`:

```python
async def test_build_storage_without_url_is_in_memory():
    from aiogram.fsm.storage.memory import MemoryStorage

    from bot.main import build_storage

    assert isinstance(build_storage(""), MemoryStorage)


async def test_build_storage_with_url_is_redis_with_30_day_ttl():
    from datetime import timedelta

    from aiogram.fsm.storage.redis import RedisStorage

    from bot.main import build_storage

    storage = build_storage("redis://localhost:6379/0")  # from_url does not connect

    assert isinstance(storage, RedisStorage)
    assert storage.state_ttl == timedelta(days=30)
    assert storage.data_ttl == timedelta(days=30)
    await storage.close()
```

- [ ] **Step 3: Run, expect FAIL**

Run: `.venv/bin/pytest tests/bot/test_main.py -k build_storage -v`
Expected: FAIL — `ImportError: cannot import name 'build_storage'`.

- [ ] **Step 4: Implement**

`bot/config.py` — add a field after `api_base_url`:

```python
    # Empty: in-memory FSM (tests, local runs). docker-compose sets redis://redis:6379/0.
    redis_url: str = ""
```

`bot/main.py` — add imports and the function (place it above `main`), then use it:

```python
from datetime import timedelta

from aiogram.fsm.storage.base import BaseStorage
from aiogram.fsm.storage.redis import RedisStorage

# Abandoned stacks and wizards expire instead of piling up in Redis.
STORAGE_TTL = timedelta(days=30)


def build_storage(redis_url: str) -> BaseStorage:
    """Redis keeps screen stacks and wizards across restarts; memory is for tests and local runs."""
    if not redis_url:
        return MemoryStorage()
    return RedisStorage.from_url(redis_url, state_ttl=STORAGE_TTL, data_ttl=STORAGE_TTL)
```

In `main()` replace `dp = Dispatcher(storage=MemoryStorage())` with:

```python
    dp = Dispatcher(storage=build_storage(settings.redis_url))
```

`docker-compose.yml` — add a service after `postgres`:

```yaml
  redis:
    image: redis:7-alpine
    command: ["redis-server", "--appendonly", "yes"]
    volumes:
      - redisdata:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 2s
      retries: 30
    restart: unless-stopped
```

In the `bot` service add `REDIS_URL: redis://redis:6379/0` under `environment`, and under `depends_on` add:

```yaml
      redis:
        condition: service_healthy
```

Add `redisdata:` under the top-level `volumes:`.

- [ ] **Step 5: Run, expect PASS; validate compose**

Run: `.venv/bin/pytest tests/bot/test_main.py -v && docker compose config -q`
Expected: tests pass; `docker compose config` prints nothing (valid).

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock bot/config.py bot/main.py docker-compose.yml tests/bot/test_main.py
git commit -m "feat(bot): keep FSM state in Redis so restarts don't drop wizards

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Screen stack core (`bot/nav.py`)

**Files:**
- Create: `bot/nav.py`
- Create: `tests/bot/helpers.py`, `tests/bot/conftest.py`
- Modify: `bot/main.py` (`setup_routers`: include `nav.router` right after `menu.router`)
- Test: `tests/bot/test_nav.py`

**Interfaces:**
- Produces (used by every later task):
  - `nav.screen(name: str, params: tuple[str, ...] = ())` — decorator registering `async def render(api, user: dict, args: dict) -> tuple[str, InlineKeyboardMarkup]`.
  - `nav.go_data(name: str, *ids: str) -> str` — `"go:<name>[:<enc id>...]"`.
  - `nav.MENU = "menu"`, `nav.BACK = "back"`, `nav.HOME = "home"`, `nav.NAV_STACK`, `nav.NAV_MSG`.
  - `async nav.push(event, state, api, user, name: str, args: dict, notice: str | None = None) -> bool`
  - `async nav.refresh(event, state, api, user, notice: str | None = None) -> bool`
  - `async nav.replace_top(event, state, api, user, args: dict) -> bool`
  - `async nav.pop(event, state, api, user, notice: str | None = None) -> None`
  - `async nav.home(event, state, api, user, notice: str | None = None) -> bool`
  - `async nav.present(event, state, text: str, markup: InlineKeyboardMarkup | None) -> None`
  - `async nav.top_args(callback, state, name: str) -> dict | None`
  - `async nav.clear_wizard(state) -> None`
  - `event` is `aiogram.types.Message | CallbackQuery`.
- Test helpers (`tests/bot/helpers.py`): `MASTER`, `ADMIN`, `MECHANIC`, `fsm_context()`, `make_message(text=None, message_id=5)`, `make_callback(data, message_id=5)`, `buttons(markup)`, `shown(event)`, `on_screens(state, *screens, msg_id=5)`.

- [ ] **Step 1: Create test helpers**

`tests/bot/conftest.py`:

```python
# Importing the bot registers every screen and wizard step (module-level decorators).
import bot.main  # noqa: F401
```

`tests/bot/helpers.py`:

```python
"""Event mocks for screen/wizard tests.

`MagicMock(spec=...)` passes isinstance checks (nav tells callbacks from
messages that way); aiogram's methods return awaitables rather than
coroutines, so each one used is replaced with an AsyncMock explicitly.
"""
from unittest.mock import AsyncMock, MagicMock

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

MASTER = {"id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "role": "master"}
ADMIN = {"id": "cccccccc-cccc-cccc-cccc-cccccccccccc", "role": "admin"}
MECHANIC = {"id": "dddddddd-dddd-dddd-dddd-dddddddddddd", "role": "mechanic"}


def fsm_context() -> FSMContext:
    return FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=1, user_id=1))


def make_message(text: str | None = None, message_id: int = 5) -> MagicMock:
    message = MagicMock(spec=Message)
    message.text = text
    message.message_id = message_id
    message.chat = MagicMock(id=1)
    message.bot = AsyncMock()
    # A message the bot sends gets id = this id + 100.
    message.answer = AsyncMock(return_value=MagicMock(message_id=message_id + 100))
    message.edit_text = AsyncMock()
    message.answer_document = AsyncMock()
    return message


def make_callback(data: str, message_id: int = 5) -> MagicMock:
    callback = MagicMock(spec=CallbackQuery)
    callback.data = data
    callback.message = make_message(message_id=message_id)
    callback.bot = callback.message.bot
    callback.answer = AsyncMock()
    return callback


def buttons(markup: InlineKeyboardMarkup) -> list[tuple[str, str]]:
    return [(b.text, b.callback_data) for row in markup.inline_keyboard for b in row]


def shown(event) -> tuple[str, InlineKeyboardMarkup]:
    """Text and markup last drawn for `event`: an edit for a callback, a new message otherwise."""
    call = event.message.edit_text.await_args if isinstance(event, CallbackQuery) else event.answer.await_args
    return call.args[0], call.kwargs["reply_markup"]


async def on_screens(state: FSMContext, *screens: tuple[str, dict], msg_id: int = 5) -> None:
    """Put the user on a stack: menu + `screens`, live message `msg_id`."""
    await state.update_data(nav_stack=[["menu", {}], *[[name, args] for name, args in screens]], nav_msg_id=msg_id)
```

- [ ] **Step 2: Write the failing tests** — `tests/bot/test_nav.py`:

```python
from unittest.mock import AsyncMock

from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.state import State, StatesGroup
from aiogram.methods import EditMessageText
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot import nav
from bot.api_client import ApiNotFound
from bot.callback_ids import encode_id
from tests.bot.helpers import MASTER, buttons, fsm_context, make_callback, make_message, on_screens, shown

A = "11111111-1111-1111-1111-111111111111"
B = "22222222-2222-2222-2222-222222222222"


@nav.screen("t_item", params=("item_id",))
async def _render_item(api, user, args):
    return f"item {args['item_id']}", InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="x", callback_data="x")]])


@nav.screen("t_broken")
async def _render_broken(api, user, args):
    raise ApiNotFound("Не найдено")


class _Wiz(StatesGroup):
    step = State()


def _bad_request(text: str) -> TelegramBadRequest:
    return TelegramBadRequest(method=EditMessageText(text="x"), message=text)


async def _stack(state):
    return (await state.get_data())["nav_stack"]


async def test_go_pushes_screen_and_edits_pressed_message():
    state = fsm_context()
    await on_screens(state)
    callback = make_callback(f"go:t_item:{encode_id(A)}")

    await nav.go_callback(callback, state, api=AsyncMock(), user=MASTER)

    assert await _stack(state) == [["menu", {}], ["t_item", {"item_id": A}]]
    text, markup = shown(callback)
    assert text == f"item {A}"
    assert buttons(markup)[-2:] == [("‹ Назад", "back"), ("🏠 Меню", "home")]
    callback.answer.assert_awaited_once_with()


async def test_go_data_encodes_ids():
    assert nav.go_data("t_item", A) == f"go:t_item:{encode_id(A)}"
    assert nav.go_data("active_visits") == "go:active_visits"


async def test_back_pops_to_previous_screen():
    state = fsm_context()
    await on_screens(state, ("t_item", {"item_id": A}), ("t_item", {"item_id": B}))
    callback = make_callback("back")

    await nav.back_callback(callback, state, api=AsyncMock(), user=MASTER)

    assert await _stack(state) == [["menu", {}], ["t_item", {"item_id": A}]]
    assert shown(callback)[0] == f"item {A}"


async def test_back_without_stack_goes_to_menu():
    state = fsm_context()  # e.g. storage lost: no nav data at all

    await nav.back_callback(make_callback("back"), state, api=AsyncMock(), user=MASTER)

    assert await _stack(state) == [["menu", {}]]


async def test_home_resets_stack_to_menu():
    state = fsm_context()
    await on_screens(state, ("t_item", {"item_id": A}), ("t_item", {"item_id": B}))

    await nav.home_callback(make_callback("home"), state, api=AsyncMock(), user=MASTER)

    assert await _stack(state) == [["menu", {}]]


async def test_render_error_alerts_and_keeps_stack():
    state = fsm_context()
    await on_screens(state, ("t_item", {"item_id": A}))
    callback = make_callback("go:t_broken")

    await nav.go_callback(callback, state, api=AsyncMock(), user=MASTER)

    callback.answer.assert_awaited_once_with("Не найдено", show_alert=True)
    callback.message.edit_text.assert_not_awaited()
    assert await _stack(state) == [["menu", {}], ["t_item", {"item_id": A}]]


async def test_back_into_broken_screen_shows_menu_with_error():
    state = fsm_context()
    await on_screens(state, ("t_broken", {}), ("t_item", {"item_id": A}))
    callback = make_callback("back")

    await nav.back_callback(callback, state, api=AsyncMock(), user=MASTER)

    assert await _stack(state) == [["menu", {}]]
    assert shown(callback)[0].startswith("Не найдено\n\n")


async def test_text_message_sends_new_message_and_strips_previous_live_one():
    state = fsm_context()
    await on_screens(state, msg_id=5)
    message = make_message("query", message_id=9)

    await nav.push(message, state, AsyncMock(), MASTER, "t_item", {"item_id": A})

    assert shown(message)[0] == f"item {A}"
    message.bot.edit_message_reply_markup.assert_awaited_once_with(chat_id=1, message_id=5, reply_markup=None)
    assert (await state.get_data())["nav_msg_id"] == 109


async def test_not_modified_is_ignored():
    state = fsm_context()
    await on_screens(state, ("t_item", {"item_id": A}))
    callback = make_callback("x")
    callback.message.edit_text.side_effect = _bad_request("Bad Request: message is not modified")

    await nav.refresh(callback, state, AsyncMock(), MASTER)

    callback.message.answer.assert_not_awaited()
    callback.answer.assert_awaited_once_with()


async def test_failed_edit_sends_new_message():
    state = fsm_context()
    await on_screens(state, ("t_item", {"item_id": A}))
    callback = make_callback("x")
    callback.message.edit_text.side_effect = _bad_request("Bad Request: message to edit not found")

    await nav.refresh(callback, state, AsyncMock(), MASTER)

    callback.message.answer.assert_awaited_once()
    assert (await state.get_data())["nav_msg_id"] == 105


async def test_failed_strip_of_old_buttons_is_ignored():
    state = fsm_context()
    await on_screens(state, msg_id=5)
    message = make_message("q", message_id=9)
    message.bot.edit_message_reply_markup.side_effect = _bad_request("Bad Request: message can't be edited")

    await nav.push(message, state, AsyncMock(), MASTER, "t_item", {"item_id": A})

    assert (await state.get_data())["nav_msg_id"] == 109


async def test_notice_goes_above_screen_text():
    state = fsm_context()
    await on_screens(state, ("t_item", {"item_id": A}))
    callback = make_callback("x")

    await nav.refresh(callback, state, AsyncMock(), MASTER, notice="Готово.")

    assert shown(callback)[0] == f"Готово.\n\nitem {A}"


async def test_replace_top_keeps_depth():
    state = fsm_context()
    await on_screens(state, ("t_item", {"item_id": A}))

    await nav.replace_top(make_callback("x"), state, AsyncMock(), MASTER, {"item_id": B})

    assert await _stack(state) == [["menu", {}], ["t_item", {"item_id": B}]]


async def test_top_args_on_live_top_screen():
    state = fsm_context()
    await on_screens(state, ("t_item", {"item_id": A}), msg_id=5)

    assert await nav.top_args(make_callback("act:x", message_id=5), state, "t_item") == {"item_id": A}


async def test_top_args_wrong_screen_is_stale():
    state = fsm_context()
    await on_screens(state, ("t_item", {"item_id": A}), msg_id=5)
    callback = make_callback("act:x", message_id=5)

    assert await nav.top_args(callback, state, "visit") is None
    callback.answer.assert_awaited_once_with("Кнопка устарела — начните действие заново.")


async def test_top_args_on_old_message_is_stale():
    state = fsm_context()
    await on_screens(state, ("t_item", {"item_id": A}), msg_id=5)
    callback = make_callback("act:x", message_id=4)

    assert await nav.top_args(callback, state, "t_item") is None
    callback.answer.assert_awaited_once_with("Кнопка устарела — начните действие заново.")


async def test_clear_wizard_keeps_stack_and_live_message():
    state = fsm_context()
    await on_screens(state, ("t_item", {"item_id": A}), msg_id=5)
    await state.set_state(_Wiz.step)
    await state.update_data(visit_id="v1")

    await nav.clear_wizard(state)

    assert await state.get_state() is None
    assert await state.get_data() == {"nav_stack": [["menu", {}], ["t_item", {"item_id": A}]], "nav_msg_id": 5}


async def test_go_to_unknown_screen_is_stale():
    state = fsm_context()
    callback = make_callback("go:nope")

    await nav.go_callback(callback, state, api=AsyncMock(), user=MASTER)

    callback.answer.assert_awaited_once_with("Кнопка устарела — начните действие заново.")


async def test_go_drops_an_unfinished_wizard():
    state = fsm_context()
    await on_screens(state)
    await state.set_state(_Wiz.step)
    await state.update_data(visit_id="v1")

    await nav.go_callback(make_callback(f"go:t_item:{encode_id(A)}"), state, api=AsyncMock(), user=MASTER)

    assert await state.get_state() is None
    assert "visit_id" not in await state.get_data()
```

The menu screen is registered in Task 5. Until then, add this at the top of `tests/bot/test_nav.py` (below the imports) so `back/home` tests can render it, and leave it in place afterwards (it is a no-op once the real menu exists):

```python
if nav.MENU not in nav.SCREENS:
    @nav.screen(nav.MENU)
    async def _placeholder_menu(api, user, args):
        return "menu", InlineKeyboardMarkup(inline_keyboard=[])
```

- [ ] **Step 3: Run, expect FAIL**

Run: `.venv/bin/pytest tests/bot/test_nav.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'bot.nav'`.

- [ ] **Step 4: Implement `bot/nav.py`**

```python
"""Screen stack: one live message that screens redraw in place.

A screen is a render function `(api, user, args) -> (text, markup)` registered
with @screen. FSM data holds the stack (`nav_stack`: [[name, args], ...], the
menu always at the bottom) and the live message id (`nav_msg_id`), so with
RedisStorage both survive restarts. A callback redraws the message it came
from; a text message gets a new message, and the previous live message loses
its buttons so no stale ones stay in the chat.
"""
import logging
from dataclasses import dataclass
from typing import Awaitable, Callable

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.api_client import ApiClient, ApiError
from bot.callback_ids import decode_id, encode_id
from bot.texts import STALE_BUTTON

logger = logging.getLogger(__name__)

router = Router()

NAV_STACK = "nav_stack"
NAV_MSG = "nav_msg_id"
MENU = "menu"
BACK = "back"
HOME = "home"

Event = Message | CallbackQuery
Rendered = tuple[str, InlineKeyboardMarkup]
Render = Callable[[ApiClient, dict, dict], Awaitable[Rendered]]


@dataclass(frozen=True)
class Screen:
    render: Render
    params: tuple[str, ...]


SCREENS: dict[str, Screen] = {}


def screen(name: str, params: tuple[str, ...] = ()):
    """Register a render function; `params` name the UUIDs a `go:` button carries, in order."""

    def decorator(render: Render) -> Render:
        SCREENS[name] = Screen(render, params)
        return render

    return decorator


def go_data(name: str, *ids: str) -> str:
    return ":".join(["go", name, *(encode_id(i) for i in ids)])


def _base_stack() -> list:
    return [[MENU, {}]]


async def _get_stack(state: FSMContext) -> list:
    return (await state.get_data()).get(NAV_STACK) or _base_stack()


async def clear_wizard(state: FSMContext) -> None:
    """Drop wizard state and data; keep the screen stack and the live message."""
    data = await state.get_data()
    await state.set_state(None)
    await state.set_data({key: data[key] for key in (NAV_STACK, NAV_MSG) if key in data})


async def present(event: Event, state: FSMContext, text: str, markup: InlineKeyboardMarkup | None) -> None:
    """Show `text` as the live message: edit the pressed message, or send a new one for a text message."""
    if isinstance(event, CallbackQuery):
        message = event.message
        try:
            await message.edit_text(text, reply_markup=markup)
            live_id = message.message_id
        except TelegramBadRequest as e:
            if "message is not modified" in e.message:
                live_id = message.message_id
            else:
                live_id = (await message.answer(text, reply_markup=markup)).message_id
    else:
        message = event
        live_id = (await message.answer(text, reply_markup=markup)).message_id
    previous = (await state.get_data()).get(NAV_MSG)
    if previous is not None and previous != live_id:
        try:
            await message.bot.edit_message_reply_markup(chat_id=message.chat.id, message_id=previous, reply_markup=None)
        except TelegramAPIError:
            logger.debug("Could not remove buttons from message %s", previous)
    await state.update_data(**{NAV_MSG: live_id})


async def _render(api: ApiClient, user: dict, stack: list, notice: str | None) -> Rendered:
    name, args = stack[-1]
    text, markup = await SCREENS[name].render(api, user, args)
    if len(stack) > 1:
        nav_row = [
            InlineKeyboardButton(text="‹ Назад", callback_data=BACK),
            InlineKeyboardButton(text="🏠 Меню", callback_data=HOME),
        ]
        markup = InlineKeyboardMarkup(inline_keyboard=[*markup.inline_keyboard, nav_row])
    if notice:
        text = f"{notice}\n\n{text}"
    return text, markup


async def _commit(event: Event, state: FSMContext, stack: list, rendered: Rendered) -> None:
    await present(event, state, *rendered)
    await state.update_data(**{NAV_STACK: stack})
    if isinstance(event, CallbackQuery):
        await event.answer()


async def _show(event: Event, state: FSMContext, api: ApiClient, user: dict, stack: list, notice: str | None = None) -> bool:
    """Render the top of `stack`; the stack is saved only if rendering succeeded."""
    try:
        rendered = await _render(api, user, stack, notice)
    except ApiError as e:
        if isinstance(event, CallbackQuery):
            await event.answer(e.message, show_alert=True)
        else:
            await event.answer(e.message)
        return False
    await _commit(event, state, stack, rendered)
    return True


async def push(event: Event, state: FSMContext, api: ApiClient, user: dict, name: str, args: dict, notice: str | None = None) -> bool:
    return await _show(event, state, api, user, [*await _get_stack(state), [name, args]], notice)


async def refresh(event: Event, state: FSMContext, api: ApiClient, user: dict, notice: str | None = None) -> bool:
    return await _show(event, state, api, user, await _get_stack(state), notice)


async def replace_top(event: Event, state: FSMContext, api: ApiClient, user: dict, args: dict) -> bool:
    stack = await _get_stack(state)
    return await _show(event, state, api, user, [*stack[:-1], [stack[-1][0], args]])


async def home(event: Event, state: FSMContext, api: ApiClient, user: dict, notice: str | None = None) -> bool:
    return await _show(event, state, api, user, _base_stack(), notice)


async def pop(event: Event, state: FSMContext, api: ApiClient, user: dict, notice: str | None = None) -> None:
    """Back one screen; if that screen can't be shown any more, fall back to the menu with the error on top."""
    stack = (await _get_stack(state))[:-1] or _base_stack()
    try:
        rendered = await _render(api, user, stack, notice)
    except ApiError as e:
        stack = _base_stack()
        rendered = await _render(api, user, stack, e.message)
    await _commit(event, state, stack, rendered)


async def top_args(callback: CallbackQuery, state: FSMContext, name: str) -> dict | None:
    """Args of the top screen for an `act:` button.

    The button carries no ids, so it is honoured only on the live message while
    `name` is on top; otherwise it would act on whatever screen is there now.
    """
    data = await state.get_data()
    stack = data.get(NAV_STACK) or _base_stack()
    if stack[-1][0] != name or data.get(NAV_MSG) != callback.message.message_id:
        await callback.answer(STALE_BUTTON)
        return None
    return stack[-1][1]


@router.callback_query(F.data.startswith("go:"))
async def go_callback(callback: CallbackQuery, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    _, name, *encoded = callback.data.split(":")
    spec = SCREENS.get(name)
    if spec is None or len(encoded) != len(spec.params):
        await callback.answer(STALE_BUTTON)
        return
    await clear_wizard(state)
    await push(callback, state, api, user, name, dict(zip(spec.params, map(decode_id, encoded))))


@router.callback_query(F.data == BACK)
async def back_callback(callback: CallbackQuery, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    await clear_wizard(state)
    await pop(callback, state, api, user)


@router.callback_query(F.data == HOME)
async def home_callback(callback: CallbackQuery, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    await clear_wizard(state)
    await home(callback, state, api, user)
```

In `bot/main.py`: add `from bot import nav` and in `setup_routers` insert `dp.include_router(nav.router)` right after `dp.include_router(menu.router)`.

- [ ] **Step 5: Run, expect PASS; run the whole bot suite**

Run: `.venv/bin/pytest tests/bot -q`
Expected: all pass (old tests are untouched by this task).

- [ ] **Step 6: Commit**

```bash
git add bot/nav.py bot/main.py tests/bot/helpers.py tests/bot/conftest.py tests/bot/test_nav.py
git commit -m "feat(bot): screen stack core with live-message redraw

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Wizard core (`bot/wizard.py`)

**Files:**
- Create: `bot/wizard.py`
- Modify: `bot/main.py` (include `wizard.router` right after `nav.router`)
- Test: `tests/bot/test_wizard.py`

**Interfaces:**
- Consumes: `nav.present`, `nav.clear_wizard`, `nav.refresh` (Task 3).
- Produces:
  - `wizard.step(*states: State)` — decorator registering `async def prompt(state, api, user) -> tuple[str, InlineKeyboardMarkup | None]`.
  - `async wizard.start(event, state, api, user, name: str, first: State, **data) -> None`
  - `async wizard.goto(event, state, api, user, target: State, *, commit: bool = False) -> None`
  - `async wizard.reprompt(event, state, api, user, error: str) -> None`
  - `async wizard.name(state) -> str | None`
  - `async wizard.finish(state) -> None`
  - callback data `wizard.WIZ_BACK = "wiz_back"`, `wizard.WIZ_CANCEL = "wiz_cancel"`.

- [ ] **Step 1: Write the failing tests** — `tests/bot/test_wizard.py`:

```python
from unittest.mock import AsyncMock

from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot import nav, wizard
from tests.bot.helpers import MASTER, buttons, fsm_context, make_callback, make_message, on_screens, shown


class _Demo(StatesGroup):
    first = State()
    second = State()
    third = State()


@wizard.step(_Demo.first)
async def _first(state, api, user):
    return "first?", None


@wizard.step(_Demo.second)
async def _second(state, api, user):
    builder = InlineKeyboardBuilder()
    builder.button(text="pick", callback_data="pick")
    return "second?", builder.as_markup()


@wizard.step(_Demo.third)
async def _third(state, api, user):
    return "third?", None


@nav.screen("w_source")
async def _source(api, user, args):
    return "source", InlineKeyboardMarkup(inline_keyboard=[])


async def _started(state):
    await on_screens(state, ("w_source", {}))
    await wizard.start(make_callback("x"), state, AsyncMock(), MASTER, "demo", _Demo.first, visit_id="v1")


async def test_start_shows_first_prompt_with_controls_and_keeps_stack():
    state = fsm_context()
    await on_screens(state, ("w_source", {}))
    await state.update_data(stale="old wizard")
    callback = make_callback("x")

    await wizard.start(callback, state, AsyncMock(), MASTER, "demo", _Demo.first, visit_id="v1")

    text, markup = shown(callback)
    assert text == "first?"
    assert buttons(markup) == [("‹ Назад", "wiz_back"), ("✖ Отмена", "wiz_cancel")]
    assert await state.get_state() == _Demo.first.state
    data = await state.get_data()
    assert data["visit_id"] == "v1" and data["wiz_name"] == "demo" and data["wiz_steps"] == []
    assert "stale" not in data
    assert data["nav_stack"] == [["menu", {}], ["w_source", {}]]
    assert await wizard.name(state) == "demo"


async def test_step_choices_come_before_controls():
    state = fsm_context()
    await _started(state)
    message = make_message("answer")

    await wizard.goto(message, state, AsyncMock(), MASTER, _Demo.second)

    assert buttons(shown(message)[1]) == [("pick", "pick"), ("‹ Назад", "wiz_back"), ("✖ Отмена", "wiz_cancel")]


async def test_back_returns_to_previous_step_and_keeps_data():
    state = fsm_context()
    await _started(state)
    await wizard.goto(make_message("a"), state, AsyncMock(), MASTER, _Demo.second)
    await wizard.goto(make_message("b"), state, AsyncMock(), MASTER, _Demo.third)
    callback = make_callback("wiz_back")

    await wizard.back_callback(callback, state, api=AsyncMock(), user=MASTER)

    assert await state.get_state() == _Demo.second.state
    assert shown(callback)[0] == "second?"
    assert (await state.get_data())["visit_id"] == "v1"


async def test_back_on_first_step_cancels_to_source_screen():
    state = fsm_context()
    await _started(state)
    callback = make_callback("wiz_back")

    await wizard.back_callback(callback, state, api=AsyncMock(), user=MASTER)

    assert await state.get_state() is None
    assert shown(callback)[0] == "source"


async def test_cancel_drops_wizard_data_and_redraws_source():
    state = fsm_context()
    await _started(state)
    await wizard.goto(make_message("a"), state, AsyncMock(), MASTER, _Demo.second)
    callback = make_callback("wiz_cancel")

    await wizard.cancel_callback(callback, state, api=AsyncMock(), user=MASTER)

    assert await state.get_state() is None
    assert "visit_id" not in await state.get_data()
    assert shown(callback)[0] == "source"


async def test_commit_drops_history_so_back_cancels():
    state = fsm_context()
    await _started(state)
    await wizard.goto(make_message("a"), state, AsyncMock(), MASTER, _Demo.second, commit=True)
    callback = make_callback("wiz_back")

    await wizard.back_callback(callback, state, api=AsyncMock(), user=MASTER)

    assert await state.get_state() is None


async def test_goto_same_step_does_not_grow_history():
    state = fsm_context()
    await _started(state)
    await wizard.goto(make_message("a"), state, AsyncMock(), MASTER, _Demo.second)
    await wizard.goto(make_message("b"), state, AsyncMock(), MASTER, _Demo.second)

    assert (await state.get_data())["wiz_steps"] == [_Demo.first.state]


async def test_reprompt_puts_error_above_prompt_in_new_message():
    state = fsm_context()
    await _started(state)
    message = make_message("bad")

    await wizard.reprompt(message, state, AsyncMock(), MASTER, "Введите число.")

    assert shown(message)[0] == "Введите число.\n\nfirst?"


async def test_finish_keeps_stack():
    state = fsm_context()
    await _started(state)

    await wizard.finish(state)

    assert await state.get_state() is None
    assert set(await state.get_data()) == {"nav_stack", "nav_msg_id"}


async def test_back_without_wizard_is_stale():
    state = fsm_context()
    callback = make_callback("wiz_back")

    await wizard.back_callback(callback, state, api=AsyncMock(), user=MASTER)

    callback.answer.assert_awaited_once_with("Кнопка устарела — начните действие заново.")
```

- [ ] **Step 2: Run, expect FAIL**

Run: `.venv/bin/pytest tests/bot/test_wizard.py -q`
Expected: FAIL — `ImportError: cannot import name 'wizard' from 'bot'`.

- [ ] **Step 3: Implement `bot/wizard.py`**

```python
"""Wizards: multi-step input on FSM states, with step-back and cancel.

Each step registers a prompt `(state, api, user) -> (text, markup | None)`.
`wiz_steps` in FSM data lists the steps behind the current one, so
"‹ Назад" re-shows the previous prompt even in branching wizards, keeping
what was typed. "✖ Отмена" drops the wizard and redraws the screen it was
started from (the top of the screen stack — wizards never push screens).
"""
from typing import Awaitable, Callable

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from bot import nav
from bot.api_client import ApiClient
from bot.texts import STALE_BUTTON

router = Router()

WIZ_NAME = "wiz_name"
WIZ_STEPS = "wiz_steps"
WIZ_BACK = "wiz_back"
WIZ_CANCEL = "wiz_cancel"

Prompt = Callable[[FSMContext, ApiClient, dict], Awaitable[tuple[str, InlineKeyboardMarkup | None]]]
PROMPTS: dict[str, Prompt] = {}


def step(*states: State):
    """Register the prompt shown on entering any of `states`."""

    def decorator(prompt: Prompt) -> Prompt:
        for s in states:
            PROMPTS[s.state] = prompt
        return prompt

    return decorator


async def _show(event: nav.Event, state: FSMContext, api: ApiClient, user: dict, error: str | None = None) -> None:
    text, markup = await PROMPTS[await state.get_state()](state, api, user)
    if error:
        text = f"{error}\n\n{text}"
    controls = [
        InlineKeyboardButton(text="‹ Назад", callback_data=WIZ_BACK),
        InlineKeyboardButton(text="✖ Отмена", callback_data=WIZ_CANCEL),
    ]
    rows = markup.inline_keyboard if markup else []
    await nav.present(event, state, text, InlineKeyboardMarkup(inline_keyboard=[*rows, controls]))
    if isinstance(event, CallbackQuery):
        await event.answer()


async def start(event: nav.Event, state: FSMContext, api: ApiClient, user: dict, name: str, first: State, **data) -> None:
    await nav.clear_wizard(state)
    await state.update_data(**{WIZ_NAME: name, WIZ_STEPS: []}, **data)
    await state.set_state(first)
    await _show(event, state, api, user)


async def goto(event: nav.Event, state: FSMContext, api: ApiClient, user: dict, target: State, *, commit: bool = False) -> None:
    """Move to `target`. After a side effect (an entity was created) pass commit=True:
    the history is dropped, so "‹ Назад" can't lead back into repeating it."""
    current = await state.get_state()
    steps = [] if commit else list((await state.get_data()).get(WIZ_STEPS, []))
    if not commit and current is not None and current != target.state:
        steps.append(current)
    await state.update_data(**{WIZ_STEPS: steps})
    await state.set_state(target)
    await _show(event, state, api, user)


async def reprompt(event: nav.Event, state: FSMContext, api: ApiClient, user: dict, error: str) -> None:
    await _show(event, state, api, user, error=error)


async def name(state: FSMContext) -> str | None:
    return (await state.get_data()).get(WIZ_NAME)


async def finish(state: FSMContext) -> None:
    await nav.clear_wizard(state)


@router.callback_query(F.data == WIZ_CANCEL)
async def cancel_callback(callback: CallbackQuery, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    if await state.get_state() is None:
        await callback.answer(STALE_BUTTON)
        return
    await nav.clear_wizard(state)
    await nav.refresh(callback, state, api, user)


@router.callback_query(F.data == WIZ_BACK)
async def back_callback(callback: CallbackQuery, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    if await state.get_state() is None:
        await callback.answer(STALE_BUTTON)
        return
    steps = list((await state.get_data()).get(WIZ_STEPS, []))
    if not steps:
        await cancel_callback(callback, state, api, user)
        return
    previous = steps.pop()
    await state.update_data(**{WIZ_STEPS: steps})
    await state.set_state(previous)
    await _show(callback, state, api, user)
```

In `bot/main.py`: `from bot import nav, wizard`; insert `dp.include_router(wizard.router)` right after `dp.include_router(nav.router)`.

- [ ] **Step 4: Run, expect PASS**

Run: `.venv/bin/pytest tests/bot -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add bot/wizard.py bot/main.py tests/bot/test_wizard.py
git commit -m "feat(bot): wizard core with step-back and cancel to source screen

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Inline menu replaces the reply keyboard

**Files:**
- Create: `bot/actions.py`
- Rewrite: `bot/handlers/menu.py`, `bot/handlers/start.py`
- Delete: `bot/keyboards.py`, `tests/bot/test_keyboards.py`
- Modify: `bot/main.py` (`BOT_COMMANDS` gets `menu`)
- Rewrite: `tests/bot/test_start_handler.py`
- Modify: `tests/bot/test_routing.py`

**Interfaces:**
- Consumes: `nav.screen`, `nav.home`, `nav.refresh`, `nav.clear_wizard`, `nav.go_data`.
- Produces: `bot/actions.py` constants used by Tasks 6–11; screen `menu`; `menu.LEGACY_MENU_TEXTS`, `menu.KEYBOARD_REMOVED`, `start.WELCOME`.

The old menu entry functions (`navigation.show_active_visits`, `visits.start_new_visit`, `search.start_search`, `consent.start_paper_consent`, `admin.start_new_staff`, `mechanic.show_my_work_items`) stay in their modules, unreferenced, until their own tasks replace them. Until then the new menu's buttons for those features answer "Кнопка устарела" — expected mid-branch.

- [ ] **Step 1: Create `bot/actions.py`**

```python
"""callback_data shared by the screen that draws a button and the handler that runs it.

`act:` buttons carry no entity ids: the handler takes them from the top
screen's args (`nav.top_args`). `wiz:` buttons start a wizard from the menu.
"""
NEW_VISIT = "wiz:new_visit"
PAPER_CONSENT = "wiz:paper_consent"
NEW_STAFF = "wiz:new_staff"

ADD_WORK = "act:add_work"
ADD_PART = "act:add_part"
APPROVE = "act:approve"
PDF = "act:pdf"
NEW_VISIT_FOR = "act:new_visit_for"
VISIT_STATUS = "act:vstatus"  # + ":<visit status>"
WORK_STATUS = "act:wstatus"  # + ":<work item status>"
REASSIGN = "act:reassign"  # + ":<encoded mechanic id>" or ":none"
SEARCH_PAGE = "act:spage"  # + ":<page>"
```

- [ ] **Step 2: Write the failing tests**

Replace `tests/bot/test_start_handler.py` with:

```python
from unittest.mock import AsyncMock

from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardRemove

from bot.handlers.menu import KEYBOARD_REMOVED, legacy_menu_text, render_menu
from bot.handlers.start import WELCOME, cmd_cancel, cmd_menu, cmd_start
from bot.main import BOT_COMMANDS
from tests.bot.helpers import ADMIN, MASTER, MECHANIC, buttons, fsm_context, make_message, on_screens, shown


class _Wiz(StatesGroup):
    step = State()


async def test_master_menu():
    text, markup = await render_menu(AsyncMock(), MASTER, {})
    assert text == "Главное меню"
    assert buttons(markup) == [
        ("🆕 Новый заезд", "wiz:new_visit"),
        ("🔧 Заезды в работе", "go:active_visits"),
        ("🔍 Поиск", "go:search"),
        ("📝 Регистрация клиента (бумага)", "wiz:paper_consent"),
    ]


async def test_admin_menu_adds_staff():
    _, markup = await render_menu(AsyncMock(), ADMIN, {})
    assert buttons(markup)[-1] == ("👥 Добавить сотрудника", "wiz:new_staff")
    assert len(buttons(markup)) == 5


async def test_mechanic_menu():
    _, markup = await render_menu(AsyncMock(), MECHANIC, {})
    assert buttons(markup) == [("🧰 Мои работы", "go:my_works"), ("🔍 Поиск", "go:search")]


async def test_start_removes_reply_keyboard_clears_wizard_and_shows_menu():
    state = fsm_context()
    await on_screens(state, ("visit", {"visit_id": "v"}))
    await state.set_state(_Wiz.step)
    message = make_message("/start")

    await cmd_start(message, state, api=AsyncMock(), user=MASTER)

    first = message.answer.await_args_list[0]
    assert first.args[0] == WELCOME
    assert isinstance(first.kwargs["reply_markup"], ReplyKeyboardRemove)
    assert shown(message)[0] == "Главное меню"
    assert await state.get_state() is None
    assert (await state.get_data())["nav_stack"] == [["menu", {}]]


async def test_menu_command_shows_menu():
    state = fsm_context()
    await state.set_state(_Wiz.step)
    message = make_message("/menu")

    await cmd_menu(message, state, api=AsyncMock(), user=MASTER)

    assert shown(message)[0] == "Главное меню"
    assert await state.get_state() is None


async def test_cancel_clears_wizard_and_redraws_current_screen():
    state = fsm_context()
    await on_screens(state)
    await state.set_state(_Wiz.step)
    await state.update_data(visit_id="v1")
    message = make_message("/cancel")

    await cmd_cancel(message, state, api=AsyncMock(), user=MASTER)

    assert await state.get_state() is None
    assert "visit_id" not in await state.get_data()
    assert shown(message)[0] == "Действие отменено.\n\nГлавное меню"


async def test_legacy_reply_keyboard_text_removes_keyboard_and_shows_menu():
    state = fsm_context()
    message = make_message("Новый заезд")

    await legacy_menu_text(message, state, api=AsyncMock(), user=MASTER)

    first = message.answer.await_args_list[0]
    assert first.args[0] == KEYBOARD_REMOVED
    assert isinstance(first.kwargs["reply_markup"], ReplyKeyboardRemove)
    assert shown(message)[0] == "Главное меню"


def test_menu_command_is_registered_in_telegram():
    assert ("menu", "Главное меню") in [(c.command, c.description) for c in BOT_COMMANDS]
```

In `tests/bot/test_routing.py`:
- delete `from bot.keyboards import ALL_MENU_BUTTONS`;
- delete `test_menu_button_wins_over_wizard_state_and_resets_it`, `test_menu_button_wins_over_mileage_state`, `test_every_menu_button_clears_active_wizard`;
- make `RecordingBot` return a real `Message` for sends (nav reads `.message_id` of what it sent):

```python
from aiogram.methods import SendMessage


class RecordingBot(Bot):
    def __init__(self):
        super().__init__(token="42:TEST")
        self.sent: list = []

    async def __call__(self, method, request_timeout=None):
        self.sent.append(method)
        if isinstance(method, SendMessage):
            return Message(
                message_id=100 + len(self.sent),
                date=datetime.now(timezone.utc),
                chat=Chat(id=CHAT_ID, type="private"),
                text=method.text,
            )
        return True
```

- append:

```python
async def test_old_reply_keyboard_text_beats_wizard_and_opens_menu(env):
    bot, dp, state, api, user = env
    await state.set_state(NewVisitStates.waiting_for_mileage)
    await state.update_data(client_id="c1", vehicle_id="v1")

    await dp.feed_update(bot, _message("Поиск"), api=api, user=user)

    assert await state.get_state() is None
    assert "Главное меню" in _texts(bot)
    api.search.assert_not_awaited()


async def test_menu_command_beats_wizard(env):
    bot, dp, state, api, user = env
    await state.set_state(AddWorkItemStates.waiting_for_hours_and_rate)

    await dp.feed_update(bot, _message("/menu"), api=api, user=user)

    assert await state.get_state() is None
    assert "Главное меню" in _texts(bot)
```

(`_message("/menu")` needs a command entity for aiogram's `Command` filter — in `_message`, pass `entities=[MessageEntity(type="bot_command", offset=0, length=len(text))] if text.startswith("/") else None` to `Message(...)`, importing `MessageEntity` from `aiogram.types`.)

- [ ] **Step 3: Run, expect FAIL**

Run: `.venv/bin/pytest tests/bot/test_start_handler.py tests/bot/test_routing.py -q`
Expected: FAIL — `ImportError: cannot import name 'KEYBOARD_REMOVED'`.

- [ ] **Step 4: Implement**

Replace `bot/handlers/menu.py` with:

```python
"""The menu screen (bottom of the screen stack) and a temporary handler for
texts of the removed reply keyboard."""
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, ReplyKeyboardRemove
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot import actions, nav
from bot.api_client import ApiClient

router = Router()

_MASTER_ITEMS = [
    ("🆕 Новый заезд", actions.NEW_VISIT),
    ("🔧 Заезды в работе", nav.go_data("active_visits")),
    ("🔍 Поиск", nav.go_data("search")),
    ("📝 Регистрация клиента (бумага)", actions.PAPER_CONSENT),
]
_ADMIN_ITEMS = _MASTER_ITEMS + [("👥 Добавить сотрудника", actions.NEW_STAFF)]
_MECHANIC_ITEMS = [("🧰 Мои работы", nav.go_data("my_works")), ("🔍 Поиск", nav.go_data("search"))]


@nav.screen(nav.MENU)
async def render_menu(api: ApiClient, user: dict, args: dict) -> nav.Rendered:
    items = {"admin": _ADMIN_ITEMS, "mechanic": _MECHANIC_ITEMS}.get(user["role"], _MASTER_ITEMS)
    builder = InlineKeyboardBuilder()
    for text, data in items:
        builder.button(text=text, callback_data=data)
    builder.adjust(1)
    return "Главное меню", builder.as_markup()


# Users who still have the old reply keyboard send its button texts as plain
# messages; without this they would turn into search queries.
# TODO(2026-10-25): delete with the rollout grace period over.
LEGACY_MENU_TEXTS = {
    "Новый заезд", "Заезды в работе", "Поиск", "Регистрация клиента (бумага)", "Добавить сотрудника", "Мои работы",
}
KEYBOARD_REMOVED = "Меню теперь в кнопках под сообщением."


@router.message(F.text.in_(LEGACY_MENU_TEXTS))
async def legacy_menu_text(message: Message, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    await nav.clear_wizard(state)
    await message.answer(KEYBOARD_REMOVED, reply_markup=ReplyKeyboardRemove())
    await nav.home(message, state, api, user)
```

Replace `bot/handlers/start.py` with:

```python
from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, ReplyKeyboardRemove

from bot import nav
from bot.api_client import ApiClient

router = Router()

WELCOME = "Добро пожаловать в CRM-бот автосервиса."


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    await nav.clear_wizard(state)
    # Also takes the old reply keyboard away for users who still have it.
    await message.answer(WELCOME, reply_markup=ReplyKeyboardRemove())
    await nav.home(message, state, api, user)


@router.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    await nav.clear_wizard(state)
    await nav.home(message, state, api, user)


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    await nav.clear_wizard(state)
    await nav.refresh(message, state, api, user, notice="Действие отменено.")
```

In `bot/main.py`: add `BotCommand(command="menu", description="Главное меню")` as the second entry of `BOT_COMMANDS`; change the `start` entry description to `"Начать заново"`; update the `setup_routers` comment to:

```python
    # Order matters: start (commands) first so /start, /menu, /cancel win over
    # any wizard; menu holds the temporary handler for old reply-keyboard texts;
    # nav and wizard own go/back/home and wiz_back/wiz_cancel; feature routers
    # follow; search catches all remaining text; fallback answers stale buttons
    # and must stay last.
```

Delete `bot/keyboards.py` and `tests/bot/test_keyboards.py`. Remove the old `_ENTRY_POINTS` loop (it was in the old `menu.py`, now gone) — `grep -rn "keyboards" bot tests` must print nothing.

- [ ] **Step 5: Run, expect PASS**

Run: `.venv/bin/pytest tests/bot -q`
Expected: all pass. (Old handler tests that call `start_new_visit`, `show_active_visits`, etc. directly still pass — those functions still exist.)

- [ ] **Step 6: Commit**

```bash
git add -A bot tests/bot
git commit -m "feat(bot): inline menu screen replaces the reply keyboard; add /menu

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Read-only screens

**Files:**
- Rewrite: `bot/handlers/navigation.py`
- Modify: `bot/main.py` (drop `dp.include_router(navigation.router)`; keep `navigation` in the import list — importing registers its screens)
- Rewrite: `tests/bot/test_navigation_handler.py`

**Interfaces:**
- Consumes: `nav.screen`, `nav.go_data`, `actions.NEW_VISIT_FOR`.
- Produces: screens `active_visits`, `client(client_id)`, `vehicle(vehicle_id)`, `client_visits(client_id)`, `vehicle_visits(vehicle_id)`, `work_history(vehicle_id)`; `navigation.visit_list(result, user_id, title, empty_text, with_date) -> (text, markup)`; `navigation.STAFF_ROLES = {"admin", "master"}`. Buttons point to screen `visit(visit_id)` (Task 7).

- [ ] **Step 1: Write the failing tests** — replace `tests/bot/test_navigation_handler.py` with:

```python
from unittest.mock import AsyncMock

from bot.callback_ids import encode_id
from bot.handlers.navigation import (
    render_active_visits,
    render_client,
    render_client_visits,
    render_vehicle,
    render_vehicle_visits,
    render_work_history,
)
from tests.bot.helpers import ADMIN, MASTER, MECHANIC, buttons

ME = MASTER["id"]
OTHER = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
V1 = "11111111-1111-1111-1111-111111111111"
V2 = "22222222-2222-2222-2222-222222222222"
C1 = "33333333-3333-3333-3333-333333333333"
CAR = "44444444-4444-4444-4444-444444444444"


def _visit(visit_id, master_id, status="in_progress", plate="А123ВС77", client="Иванов Пётр"):
    return {
        "id": visit_id, "status": status, "plate_number": plate, "client_name": client,
        "assigned_master_id": master_id, "created_at": "2026-10-02T07:00:00+00:00",
    }


async def test_active_visits_marks_own_with_star_and_opens_card():
    api = AsyncMock()
    api.list_visits.return_value = {
        "items": [_visit(V1, ME), _visit(V2, OTHER, status="diagnostics", plate="В001ОР50", client="Петрова")],
        "has_more": False,
    }

    text, markup = await render_active_visits(api, MASTER, {})

    api.list_visits.assert_awaited_once_with(active=True)
    assert text == "Заезды в работе (2)"
    assert buttons(markup) == [
        ("⭐ А123ВС77 · Иванов Пётр · Ремонт", f"go:visit:{encode_id(V1)}"),
        ("В001ОР50 · Петрова · Диагностика", f"go:visit:{encode_id(V2)}"),
    ]


async def test_active_visits_admin_sees_no_stars():
    api = AsyncMock()
    api.list_visits.return_value = {"items": [_visit(V1, OTHER)], "has_more": False}

    _, markup = await render_active_visits(api, ADMIN, {})

    assert not buttons(markup)[0][0].startswith("⭐")


async def test_active_visits_empty():
    api = AsyncMock()
    api.list_visits.return_value = {"items": [], "has_more": False}

    text, markup = await render_active_visits(api, MASTER, {})

    assert text == "Незакрытых заездов нет."
    assert buttons(markup) == []


async def test_active_visits_warns_when_truncated():
    api = AsyncMock()
    api.list_visits.return_value = {"items": [_visit(V1, ME)], "has_more": True}

    text, _ = await render_active_visits(api, MASTER, {})

    assert text == "Заезды в работе (1)\nПоказаны последние 30."


async def test_client_card_lists_vehicles_and_visits_button():
    api = AsyncMock()
    api.get_client.return_value = {"id": C1, "full_name": "Иван Иванов", "phone_display": "+7 999 123-45-67"}
    api.list_client_vehicles.return_value = [{"id": CAR, "make": "Toyota", "model": "Camry", "plate_number": "А123ВС77"}]

    text, markup = await render_client(api, MASTER, {"client_id": C1})

    assert text == "👤 Иван Иванов\n+7 999 123-45-67"
    assert buttons(markup) == [
        ("🚗 Toyota Camry (А123ВС77)", f"go:vehicle:{encode_id(CAR)}"),
        ("📋 Заезды клиента", f"go:client_visits:{encode_id(C1)}"),
    ]


def _car():
    return {"id": CAR, "make": "Toyota", "model": "Camry", "plate_number": "А123ВС77", "vin": "X" * 17, "mileage_current": 120500}


async def test_vehicle_card_for_master_has_owner_visits_new_visit_and_history():
    api = AsyncMock()
    api.get_vehicle.return_value = _car()
    api.get_vehicle_owner.return_value = {"id": C1, "full_name": "Иван Иванов"}

    text, markup = await render_vehicle(api, MASTER, {"vehicle_id": CAR})

    assert text == f"🚗 Toyota Camry · А123ВС77\nVIN: {'X' * 17} · Пробег: 120 500 км"
    assert buttons(markup) == [
        ("👤 Владелец: Иван Иванов", f"go:client:{encode_id(C1)}"),
        ("📋 Заезды по машине", f"go:vehicle_visits:{encode_id(CAR)}"),
        ("➕ Новый заезд", "act:new_visit_for"),
        ("🔧 История работ", f"go:work_history:{encode_id(CAR)}"),
    ]


async def test_vehicle_card_without_owner_hides_owner_and_new_visit():
    api = AsyncMock()
    api.get_vehicle.return_value = _car()
    api.get_vehicle_owner.return_value = None

    _, markup = await render_vehicle(api, MASTER, {"vehicle_id": CAR})

    assert [t for t, _ in buttons(markup)] == ["📋 Заезды по машине", "🔧 История работ"]


async def test_vehicle_card_for_mechanic_has_only_history_and_never_asks_owner():
    api = AsyncMock()
    api.get_vehicle.return_value = _car()

    _, markup = await render_vehicle(api, MECHANIC, {"vehicle_id": CAR})

    assert [t for t, _ in buttons(markup)] == ["🔧 История работ"]
    api.get_vehicle_owner.assert_not_awaited()


async def test_client_and_vehicle_visits_are_dated_lists():
    api = AsyncMock()
    api.list_visits.return_value = {"items": [_visit(V1, ME, status="issued")], "has_more": False}

    text, markup = await render_client_visits(api, MASTER, {"client_id": C1})
    api.list_visits.assert_awaited_with(client_id=C1)
    assert text == "Заезды (1)"
    assert buttons(markup) == [("⭐ 02.10 · А123ВС77 · Выдан", f"go:visit:{encode_id(V1)}")]

    await render_vehicle_visits(api, MASTER, {"vehicle_id": CAR})
    api.list_visits.assert_awaited_with(vehicle_id=CAR)


async def test_visits_history_empty():
    api = AsyncMock()
    api.list_visits.return_value = {"items": [], "has_more": False}

    text, _ = await render_client_visits(api, MASTER, {"client_id": C1})

    assert text == "Заездов ещё не было."


async def test_work_history_groups_by_visit():
    api = AsyncMock()
    api.get_vehicle.return_value = _car()
    api.get_vehicle_work_history.return_value = {
        "items": [
            {"visit_id": V1, "visit_at": "2026-10-02T07:00:00+00:00", "mileage": 120000, "name": "Замена масла", "status": "ready"},
            {"visit_id": V1, "visit_at": "2026-10-02T07:00:00+00:00", "mileage": 120000, "name": "Фильтр", "status": "in_progress"},
        ],
        "has_more": False,
    }

    text, markup = await render_work_history(api, MECHANIC, {"vehicle_id": CAR})

    assert text == "🔧 История работ · А123ВС77\n02.10.2026 · 120 000 км\n  • Замена масла — Готово\n  • Фильтр — В работе"
    assert buttons(markup) == []


async def test_work_history_empty_and_truncated():
    api = AsyncMock()
    api.get_vehicle.return_value = _car()
    api.get_vehicle_work_history.return_value = {"items": [], "has_more": False}
    assert (await render_work_history(api, MASTER, {"vehicle_id": CAR}))[0] == "Работ по машине ещё не было."

    api.get_vehicle_work_history.return_value = {
        "items": [{"visit_id": V1, "visit_at": "2026-10-02T07:00:00+00:00", "mileage": 1, "name": "X", "status": "ready"}],
        "has_more": True,
    }
    assert (await render_work_history(api, MASTER, {"vehicle_id": CAR}))[0].endswith("Показаны последние 30 работ.")
```

- [ ] **Step 2: Run, expect FAIL**

Run: `.venv/bin/pytest tests/bot/test_navigation_handler.py -q`
Expected: FAIL — `ImportError: cannot import name 'render_active_visits'`.

- [ ] **Step 3: Implement** — replace `bot/handlers/navigation.py` with:

```python
"""Read-only screens: visit lists, client/vehicle cards, histories."""
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot import actions, nav
from bot.api_client import ApiClient
from bot.formatting import format_date, format_day, format_number
from bot.visit_status import visit_status_label
from bot.work_item_status import work_item_status_label

LIST_TRUNCATED = "Показаны последние 30."
STAFF_ROLES = {"admin", "master"}


def visit_list(result: dict, user_id: str, title: str, empty_text: str, with_date: bool) -> nav.Rendered:
    builder = InlineKeyboardBuilder()
    visits = result["items"]
    if not visits:
        return empty_text, builder.as_markup()
    for visit in visits:
        if with_date:
            parts = [format_day(visit["created_at"]), visit["plate_number"]]
        else:
            parts = [visit["plate_number"], visit["client_name"]]
        parts.append(visit_status_label(visit["status"]))
        star = "⭐ " if str(visit["assigned_master_id"]) == str(user_id) else ""
        builder.button(text=star + " · ".join(parts), callback_data=nav.go_data("visit", visit["id"]))
    builder.adjust(1)
    text = f"{title} ({len(visits)})"
    if result["has_more"]:
        text += f"\n{LIST_TRUNCATED}"
    return text, builder.as_markup()


@nav.screen("active_visits")
async def render_active_visits(api: ApiClient, user: dict, args: dict) -> nav.Rendered:
    result = await api.list_visits(active=True)
    return visit_list(result, user["id"], "Заезды в работе", "Незакрытых заездов нет.", with_date=False)


@nav.screen("client", params=("client_id",))
async def render_client(api: ApiClient, user: dict, args: dict) -> nav.Rendered:
    client = await api.get_client(args["client_id"])
    vehicles = await api.list_client_vehicles(args["client_id"])
    builder = InlineKeyboardBuilder()
    for v in vehicles:
        builder.button(text=f"🚗 {v['make']} {v['model']} ({v['plate_number']})", callback_data=nav.go_data("vehicle", v["id"]))
    builder.button(text="📋 Заезды клиента", callback_data=nav.go_data("client_visits", args["client_id"]))
    builder.adjust(1)
    return f"👤 {client['full_name']}\n{client['phone_display']}", builder.as_markup()


@nav.screen("vehicle", params=("vehicle_id",))
async def render_vehicle(api: ApiClient, user: dict, args: dict) -> nav.Rendered:
    vehicle_id = args["vehicle_id"]
    vehicle = await api.get_vehicle(vehicle_id)
    builder = InlineKeyboardBuilder()
    if user["role"] in STAFF_ROLES:
        # Owner is personal data: mechanics never request it (the API would 403).
        owner = await api.get_vehicle_owner(vehicle_id)
        if owner is not None:
            builder.button(text=f"👤 Владелец: {owner['full_name']}", callback_data=nav.go_data("client", owner["id"]))
        builder.button(text="📋 Заезды по машине", callback_data=nav.go_data("vehicle_visits", vehicle_id))
        if owner is not None:
            builder.button(text="➕ Новый заезд", callback_data=actions.NEW_VISIT_FOR)
    builder.button(text="🔧 История работ", callback_data=nav.go_data("work_history", vehicle_id))
    builder.adjust(1)
    text = (
        f"🚗 {vehicle['make']} {vehicle['model']} · {vehicle['plate_number']}\n"
        f"VIN: {vehicle['vin']} · Пробег: {format_number(vehicle['mileage_current'])} км"
    )
    return text, builder.as_markup()


@nav.screen("client_visits", params=("client_id",))
async def render_client_visits(api: ApiClient, user: dict, args: dict) -> nav.Rendered:
    result = await api.list_visits(client_id=args["client_id"])
    return visit_list(result, user["id"], "Заезды", "Заездов ещё не было.", with_date=True)


@nav.screen("vehicle_visits", params=("vehicle_id",))
async def render_vehicle_visits(api: ApiClient, user: dict, args: dict) -> nav.Rendered:
    result = await api.list_visits(vehicle_id=args["vehicle_id"])
    return visit_list(result, user["id"], "Заезды", "Заездов ещё не было.", with_date=True)


@nav.screen("work_history", params=("vehicle_id",))
async def render_work_history(api: ApiClient, user: dict, args: dict) -> nav.Rendered:
    vehicle = await api.get_vehicle(args["vehicle_id"])
    history = await api.get_vehicle_work_history(args["vehicle_id"])
    no_buttons = InlineKeyboardBuilder().as_markup()
    if not history["items"]:
        return "Работ по машине ещё не было.", no_buttons
    lines = [f"🔧 История работ · {vehicle['plate_number']}"]
    current_visit = None
    for item in history["items"]:
        if item["visit_id"] != current_visit:
            current_visit = item["visit_id"]
            lines.append(f"{format_date(item['visit_at'])} · {format_number(item['mileage'])} км")
        lines.append(f"  • {item['name']} — {work_item_status_label(item['status'])}")
    if history["has_more"]:
        lines.append("Показаны последние 30 работ.")
    return "\n".join(lines), no_buttons
```

In `bot/main.py` remove `dp.include_router(navigation.router)` (keep the import).

- [ ] **Step 4: Run, expect PASS**

Run: `.venv/bin/pytest tests/bot -q`
Expected: all pass. If `tests/bot/test_routing.py` still references `client_open:`/`vehicle_open:`/`visit_open:` callbacks, delete those tests.

- [ ] **Step 5: Commit**

```bash
git add -A bot/handlers/navigation.py bot/main.py tests/bot/test_navigation_handler.py tests/bot/test_routing.py
git commit -m "feat(bot): visit lists, client/vehicle cards and histories as stack screens

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Compact visit card, work screen, my works, PDF

**Files:**
- Modify: `bot/handlers/visits.py` (add screens `visit`, `visit_status`, status action, cancel-reason wizard; delete `change_status_callback`, old `receive_cancel_reason`, `approve_work_callback`)
- Modify: `bot/handlers/work_items.py` (add screens `work`, `reassign`, actions; delete `start_reassign_mechanic`, `choose_new_mechanic_callback`)
- Rewrite: `bot/handlers/mechanic.py`, `bot/handlers/documents.py`
- Modify: `bot/work_item_status.py` (add icons)
- Modify: `bot/states.py` (delete `ReassignMechanicStates`)
- Delete: `bot/handlers/work_status.py`, `tests/bot/test_work_status_handler.py`, `tests/bot/test_reassign_mechanic_handler.py` (move its last test, see Step 1)
- Rewrite: `tests/bot/test_mechanic_handler.py`, `tests/bot/test_documents_handler.py`
- Create: `tests/bot/test_visit_screens.py`
- Modify: `tests/bot/test_visits_handler.py` (delete tests listed in Step 1), `tests/bot/test_routing.py`
- Modify: `bot/main.py` (drop `work_status`; import `mechanic` for registration)

**Interfaces:**
- Consumes: `nav.*`, `wizard.*`, `actions.*`, `navigation.STAFF_ROLES`.
- Produces: screens `visit(visit_id)`, `visit_status(visit_id)`, `work(visit_id, item_id)`, `reassign(visit_id, item_id)`, `my_works`; `work_item_status.work_item_icon(code) -> str`; `visits.visit_card(visit, items) -> (text, markup)`.
- Keep `send_visit_card`, `refresh_visit_card` (visits.py) and `add_work_status_buttons`, `FROM_VISIT_CARD`, `FROM_MY_WORK_ITEMS` (work_item_status.py) for now: the old add-work, add-part and new-visit wizards still call them until Tasks 8–9 delete them.

- [ ] **Step 1: Prune obsolete tests**

- Delete `tests/bot/test_work_status_handler.py`.
- Move `test_api_client_assign_work_item_mechanic_patches_endpoint` (with its `@respx.mock`, `VISIT_ID`, `ITEM_ID` constants and `httpx`/`respx`/`ApiClient` imports) from `tests/bot/test_reassign_mechanic_handler.py` to the end of `tests/bot/test_api_client.py`, then delete `tests/bot/test_reassign_mechanic_handler.py`.
- In `tests/bot/test_visits_handler.py` delete `test_approve_work_callback_approves_and_refreshes_card`, `test_change_status_callback_refreshes_visit_card`, `test_change_status_callback_cancelled_asks_for_reason`, `test_receive_cancel_reason_cancels_with_reason_and_refreshes_card`, `test_receive_cancel_reason_rejects_non_text`, `test_visit_header_formats_total_with_thousands_separator` (moves to the new file), and drop `approve_work_callback`, `change_status_callback`, `receive_cancel_reason` from its import list (and `VisitCancelStates` if now unused).
- In `tests/bot/test_routing.py` delete `test_work_status_button_from_card_routes_to_shared_handler` and `test_reassign_mechanic_buttons_route_end_to_end`.

- [ ] **Step 2: Write the failing tests**

`tests/bot/test_visit_screens.py`:

```python
from unittest.mock import AsyncMock

import pytest

from bot.api_client import ApiNotFound
from bot.callback_ids import encode_id
from bot.handlers.documents import pdf_callback
from bot.handlers.mechanic import render_my_works
from bot.handlers.visits import receive_cancel_reason, render_visit, render_visit_status, visit_header, visit_status_callback
from bot.handlers.work_items import (
    approve_callback,
    reassign_callback,
    render_reassign,
    render_work,
    work_status_callback,
)
from bot.states import VisitCancelStates
from tests.bot.helpers import MASTER, MECHANIC, buttons, fsm_context, make_callback, make_message, on_screens, shown

VISIT = "11111111-1111-1111-1111-111111111111"
ITEM = "22222222-2222-2222-2222-222222222222"
ITEM2 = "55555555-5555-5555-5555-555555555555"
MECH = "33333333-3333-3333-3333-333333333333"


def _visit(status="in_progress"):
    return {
        "id": VISIT, "status": status, "total_amount": 12400.0, "plate_number": "А123ВС77",
        "make_model": "Toyota Camry", "client_name": "Иванов Пётр", "master_name": "Петров",
    }


def _item(item_id=ITEM, name="Замена масла", status="in_progress", approved=True, mechanic="Сидоров"):
    return {"id": item_id, "visit_id": VISIT, "name": name, "status": status,
            "approved_by_client": approved, "assigned_mechanic_name": mechanic}


def _api(visit=None, items=None):
    api = AsyncMock()
    api.get_visit.return_value = visit or _visit()
    api.list_work_items.return_value = items if items is not None else [_item()]
    return api


# --- visit card ---

async def test_visit_card_is_compact_one_button_per_work_item():
    api = _api(items=[_item(), _item(ITEM2, "Диагностика", "not_ready", mechanic=None)])

    text, markup = await render_visit(api, MASTER, {"visit_id": VISIT})

    assert text.splitlines() == [
        "А123ВС77 · Toyota Camry · Иванов Пётр",
        "Статус: Ремонт · Мастер: Петров",
        "Сумма: 12 400",
        "Работы:",
        "1. Замена масла — В работе · Сидоров",
        "2. Диагностика — Не начата · без исполнителя",
    ]
    assert buttons(markup) == [
        ("🔧 1. Замена масла · Сидоров", f"go:work:{encode_id(VISIT)}:{encode_id(ITEM)}"),
        ("⏳ 2. Диагностика · без исполнителя", f"go:work:{encode_id(VISIT)}:{encode_id(ITEM2)}"),
        ("➕ Добавить работу", "act:add_work"),
        ("🔄 Статус заезда", f"go:visit_status:{encode_id(VISIT)}"),
        ("📄 PDF", "act:pdf"),
    ]


async def test_closed_visit_has_no_status_button():
    _, markup = await render_visit(_api(visit=_visit("issued"), items=[]), MASTER, {"visit_id": VISIT})

    assert "🔄 Статус заезда" not in [t for t, _ in buttons(markup)]


def test_visit_header_formats_total_and_falls_back_to_generic_title():
    assert visit_header({"status": "received", "total_amount": 12400.5}) == ["Заезд", "Статус: Принят", "Сумма: 12 400.50"]


# --- visit status ---

async def test_visit_status_screen_lists_allowed_next_statuses():
    text, markup = await render_visit_status(_api(visit=_visit("in_progress")), MASTER, {"visit_id": VISIT})

    assert text == "Статус сейчас: Ремонт\nСменить на:"
    assert buttons(markup) == [
        ("Ждём запчасти", "act:vstatus:waiting_parts"),
        ("Готов", "act:vstatus:ready"),
        ("Отменён", "act:vstatus:cancelled"),
    ]


async def test_choosing_status_changes_it_and_returns_to_card():
    state = fsm_context()
    await on_screens(state, ("visit", {"visit_id": VISIT}), ("visit_status", {"visit_id": VISIT}))
    api = _api()
    callback = make_callback("act:vstatus:ready")

    await visit_status_callback(callback, state, api=api, user=MASTER)

    api.change_visit_status.assert_awaited_once_with(VISIT, "ready")
    assert (await state.get_data())["nav_stack"] == [["menu", {}], ["visit", {"visit_id": VISIT}]]
    assert shown(callback)[0].startswith("А123ВС77")


async def test_choosing_cancelled_asks_for_reason():
    state = fsm_context()
    await on_screens(state, ("visit", {"visit_id": VISIT}), ("visit_status", {"visit_id": VISIT}))
    api = _api()
    callback = make_callback("act:vstatus:cancelled")

    await visit_status_callback(callback, state, api=api, user=MASTER)

    api.change_visit_status.assert_not_awaited()
    assert await state.get_state() == VisitCancelStates.waiting_for_reason.state
    assert (await state.get_data())["visit_id"] == VISIT
    assert shown(callback)[0] == "Укажите причину отмены заезда:"


async def test_cancel_reason_cancels_and_returns_to_card():
    state = fsm_context()
    await on_screens(state, ("visit", {"visit_id": VISIT}), ("visit_status", {"visit_id": VISIT}))
    await state.set_state(VisitCancelStates.waiting_for_reason)
    await state.update_data(visit_id=VISIT, wiz_steps=[])
    api = _api()
    message = make_message("клиент передумал")

    await receive_cancel_reason(message, state, api=api, user=MASTER)

    api.change_visit_status.assert_awaited_once_with(VISIT, "cancelled", reason="клиент передумал")
    assert await state.get_state() is None
    assert (await state.get_data())["nav_stack"][-1] == ["visit", {"visit_id": VISIT}]


async def test_cancel_reason_must_be_text():
    state = fsm_context()
    await on_screens(state, ("visit_status", {"visit_id": VISIT}))
    await state.set_state(VisitCancelStates.waiting_for_reason)
    await state.update_data(visit_id=VISIT)
    api = _api()
    message = make_message(None)

    await receive_cancel_reason(message, state, api=api, user=MASTER)

    api.change_visit_status.assert_not_awaited()
    assert shown(message)[0] == "Пожалуйста, отправьте ответ текстом.\n\nУкажите причину отмены заезда:"


async def test_status_button_from_another_screen_is_stale():
    state = fsm_context()
    await on_screens(state, ("visit", {"visit_id": VISIT}))
    api = _api()
    callback = make_callback("act:vstatus:ready")

    await visit_status_callback(callback, state, api=api, user=MASTER)

    api.change_visit_status.assert_not_awaited()
    callback.answer.assert_awaited_once_with("Кнопка устарела — начните действие заново.")


# --- work screen ---

async def test_work_screen_for_master():
    api = _api(items=[_item(approved=False)])

    text, markup = await render_work(api, MASTER, {"visit_id": VISIT, "item_id": ITEM})

    assert text == "А123ВС77 · Toyota Camry\n🔧 Замена масла\nСтатус: В работе\nИсполнитель: Сидоров\nСогласовано клиентом: нет"
    assert buttons(markup) == [
        ("✅ Согласовано клиентом", "act:approve"),
        ("→ Ждёт запчасти", "act:wstatus:waiting_parts"),
        ("→ Готово", "act:wstatus:ready"),
        ("🔩 Добавить запчасть", "act:add_part"),
        ("👤 Сменить исполнителя", f"go:reassign:{encode_id(VISIT)}:{encode_id(ITEM)}"),
    ]


async def test_work_screen_for_mechanic_has_only_status_buttons_and_no_visit_call():
    api = AsyncMock()
    api.list_my_work_items.return_value = [
        {"id": ITEM, "visit_id": VISIT, "name": "Замена масла", "status": "not_ready",
         "plate_number": "А123ВС77", "make_model": "Toyota Camry"},
    ]

    text, markup = await render_work(api, MECHANIC, {"visit_id": VISIT, "item_id": ITEM})

    api.get_visit.assert_not_awaited()
    assert text == "А123ВС77 · Toyota Camry\n⏳ Замена масла\nСтатус: Не начата"
    assert buttons(markup) == [("→ В работе", "act:wstatus:in_progress")]


async def test_work_screen_reassigned_away_from_mechanic_raises_not_found():
    api = AsyncMock()
    api.list_my_work_items.return_value = []

    with pytest.raises(ApiNotFound):
        await render_work(api, MECHANIC, {"visit_id": VISIT, "item_id": ITEM})


async def test_work_status_action_updates_and_redraws_in_place():
    state = fsm_context()
    await on_screens(state, ("work", {"visit_id": VISIT, "item_id": ITEM}))
    api = _api()
    callback = make_callback("act:wstatus:ready")

    await work_status_callback(callback, state, api=api, user=MASTER)

    api.update_work_item_status.assert_awaited_once_with(VISIT, ITEM, "ready")
    assert (await state.get_data())["nav_stack"][-1][0] == "work"
    callback.message.edit_text.assert_awaited_once()


async def test_work_status_action_on_old_message_is_stale():
    state = fsm_context()
    await on_screens(state, ("work", {"visit_id": VISIT, "item_id": ITEM}), msg_id=7)
    api = _api()
    callback = make_callback("act:wstatus:ready", message_id=5)

    await work_status_callback(callback, state, api=api, user=MASTER)

    api.update_work_item_status.assert_not_awaited()


async def test_approve_action():
    state = fsm_context()
    await on_screens(state, ("work", {"visit_id": VISIT, "item_id": ITEM}))
    api = _api()

    await approve_callback(make_callback("act:approve"), state, api=api, user=MASTER)

    api.approve_work_item.assert_awaited_once_with(VISIT, ITEM)


async def test_reassign_screen_and_choice_returns_to_work():
    api = _api()
    api.list_mechanics.return_value = [{"id": MECH, "full_name": "Петров"}]

    text, markup = await render_reassign(api, MASTER, {"visit_id": VISIT, "item_id": ITEM})
    assert text == "Кому передать работу?"
    assert buttons(markup) == [("Петров", f"act:reassign:{encode_id(MECH)}"), ("Без исполнителя", "act:reassign:none")]

    state = fsm_context()
    args = {"visit_id": VISIT, "item_id": ITEM}
    await on_screens(state, ("work", args), ("reassign", args))
    await reassign_callback(make_callback(f"act:reassign:{encode_id(MECH)}"), state, api=api, user=MASTER)
    api.assign_work_item_mechanic.assert_awaited_once_with(VISIT, ITEM, MECH)
    assert (await state.get_data())["nav_stack"][-1] == ["work", args]

    await on_screens(state, ("work", args), ("reassign", args))
    await reassign_callback(make_callback("act:reassign:none"), state, api=api, user=MASTER)
    api.assign_work_item_mechanic.assert_awaited_with(VISIT, ITEM, None)


# --- my works ---

async def test_my_works_lists_items_with_car():
    api = AsyncMock()
    api.list_my_work_items.return_value = [
        {"id": ITEM, "visit_id": VISIT, "name": "Замена масла", "status": "in_progress", "plate_number": "А123ВС77"},
    ]

    text, markup = await render_my_works(api, MECHANIC, {})

    assert text == "Мои работы (1)"
    assert buttons(markup) == [("🔧 Замена масла · А123ВС77", f"go:work:{encode_id(VISIT)}:{encode_id(ITEM)}")]


async def test_my_works_empty():
    api = AsyncMock()
    api.list_my_work_items.return_value = []

    text, markup = await render_my_works(api, MECHANIC, {})

    assert text == "У вас нет назначенных работ."
    assert buttons(markup) == []


# --- pdf ---

async def test_pdf_action_sends_document_without_redrawing():
    state = fsm_context()
    await on_screens(state, ("visit", {"visit_id": VISIT}))
    api = AsyncMock()
    api.generate_document.return_value = {"document_id": "d1"}
    api.get_document_file.return_value = b"%PDF"
    callback = make_callback("act:pdf")

    await pdf_callback(callback, state, api=api, user=MASTER)

    api.generate_document.assert_awaited_once_with(VISIT)
    document = callback.message.answer_document.await_args.args[0]
    assert document.filename == f"zakaz-naryad-{VISIT}.pdf"
    callback.message.edit_text.assert_not_awaited()
    callback.answer.assert_awaited_once_with()
```

Replace `tests/bot/test_mechanic_handler.py` and `tests/bot/test_documents_handler.py` with a single line each — `# Covered by tests/bot/test_visit_screens.py` — or delete them (preferred: `git rm`).

- [ ] **Step 3: Run, expect FAIL**

Run: `.venv/bin/pytest tests/bot/test_visit_screens.py -q`
Expected: FAIL — `ImportError: cannot import name 'pdf_callback'`.

- [ ] **Step 4: Implement**

`bot/work_item_status.py` — add after `WORK_ITEM_STATUS_LABELS`:

```python
WORK_ITEM_STATUS_ICONS: dict[str, str] = {
    "not_ready": "⏳",
    "in_progress": "🔧",
    "waiting_parts": "📦",
    "ready": "✅",
}


def work_item_icon(code: str) -> str:
    return WORK_ITEM_STATUS_ICONS.get(code, "•")
```

`bot/handlers/documents.py` — replace with:

```python
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery

from bot import actions, nav
from bot.api_client import ApiClient

router = Router()


@router.callback_query(F.data == actions.PDF)
async def pdf_callback(callback: CallbackQuery, state: FSMContext, api: ApiClient, **kwargs) -> None:
    """Send the work order as a separate document; the live card stays as it is."""
    args = await nav.top_args(callback, state, "visit")
    if args is None:
        return
    visit_id = args["visit_id"]
    result = await api.generate_document(visit_id)
    content = await api.get_document_file(result["document_id"])
    await callback.message.answer_document(BufferedInputFile(content, filename=f"zakaz-naryad-{visit_id}.pdf"))
    await callback.answer()
```

`bot/handlers/mechanic.py` — replace with:

```python
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot import nav
from bot.api_client import ApiClient
from bot.work_item_status import work_item_icon


@nav.screen("my_works")
async def render_my_works(api: ApiClient, user: dict, args: dict) -> nav.Rendered:
    items = await api.list_my_work_items()
    builder = InlineKeyboardBuilder()
    if not items:
        return "У вас нет назначенных работ.", builder.as_markup()
    for item in items:
        label = f"{work_item_icon(item['status'])} {item['name']}"
        if item.get("plate_number"):
            label += f" · {item['plate_number']}"
        builder.button(text=label, callback_data=nav.go_data("work", item["visit_id"], item["id"]))
    builder.adjust(1)
    return f"Мои работы ({len(items)})", builder.as_markup()
```

`bot/handlers/visits.py` — add imports `from aiogram.types import InlineKeyboardMarkup`, `from bot import actions, nav, wizard`, `from bot.work_item_status import work_item_icon`. Delete `change_status_callback`, the old `receive_cancel_reason`, `approve_work_callback`. Add:

```python
def visit_card(visit: dict, work_items: list[dict]) -> nav.Rendered:
    """Header + numbered work list; one button per work item opens its screen."""
    lines = visit_header(visit)
    builder = InlineKeyboardBuilder()
    if work_items:
        lines.append("Работы:")
    for index, item in enumerate(work_items, start=1):
        mechanic = item.get("assigned_mechanic_name") or "без исполнителя"
        lines.append(f"{index}. {item['name']} — {work_item_status_label(item['status'])} · {mechanic}")
        builder.button(
            text=f"{work_item_icon(item['status'])} {index}. {item['name']} · {mechanic}",
            callback_data=nav.go_data("work", visit["id"], item["id"]),
        )
    builder.button(text="➕ Добавить работу", callback_data=actions.ADD_WORK)
    if visit["status"] in _NEXT_STATUS_BY_CURRENT:
        builder.button(text="🔄 Статус заезда", callback_data=nav.go_data("visit_status", visit["id"]))
    builder.button(text="📄 PDF", callback_data=actions.PDF)
    builder.adjust(1)
    return "\n".join(lines), builder.as_markup()


@nav.screen("visit", params=("visit_id",))
async def render_visit(api: ApiClient, user: dict, args: dict) -> nav.Rendered:
    visit = await api.get_visit(args["visit_id"])
    items = await api.list_work_items(args["visit_id"])
    return visit_card(visit, items)


@nav.screen("visit_status", params=("visit_id",))
async def render_visit_status(api: ApiClient, user: dict, args: dict) -> nav.Rendered:
    visit = await api.get_visit(args["visit_id"])
    builder = InlineKeyboardBuilder()
    for status in _NEXT_STATUS_BY_CURRENT.get(visit["status"], []):
        builder.button(text=visit_status_label(status), callback_data=f"{actions.VISIT_STATUS}:{status}")
    builder.adjust(1)
    return f"Статус сейчас: {visit_status_label(visit['status'])}\nСменить на:", builder.as_markup()


@router.callback_query(F.data.startswith(f"{actions.VISIT_STATUS}:"))
async def visit_status_callback(callback: CallbackQuery, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    args = await nav.top_args(callback, state, "visit_status")
    if args is None:
        return
    new_status = callback.data.rsplit(":", 1)[1]
    if new_status == "cancelled":
        await wizard.start(callback, state, api, user, "cancel_visit", VisitCancelStates.waiting_for_reason, visit_id=args["visit_id"])
        return
    await api.change_visit_status(args["visit_id"], new_status)
    await nav.pop(callback, state, api, user)


@wizard.step(VisitCancelStates.waiting_for_reason)
async def cancel_reason_prompt(state: FSMContext, api: ApiClient, user: dict):
    return "Укажите причину отмены заезда:", None


@router.message(VisitCancelStates.waiting_for_reason)
async def receive_cancel_reason(message: Message, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    if not message.text:
        await wizard.reprompt(message, state, api, user, TEXT_REQUIRED)
        return
    visit_id = (await state.get_data())["visit_id"]
    await api.change_visit_status(visit_id, "cancelled", reason=message.text)
    await wizard.finish(state)
    await nav.pop(message, state, api, user)  # off the status screen, back to the card
```

`bot/handlers/work_items.py` — add imports `from bot import actions, nav`, `from bot.api_client import ApiNotFound`, `from bot.handlers.navigation import STAFF_ROLES`, `from bot.work_item_status import NEXT_WORK_ITEM_STATUSES, work_item_icon, work_item_status_label`. Delete `start_reassign_mechanic`, `choose_new_mechanic_callback` and the `ReassignMechanicStates` import. Add:

```python
def _find(items: list[dict], item_id: str) -> dict | None:
    return next((i for i in items if str(i["id"]) == str(item_id)), None)


def _title(source: dict) -> str:
    return " · ".join(p for p in (source.get("plate_number"), source.get("make_model")) if p)


@nav.screen("work", params=("visit_id", "item_id"))
async def render_work(api: ApiClient, user: dict, args: dict) -> nav.Rendered:
    staff = user["role"] in STAFF_ROLES
    if staff:
        visit = await api.get_visit(args["visit_id"])
        item = _find(await api.list_work_items(args["visit_id"]), args["item_id"])
        if item is None:
            raise ApiNotFound("Работа не найдена.")
        title = _title(visit)
    else:
        # Mechanics can't read the visit; their own list carries the car.
        item = _find(await api.list_my_work_items(), args["item_id"])
        if item is None:
            raise ApiNotFound("Работа больше не назначена вам.")
        title = _title(item)
    lines = [title] if title else []
    lines += [f"{work_item_icon(item['status'])} {item['name']}", f"Статус: {work_item_status_label(item['status'])}"]
    builder = InlineKeyboardBuilder()
    if staff:
        lines.append(f"Исполнитель: {item.get('assigned_mechanic_name') or 'без исполнителя'}")
        lines.append(f"Согласовано клиентом: {'да' if item['approved_by_client'] else 'нет'}")
        if not item["approved_by_client"]:
            builder.button(text="✅ Согласовано клиентом", callback_data=actions.APPROVE)
    for status in NEXT_WORK_ITEM_STATUSES.get(item["status"], []):
        builder.button(text=f"→ {work_item_status_label(status)}", callback_data=f"{actions.WORK_STATUS}:{status}")
    if staff:
        builder.button(text="🔩 Добавить запчасть", callback_data=actions.ADD_PART)
        builder.button(text="👤 Сменить исполнителя", callback_data=nav.go_data("reassign", args["visit_id"], args["item_id"]))
    builder.adjust(1)
    return "\n".join(lines), builder.as_markup()


@router.callback_query(F.data.startswith(f"{actions.WORK_STATUS}:"))
async def work_status_callback(callback: CallbackQuery, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    args = await nav.top_args(callback, state, "work")
    if args is None:
        return
    await api.update_work_item_status(args["visit_id"], args["item_id"], callback.data.rsplit(":", 1)[1])
    await nav.refresh(callback, state, api, user)


@router.callback_query(F.data == actions.APPROVE)
async def approve_callback(callback: CallbackQuery, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    args = await nav.top_args(callback, state, "work")
    if args is None:
        return
    await api.approve_work_item(args["visit_id"], args["item_id"])
    await nav.refresh(callback, state, api, user)


@nav.screen("reassign", params=("visit_id", "item_id"))
async def render_reassign(api: ApiClient, user: dict, args: dict) -> nav.Rendered:
    builder = InlineKeyboardBuilder()
    for mechanic in await api.list_mechanics():
        builder.button(text=mechanic["full_name"], callback_data=f"{actions.REASSIGN}:{encode_id(mechanic['id'])}")
    builder.button(text="Без исполнителя", callback_data=f"{actions.REASSIGN}:none")
    builder.adjust(1)
    return "Кому передать работу?", builder.as_markup()


@router.callback_query(F.data.startswith(f"{actions.REASSIGN}:"))
async def reassign_callback(callback: CallbackQuery, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    args = await nav.top_args(callback, state, "reassign")
    if args is None:
        return
    picked = callback.data.rsplit(":", 1)[1]
    await api.assign_work_item_mechanic(args["visit_id"], args["item_id"], None if picked == "none" else decode_id(picked))
    await nav.pop(callback, state, api, user)
```

`bot/states.py` — delete `class ReassignMechanicStates`.

Delete `bot/handlers/work_status.py`. In `bot/main.py`: remove `work_status` from imports and `dp.include_router(work_status.router)`; add `mechanic` to the handler import list with a trailing comment `# mechanic, navigation: imported to register their screens`.

- [ ] **Step 5: Run, expect PASS**

Run: `.venv/bin/pytest tests/bot -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add -A bot tests/bot
git commit -m "feat(bot): compact visit card, work and status screens, my works list

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: New-visit wizard (with client/vehicle sub-steps), `/new_client`, `/new_vehicle`

**Files:**
- Modify: `bot/handlers/visits.py` (replace the new-visit section: `start_new_visit` … `new_visit_for_vehicle_callback`)
- Rewrite: `bot/handlers/clients.py`, `bot/handlers/vehicles.py`
- Rewrite: `tests/bot/test_visits_handler.py`, `tests/bot/test_clients_handler.py`, `tests/bot/test_vehicles_handler.py`
- Modify: `tests/bot/test_routing.py`

**Interfaces:**
- Consumes: `wizard.start/goto/reprompt/finish/name/step`, `nav.push/home/refresh/top_args`, `actions.NEW_VISIT`, `actions.NEW_VISIT_FOR`, screen `visit`.
- Produces: wizard name `"new_visit"` (steps across `NewVisitStates`, `NewClientStates`, `NewVehicleStates`), `"new_client"`, `"new_vehicle"`. Callback data kept: `client_pick:<uuid>`, `vehicle_pick:<uuid>`, `mileage_confirm`, `master_pick:<enc>`.
- FSM data keys: `client_choices: list[[id, name]]`, `vehicle_choices: list[[id, plate]]`, `master_choices: list[[id, name]]`, `client_id`, `vehicle_id`, `mileage`, `mileage_confirmed`, `assigned_master_id`, `rollback_message`, `owner_name`, `created_client`, `created_vehicle`.

- [ ] **Step 1: Write the failing tests** — replace `tests/bot/test_visits_handler.py` with:

```python
import json
from unittest.mock import AsyncMock

from bot.api_client import ApiMileageRollback
from bot.callback_ids import encode_id
from bot.handlers.visits import (
    choose_client_callback,
    choose_master_callback,
    choose_vehicle_callback,
    confirm_mileage_callback,
    new_visit_for_callback,
    receive_client_query,
    receive_mileage,
    receive_vehicle_query,
    start_new_visit,
)
from bot.states import NewClientStates, NewVehicleStates, NewVisitStates
from tests.bot.helpers import ADMIN, MASTER, MECHANIC, buttons, fsm_context, make_callback, make_message, on_screens, shown

C1 = "11111111-1111-1111-1111-111111111111"
CAR = "44444444-4444-4444-4444-444444444444"
VISIT = "55555555-5555-5555-5555-555555555555"
MASTER_B = "66666666-6666-6666-6666-666666666666"


def _api():
    api = AsyncMock()
    api.create_visit.return_value = {"id": VISIT, "status": "received", "total_amount": 0}
    api.get_visit.return_value = {"id": VISIT, "status": "received", "total_amount": 0, "plate_number": "А123ВС77"}
    api.list_work_items.return_value = []
    return api


async def _at(state, step, **data):
    await on_screens(state)
    await state.set_state(step)
    await state.update_data(wiz_name="new_visit", wiz_steps=[], **data)


async def test_start_from_menu_asks_for_client():
    state = fsm_context()
    await on_screens(state)
    callback = make_callback("wiz:new_visit")

    await start_new_visit(callback, state, api=_api(), user=MASTER)

    assert await state.get_state() == NewVisitStates.waiting_for_client_query.state
    assert shown(callback)[0] == "Введите телефон или ФИО клиента:"


async def test_start_refused_for_mechanic():
    state = fsm_context()
    callback = make_callback("wiz:new_visit")

    await start_new_visit(callback, state, api=_api(), user=MECHANIC)

    assert await state.get_state() is None
    callback.answer.assert_awaited_once_with("Недостаточно прав")


async def test_client_query_offers_candidates_and_data_is_json():
    state = fsm_context()
    await _at(state, NewVisitStates.waiting_for_client_query)
    api = _api()
    api.search.return_value = [{"entity": "client", "id": C1}, {"entity": "vehicle", "id": CAR}]
    api.get_client.return_value = {"id": C1, "full_name": "Иван Иванов"}
    message = make_message("Иван")

    await receive_client_query(message, state, api=api, user=MASTER)

    assert await state.get_state() == NewVisitStates.choosing_client.state
    text, markup = shown(message)
    assert text == "Выберите клиента:"
    assert buttons(markup)[0] == ("Иван Иванов", f"client_pick:{C1}")
    json.dumps(await state.get_data())  # survives RedisStorage


async def test_client_not_found_goes_to_client_creation():
    state = fsm_context()
    await _at(state, NewVisitStates.waiting_for_client_query)
    api = _api()
    api.search.return_value = []
    message = make_message("Пётр")

    await receive_client_query(message, state, api=api, user=MASTER)

    assert await state.get_state() == NewClientStates.waiting_for_phone.state
    assert shown(message)[0] == "Клиент не найден. Введите телефон клиента:"


async def test_choose_client_then_vehicle_query():
    state = fsm_context()
    await _at(state, NewVisitStates.choosing_client, client_choices=[[C1, "Иван"]])
    callback = make_callback(f"client_pick:{C1}")

    await choose_client_callback(callback, state, api=_api(), user=MASTER)

    assert (await state.get_data())["client_id"] == C1
    assert await state.get_state() == NewVisitStates.waiting_for_vehicle_query.state
    assert shown(callback)[0] == "Введите VIN или гос.номер авто:"


async def test_vehicle_query_offers_candidates():
    state = fsm_context()
    await _at(state, NewVisitStates.waiting_for_vehicle_query, client_id=C1)
    api = _api()
    api.search.return_value = [{"entity": "vehicle", "id": CAR}]
    api.get_vehicle.return_value = {"id": CAR, "plate_number": "А123ВС77"}
    message = make_message("А123")

    await receive_vehicle_query(message, state, api=api, user=MASTER)

    assert await state.get_state() == NewVisitStates.choosing_vehicle.state
    assert buttons(shown(message)[1])[0] == ("А123ВС77", f"vehicle_pick:{CAR}")


async def test_vehicle_not_found_goes_to_vehicle_creation():
    state = fsm_context()
    await _at(state, NewVisitStates.waiting_for_vehicle_query, client_id=C1)
    api = _api()
    api.search.return_value = []
    message = make_message("Х000")

    await receive_vehicle_query(message, state, api=api, user=MASTER)

    assert await state.get_state() == NewVehicleStates.waiting_for_vin.state
    assert shown(message)[0] == "Автомобиль не найден. Введите VIN:"


async def test_choose_vehicle_then_mileage():
    state = fsm_context()
    await _at(state, NewVisitStates.choosing_vehicle, client_id=C1, vehicle_choices=[[CAR, "А123ВС77"]])
    callback = make_callback(f"vehicle_pick:{CAR}")

    await choose_vehicle_callback(callback, state, api=_api(), user=MASTER)

    assert (await state.get_data())["vehicle_id"] == CAR
    assert shown(callback)[0] == "Введите пробег на приёмке:"


async def test_master_mileage_creates_visit_and_opens_card_over_source():
    state = fsm_context()
    await _at(state, NewVisitStates.waiting_for_mileage, client_id=C1, vehicle_id=CAR)
    api = _api()
    message = make_message("45000")

    await receive_mileage(message, state, api=api, user=MASTER)

    api.create_visit.assert_awaited_once_with(
        client_id=C1, vehicle_id=CAR, assigned_master_id=MASTER["id"], mileage_at_intake=45000,
        mileage_manually_confirmed=False,
    )
    assert await state.get_state() is None
    assert (await state.get_data())["nav_stack"] == [["menu", {}], ["visit", {"visit_id": VISIT}]]


async def test_mileage_must_be_a_number():
    state = fsm_context()
    await _at(state, NewVisitStates.waiting_for_mileage, client_id=C1, vehicle_id=CAR)
    message = make_message("много")

    await receive_mileage(message, state, api=_api(), user=MASTER)

    assert shown(message)[0] == "Введите число (пробег в км).\n\nВведите пробег на приёмке:"


async def test_mileage_rollback_asks_confirmation_then_confirm_creates():
    state = fsm_context()
    await _at(state, NewVisitStates.waiting_for_mileage, client_id=C1, vehicle_id=CAR)
    api = _api()
    api.create_visit.side_effect = [ApiMileageRollback("Пробег меньше последнего (50 000)."), api.create_visit.return_value]
    message = make_message("900")

    await receive_mileage(message, state, api=api, user=MASTER)

    assert await state.get_state() == NewVisitStates.confirming_mileage.state
    text, markup = shown(message)
    assert text == "Пробег меньше последнего (50 000).\nИли введите другой пробег."
    assert buttons(markup)[0] == ("Подтвердить пробег", "mileage_confirm")

    await confirm_mileage_callback(make_callback("mileage_confirm"), state, api=api, user=MASTER)

    assert api.create_visit.await_args.kwargs["mileage_manually_confirmed"] is True
    assert await state.get_state() is None


async def test_admin_chooses_master_then_visit_is_created_with_them():
    state = fsm_context()
    await _at(state, NewVisitStates.waiting_for_mileage, client_id=C1, vehicle_id=CAR)
    api = _api()
    api.list_masters.return_value = [{"id": MASTER_B, "full_name": "Петров"}]
    message = make_message("45000")

    await receive_mileage(message, state, api=api, user=ADMIN)

    assert await state.get_state() == NewVisitStates.choosing_master.state
    assert buttons(shown(message)[1])[0] == ("Петров", f"master_pick:{encode_id(MASTER_B)}")

    await choose_master_callback(make_callback(f"master_pick:{encode_id(MASTER_B)}"), state, api=api, user=ADMIN)

    assert api.create_visit.await_args.kwargs["assigned_master_id"] == MASTER_B


async def test_admin_without_masters_is_told_to_add_one():
    state = fsm_context()
    await _at(state, NewVisitStates.waiting_for_mileage, client_id=C1, vehicle_id=CAR)
    api = _api()
    api.list_masters.return_value = []
    message = make_message("45000")

    await receive_mileage(message, state, api=api, user=ADMIN)

    assert await state.get_state() is None
    assert shown(message)[0].startswith("Сначала добавьте мастера через «Добавить сотрудника».")
    api.create_visit.assert_not_awaited()


async def test_new_visit_from_vehicle_card_starts_at_mileage_with_owner():
    state = fsm_context()
    await on_screens(state, ("vehicle", {"vehicle_id": CAR}))
    api = _api()
    api.get_vehicle_owner.return_value = {"id": C1, "full_name": "Иван Иванов"}
    callback = make_callback("act:new_visit_for")

    await new_visit_for_callback(callback, state, api=api, user=MASTER)

    data = await state.get_data()
    assert (data["client_id"], data["vehicle_id"]) == (C1, CAR)
    assert shown(callback)[0] == "Новый заезд: Иван Иванов. Введите пробег на приёмке:"


async def test_new_visit_from_vehicle_without_owner_is_refused():
    state = fsm_context()
    await on_screens(state, ("vehicle", {"vehicle_id": CAR}))
    api = _api()
    api.get_vehicle_owner.return_value = None
    callback = make_callback("act:new_visit_for")

    await new_visit_for_callback(callback, state, api=api, user=MASTER)

    assert await state.get_state() is None
    callback.answer.assert_awaited_once_with("У машины нет владельца — заведите заезд через «Новый заезд».", show_alert=True)


async def test_new_visit_from_vehicle_refused_for_mechanic():
    state = fsm_context()
    await on_screens(state, ("vehicle", {"vehicle_id": CAR}))
    api = _api()
    callback = make_callback("act:new_visit_for")

    await new_visit_for_callback(callback, state, api=api, user=MECHANIC)

    api.get_vehicle_owner.assert_not_awaited()
    callback.answer.assert_awaited_once_with("Недостаточно прав")
```

Replace `tests/bot/test_clients_handler.py` with:

```python
from unittest.mock import AsyncMock

from bot import wizard
from bot.handlers.clients import receive_full_name, receive_phone, start_new_client
from bot.states import NewClientStates, NewVisitStates
from tests.bot.helpers import MASTER, MECHANIC, fsm_context, make_callback, make_message, on_screens, shown

C1 = "11111111-1111-1111-1111-111111111111"


async def test_new_client_command_asks_for_phone():
    state = fsm_context()
    message = make_message("/new_client")

    await start_new_client(message, state, api=AsyncMock(), user=MASTER)

    assert await state.get_state() == NewClientStates.waiting_for_phone.state
    assert shown(message)[0] == "Введите телефон клиента:"


async def test_new_client_refused_for_mechanic():
    state = fsm_context()
    message = make_message("/new_client")

    await start_new_client(message, state, api=AsyncMock(), user=MECHANIC)

    assert await state.get_state() is None
    message.answer.assert_awaited_once_with("Недостаточно прав.")


async def test_standalone_client_is_created_and_menu_shown():
    state = fsm_context()
    await on_screens(state)
    await state.set_state(NewClientStates.waiting_for_full_name)
    await state.update_data(wiz_name="new_client", wiz_steps=[], phone="79990000000")
    api = AsyncMock()
    api.create_client.return_value = {"id": C1, "full_name": "Иван Иванов"}
    message = make_message("Иван Иванов")

    await receive_full_name(message, state, api=api, user=MASTER)

    api.create_client.assert_awaited_once_with(full_name="Иван Иванов", phone="79990000000")
    assert await state.get_state() is None
    assert shown(message)[0] == "Клиент создан: Иван Иванов\n\nГлавное меню"


async def test_client_in_new_visit_continues_and_back_cannot_recreate_it():
    state = fsm_context()
    await on_screens(state)
    await state.set_state(NewClientStates.waiting_for_full_name)
    await state.update_data(wiz_name="new_visit", wiz_steps=["NewVisitStates:waiting_for_client_query"], phone="7999")
    api = AsyncMock()
    api.create_client.return_value = {"id": C1, "full_name": "Иван Иванов"}
    message = make_message("Иван Иванов")

    await receive_full_name(message, state, api=api, user=MASTER)

    assert (await state.get_data())["client_id"] == C1
    assert await state.get_state() == NewVisitStates.waiting_for_vehicle_query.state
    assert shown(message)[0] == "Клиент создан: Иван Иванов\nВведите VIN или гос.номер авто:"

    await wizard.back_callback(make_callback("wiz_back"), state, api=api, user=MASTER)

    assert await state.get_state() is None  # history dropped: back = cancel
    api.create_client.assert_awaited_once()


async def test_phone_must_be_text():
    state = fsm_context()
    await state.set_state(NewClientStates.waiting_for_phone)
    await state.update_data(wiz_name="new_client", wiz_steps=[])
    message = make_message(None)

    await receive_phone(message, state, api=AsyncMock(), user=MASTER)

    assert shown(message)[0] == "Пожалуйста, отправьте ответ текстом.\n\nВведите телефон клиента:"
```

Replace `tests/bot/test_vehicles_handler.py` with:

```python
from datetime import date
from unittest.mock import AsyncMock

from bot.handlers.vehicles import receive_make_model, start_new_vehicle
from bot.states import NewVehicleStates, NewVisitStates
from tests.bot.helpers import MASTER, MECHANIC, fsm_context, make_message, on_screens, shown

C1 = "11111111-1111-1111-1111-111111111111"
CAR = "44444444-4444-4444-4444-444444444444"


async def test_new_vehicle_command_asks_for_vin():
    state = fsm_context()
    message = make_message("/new_vehicle")

    await start_new_vehicle(message, state, api=AsyncMock(), user=MASTER)

    assert await state.get_state() == NewVehicleStates.waiting_for_vin.state
    assert shown(message)[0] == "Введите VIN:"


async def test_new_vehicle_refused_for_mechanic():
    message = make_message("/new_vehicle")

    await start_new_vehicle(message, fsm_context(), api=AsyncMock(), user=MECHANIC)

    message.answer.assert_awaited_once_with("Недостаточно прав.")


async def test_standalone_vehicle_is_created_without_owner():
    state = fsm_context()
    await on_screens(state)
    await state.set_state(NewVehicleStates.waiting_for_make_model)
    await state.update_data(wiz_name="new_vehicle", wiz_steps=[], vin="X" * 17, plate_number="А123ВС77")
    api = AsyncMock()
    api.create_vehicle.return_value = {"id": CAR, "vin": "X" * 17}
    message = make_message("Toyota Camry")

    await receive_make_model(message, state, api=api, user=MASTER)

    api.create_vehicle.assert_awaited_once_with(vin="X" * 17, plate_number="А123ВС77", make="Toyota", model="Camry")
    api.attach_owner.assert_not_awaited()
    assert shown(message)[0] == f"Автомобиль создан: {'X' * 17}\n\nГлавное меню"


async def test_vehicle_in_new_visit_is_linked_to_client_and_asks_mileage():
    state = fsm_context()
    await on_screens(state)
    await state.set_state(NewVehicleStates.waiting_for_make_model)
    await state.update_data(wiz_name="new_visit", wiz_steps=[], client_id=C1, vin="X" * 17, plate_number="А1")
    api = AsyncMock()
    api.create_vehicle.return_value = {"id": CAR, "vin": "X" * 17}
    message = make_message("Toyota Camry")

    await receive_make_model(message, state, api=api, user=MASTER)

    api.attach_owner.assert_awaited_once_with(CAR, C1, date_from=date.today().isoformat())
    assert (await state.get_data())["vehicle_id"] == CAR
    assert await state.get_state() == NewVisitStates.waiting_for_mileage.state
    assert shown(message)[0] == f"Автомобиль создан: {'X' * 17}\nВведите пробег на приёмке:"
    assert (await state.get_data())["wiz_steps"] == []
```

In `tests/bot/test_routing.py`, in `test_mileage_confirm_callback_routes_in_confirming_state`: set `api.list_work_items.return_value = []` and `api.get_visit.return_value = {"id": "11111111-1111-1111-1111-111111111111", "status": "received", "total_amount": 0}` before feeding the update, and also `await state.update_data(wiz_name="new_visit", wiz_steps=[])`.

- [ ] **Step 2: Run, expect FAIL**

Run: `.venv/bin/pytest tests/bot/test_visits_handler.py tests/bot/test_clients_handler.py tests/bot/test_vehicles_handler.py -q`
Expected: FAIL — `ImportError: cannot import name 'new_visit_for_callback'`.

- [ ] **Step 3: Implement**

In `bot/handlers/visits.py`, delete everything from `async def start_new_visit` through `new_visit_for_vehicle_callback` (keep `_NEXT_STATUS_BY_CURRENT`, `MILEAGE_CONFIRM`, `visit_header`, `send_visit_card`, `refresh_visit_card`, and the Task 7 code). Remove the `CANCEL_HINT` import. Add `STAFF_ROLES` import from `bot.handlers.navigation`. Add:

```python
# --- New-visit wizard. Its client/vehicle creation steps live in clients.py
# and vehicles.py; they continue this wizard when wiz_name == "new_visit".


def _choices(rows: list[list[str]], prefix: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for value, label in rows:
        builder.button(text=label, callback_data=f"{prefix}:{value}")
    builder.adjust(1)
    return builder.as_markup()


@wizard.step(NewVisitStates.waiting_for_client_query)
async def client_query_prompt(state: FSMContext, api: ApiClient, user: dict):
    return "Введите телефон или ФИО клиента:", None


@wizard.step(NewVisitStates.choosing_client)
async def choosing_client_prompt(state: FSMContext, api: ApiClient, user: dict):
    return "Выберите клиента:", _choices((await state.get_data())["client_choices"], "client_pick")


@wizard.step(NewVisitStates.waiting_for_vehicle_query)
async def vehicle_query_prompt(state: FSMContext, api: ApiClient, user: dict):
    created = (await state.get_data()).get("created_client")
    prefix = f"Клиент создан: {created}\n" if created else ""
    return f"{prefix}Введите VIN или гос.номер авто:", None


@wizard.step(NewVisitStates.choosing_vehicle)
async def choosing_vehicle_prompt(state: FSMContext, api: ApiClient, user: dict):
    return "Выберите автомобиль:", _choices((await state.get_data())["vehicle_choices"], "vehicle_pick")


@wizard.step(NewVisitStates.waiting_for_mileage)
async def mileage_prompt(state: FSMContext, api: ApiClient, user: dict):
    data = await state.get_data()
    if data.get("owner_name"):
        return f"Новый заезд: {data['owner_name']}. Введите пробег на приёмке:", None
    if data.get("created_vehicle"):
        return f"Автомобиль создан: {data['created_vehicle']}\nВведите пробег на приёмке:", None
    return "Введите пробег на приёмке:", None


@wizard.step(NewVisitStates.confirming_mileage)
async def confirm_mileage_prompt(state: FSMContext, api: ApiClient, user: dict):
    builder = InlineKeyboardBuilder()
    builder.button(text="Подтвердить пробег", callback_data=MILEAGE_CONFIRM)
    return f"{(await state.get_data())['rollback_message']}\nИли введите другой пробег.", builder.as_markup()


@wizard.step(NewVisitStates.choosing_master)
async def choosing_master_prompt(state: FSMContext, api: ApiClient, user: dict):
    return "Выберите мастера:", _choices((await state.get_data())["master_choices"], "master_pick")


@router.callback_query(F.data == actions.NEW_VISIT)
async def start_new_visit(callback: CallbackQuery, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    if user["role"] not in STAFF_ROLES:
        await callback.answer("Недостаточно прав")
        return
    await wizard.start(callback, state, api, user, "new_visit", NewVisitStates.waiting_for_client_query)


@router.callback_query(F.data == actions.NEW_VISIT_FOR)
async def new_visit_for_callback(callback: CallbackQuery, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    if user["role"] not in STAFF_ROLES:
        await callback.answer("Недостаточно прав")
        return
    args = await nav.top_args(callback, state, "vehicle")
    if args is None:
        return
    owner = await api.get_vehicle_owner(args["vehicle_id"])
    if owner is None:
        await callback.answer("У машины нет владельца — заведите заезд через «Новый заезд».", show_alert=True)
        return
    await wizard.start(
        callback, state, api, user, "new_visit", NewVisitStates.waiting_for_mileage,
        client_id=str(owner["id"]), vehicle_id=args["vehicle_id"], owner_name=owner["full_name"],
    )


@router.message(NewVisitStates.waiting_for_client_query)
async def receive_client_query(message: Message, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    if not message.text:
        await wizard.reprompt(message, state, api, user, TEXT_REQUIRED)
        return
    results = await api.search(message.text)
    client_ids = [r["id"] for r in results if r["entity"] == "client"][:5]
    if not client_ids:
        await wizard.goto(message, state, api, user, NewClientStates.waiting_for_phone)
        return
    choices = [[str(cid), (await api.get_client(cid))["full_name"]] for cid in client_ids]
    await state.update_data(client_choices=choices)
    await wizard.goto(message, state, api, user, NewVisitStates.choosing_client)


@router.callback_query(NewVisitStates.choosing_client, F.data.startswith("client_pick:"))
async def choose_client_callback(callback: CallbackQuery, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    await state.update_data(client_id=callback.data.split(":", 1)[1])
    await wizard.goto(callback, state, api, user, NewVisitStates.waiting_for_vehicle_query)


@router.message(NewVisitStates.waiting_for_vehicle_query)
async def receive_vehicle_query(message: Message, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    if not message.text:
        await wizard.reprompt(message, state, api, user, TEXT_REQUIRED)
        return
    results = await api.search(message.text)
    vehicle_ids = [r["id"] for r in results if r["entity"] == "vehicle"][:5]
    if not vehicle_ids:
        await wizard.goto(message, state, api, user, NewVehicleStates.waiting_for_vin)
        return
    choices = [[str(vid), (await api.get_vehicle(vid))["plate_number"]] for vid in vehicle_ids]
    await state.update_data(vehicle_choices=choices)
    await wizard.goto(message, state, api, user, NewVisitStates.choosing_vehicle)


@router.callback_query(NewVisitStates.choosing_vehicle, F.data.startswith("vehicle_pick:"))
async def choose_vehicle_callback(callback: CallbackQuery, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    await state.update_data(vehicle_id=callback.data.split(":", 1)[1])
    await wizard.goto(callback, state, api, user, NewVisitStates.waiting_for_mileage)


@router.message(NewVisitStates.waiting_for_mileage)
@router.message(NewVisitStates.confirming_mileage)
async def receive_mileage(message: Message, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    try:
        mileage = int(message.text)
    except (ValueError, TypeError):
        await wizard.reprompt(message, state, api, user, "Введите число (пробег в км).")
        return
    await state.update_data(mileage=mileage, mileage_confirmed=False)
    await _continue_after_mileage(message, state, api, user)


@router.callback_query(NewVisitStates.confirming_mileage, F.data == MILEAGE_CONFIRM)
async def confirm_mileage_callback(callback: CallbackQuery, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    await state.update_data(mileage_confirmed=True)
    await _continue_after_mileage(callback, state, api, user)


@router.callback_query(NewVisitStates.choosing_master, F.data.startswith("master_pick:"))
async def choose_master_callback(callback: CallbackQuery, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    await state.update_data(assigned_master_id=decode_id(callback.data.split(":", 1)[1]))
    await _create_visit(callback, state, api, user)


async def _continue_after_mileage(event: nav.Event, state: FSMContext, api: ApiClient, user: dict) -> None:
    data = await state.get_data()
    if user["role"] == "admin" and "assigned_master_id" not in data:
        masters = await api.list_masters()
        if not masters:
            await wizard.finish(state)
            await nav.refresh(event, state, api, user, notice="Сначала добавьте мастера через «Добавить сотрудника».")
            return
        await state.update_data(master_choices=[[encode_id(m["id"]), m["full_name"]] for m in masters])
        await wizard.goto(event, state, api, user, NewVisitStates.choosing_master)
        return
    await _create_visit(event, state, api, user)


async def _create_visit(event: nav.Event, state: FSMContext, api: ApiClient, user: dict) -> None:
    """Create the visit from wizard data; a MASTER is always the visit's master, an ADMIN picked one."""
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
        # Everything (incl. the chosen master) is kept until the mileage is
        # confirmed or a different one is typed — also accepted in this step.
        await state.update_data(rollback_message=e.message)
        await wizard.goto(event, state, api, user, NewVisitStates.confirming_mileage)
        return
    await wizard.finish(state)
    await nav.push(event, state, api, user, "visit", {"visit_id": str(visit["id"])})
```

Replace `bot/handlers/clients.py` with:

```python
from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot import nav, wizard
from bot.api_client import ApiClient
from bot.states import NewClientStates, NewVisitStates
from bot.texts import TEXT_REQUIRED

router = Router()


@wizard.step(NewClientStates.waiting_for_phone)
async def phone_prompt(state: FSMContext, api: ApiClient, user: dict):
    if await wizard.name(state) == "new_visit":
        return "Клиент не найден. Введите телефон клиента:", None
    return "Введите телефон клиента:", None


@wizard.step(NewClientStates.waiting_for_full_name)
async def full_name_prompt(state: FSMContext, api: ApiClient, user: dict):
    return "Введите ФИО клиента:", None


@router.message(Command("new_client"))
async def start_new_client(message: Message, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    if user["role"] == "mechanic":
        await message.answer("Недостаточно прав.")
        return
    await wizard.start(message, state, api, user, "new_client", NewClientStates.waiting_for_phone)


@router.message(NewClientStates.waiting_for_phone)
async def receive_phone(message: Message, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    if not message.text:
        await wizard.reprompt(message, state, api, user, TEXT_REQUIRED)
        return
    await state.update_data(phone=message.text)
    await wizard.goto(message, state, api, user, NewClientStates.waiting_for_full_name)


@router.message(NewClientStates.waiting_for_full_name)
async def receive_full_name(message: Message, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    if not message.text:
        await wizard.reprompt(message, state, api, user, TEXT_REQUIRED)
        return
    data = await state.get_data()
    client = await api.create_client(full_name=message.text, phone=data["phone"])
    if await wizard.name(state) == "new_visit":
        await state.update_data(client_id=str(client["id"]), created_client=client["full_name"])
        await wizard.goto(message, state, api, user, NewVisitStates.waiting_for_vehicle_query, commit=True)
        return
    await wizard.finish(state)
    await nav.home(message, state, api, user, notice=f"Клиент создан: {client['full_name']}")
```

Replace `bot/handlers/vehicles.py` with:

```python
from datetime import date

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot import nav, wizard
from bot.api_client import ApiClient
from bot.states import NewVehicleStates, NewVisitStates
from bot.texts import TEXT_REQUIRED

router = Router()


@wizard.step(NewVehicleStates.waiting_for_vin)
async def vin_prompt(state: FSMContext, api: ApiClient, user: dict):
    if await wizard.name(state) == "new_visit":
        return "Автомобиль не найден. Введите VIN:", None
    return "Введите VIN:", None


@wizard.step(NewVehicleStates.waiting_for_plate)
async def plate_prompt(state: FSMContext, api: ApiClient, user: dict):
    return "Введите гос.номер:", None


@wizard.step(NewVehicleStates.waiting_for_make_model)
async def make_model_prompt(state: FSMContext, api: ApiClient, user: dict):
    return "Введите марку и модель через пробел (например: Toyota Camry):", None


@router.message(Command("new_vehicle"))
async def start_new_vehicle(message: Message, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    if user["role"] == "mechanic":
        await message.answer("Недостаточно прав.")
        return
    await wizard.start(message, state, api, user, "new_vehicle", NewVehicleStates.waiting_for_vin)


@router.message(NewVehicleStates.waiting_for_vin)
async def receive_vin(message: Message, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    if not message.text:
        await wizard.reprompt(message, state, api, user, TEXT_REQUIRED)
        return
    await state.update_data(vin=message.text)
    await wizard.goto(message, state, api, user, NewVehicleStates.waiting_for_plate)


@router.message(NewVehicleStates.waiting_for_plate)
async def receive_plate(message: Message, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    if not message.text:
        await wizard.reprompt(message, state, api, user, TEXT_REQUIRED)
        return
    await state.update_data(plate_number=message.text)
    await wizard.goto(message, state, api, user, NewVehicleStates.waiting_for_make_model)


@router.message(NewVehicleStates.waiting_for_make_model)
async def receive_make_model(message: Message, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    if not message.text:
        await wizard.reprompt(message, state, api, user, TEXT_REQUIRED)
        return
    make, _, model = message.text.partition(" ")
    data = await state.get_data()
    vehicle = await api.create_vehicle(vin=data["vin"], plate_number=data["plate_number"], make=make, model=model)
    if await wizard.name(state) == "new_visit":
        await api.attach_owner(vehicle["id"], data["client_id"], date_from=date.today().isoformat())
        await state.update_data(vehicle_id=str(vehicle["id"]), created_vehicle=vehicle["vin"])
        await wizard.goto(message, state, api, user, NewVisitStates.waiting_for_mileage, commit=True)
        return
    await wizard.finish(state)
    await nav.home(message, state, api, user, notice=f"Автомобиль создан: {vehicle['vin']}")
```

- [ ] **Step 4: Run, expect PASS**

Run: `.venv/bin/pytest tests/bot -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add -A bot tests/bot
git commit -m "feat(bot): new-visit wizard with step-back; client/vehicle creation as its steps

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Add-work and add-part wizards; delete the old card

**Files:**
- Modify: `bot/handlers/work_items.py` (replace the add-work wizard section)
- Rewrite: `bot/handlers/part_items.py`
- Modify: `bot/handlers/visits.py` (delete `send_visit_card`, `refresh_visit_card`)
- Modify: `bot/work_item_status.py` (delete `add_work_status_buttons`, `FROM_VISIT_CARD`, `FROM_MY_WORK_ITEMS`, and the now-unused `InlineKeyboardBuilder`/`encode_id` imports)
- Modify: `bot/states.py` (delete unused `AddPartItemStates.choosing_work_item`)
- Rewrite: `tests/bot/test_work_items_handler.py`, `tests/bot/test_part_items_handler.py`

**Interfaces:**
- Consumes: `wizard.*`, `nav.top_args/refresh`, `actions.ADD_WORK`, `actions.ADD_PART`, screens `visit`, `work`.
- Produces: wizard names `"add_work"`, `"add_part"`. Callback data kept: `catalog_pick:<id|none>`, `category_pick:<value>`, `assign_mech:<enc|none>`. FSM keys: `visit_id`, `work_item_id`, `free_text_name`, `suggestions: dict[id, item]`, `catalog_item_id`, `category`, `norm_hours`, `hourly_rate`, `mechanic_choices: list[[enc id, name]]`, `name`.

- [ ] **Step 1: Write the failing tests** — replace `tests/bot/test_work_items_handler.py` with:

```python
from unittest.mock import AsyncMock

from bot import wizard
from bot.callback_ids import encode_id
from bot.handlers.work_items import (
    choose_catalog_callback,
    choose_category_callback,
    choose_mechanic_callback,
    receive_hours_and_rate,
    receive_work_name,
    start_add_work_item,
)
from bot.states import AddWorkItemStates
from tests.bot.helpers import MASTER, buttons, fsm_context, make_callback, make_message, on_screens, shown

VISIT = "11111111-1111-1111-1111-111111111111"
MECH = "33333333-3333-3333-3333-333333333333"
SUGGESTION = {"id": "cat1", "name": "Замена масла", "category": "maintenance", "default_norm_hours": 1.0}


def _api():
    api = AsyncMock()
    api.get_visit.return_value = {"id": VISIT, "status": "in_progress", "total_amount": 0, "plate_number": "А1"}
    api.list_work_items.return_value = []
    api.suggest_catalog.return_value = [SUGGESTION]
    api.list_mechanics.return_value = [{"id": MECH, "full_name": "Петров"}]
    return api


async def _at(state, step, **data):
    await on_screens(state, ("visit", {"visit_id": VISIT}))
    await state.set_state(step)
    await state.update_data(wiz_name="add_work", wiz_steps=[], visit_id=VISIT, **data)


async def test_start_from_visit_card_asks_for_name():
    state = fsm_context()
    await on_screens(state, ("visit", {"visit_id": VISIT}))
    callback = make_callback("act:add_work")

    await start_add_work_item(callback, state, api=_api(), user=MASTER)

    assert await state.get_state() == AddWorkItemStates.waiting_for_name.state
    assert (await state.get_data())["visit_id"] == VISIT
    assert shown(callback)[0] == "Введите название работы:"


async def test_name_offers_catalog_suggestions():
    state = fsm_context()
    await _at(state, AddWorkItemStates.waiting_for_name)
    api = _api()
    message = make_message("замена масла")

    await receive_work_name(message, state, api=api, user=MASTER)

    api.suggest_catalog.assert_awaited_once_with("замена масла")
    text, markup = shown(message)
    assert text == "Выберите работу из справочника или укажите свою:"
    assert buttons(markup)[:2] == [("Замена масла", "catalog_pick:cat1"), ("Своя формулировка", "catalog_pick:none")]


async def test_catalog_pick_asks_only_rate():
    state = fsm_context()
    await _at(state, AddWorkItemStates.choosing_suggestion, suggestions={"cat1": SUGGESTION}, free_text_name="масло")
    callback = make_callback("catalog_pick:cat1")

    await choose_catalog_callback(callback, state, api=_api(), user=MASTER)

    data = await state.get_data()
    assert (data["catalog_item_id"], data["category"], data["norm_hours"]) == ("cat1", "maintenance", 1.0)
    assert shown(callback)[0] == "Введите часовую ставку:"


async def test_back_from_rate_then_own_wording_asks_hours_and_rate():
    state = fsm_context()
    await _at(state, AddWorkItemStates.choosing_suggestion, suggestions={"cat1": SUGGESTION}, free_text_name="масло")
    api = _api()
    await choose_catalog_callback(make_callback("catalog_pick:cat1"), state, api=api, user=MASTER)
    await wizard.back_callback(make_callback("wiz_back"), state, api=api, user=MASTER)
    await choose_catalog_callback(make_callback("catalog_pick:none"), state, api=api, user=MASTER)
    callback = make_callback("category_pick:body")

    await choose_category_callback(callback, state, api=api, user=MASTER)

    assert (await state.get_data())["catalog_item_id"] is None
    assert shown(callback)[0] == "Введите нормо-часы и ставку через пробел (например: 1.5 800):"


async def test_rate_then_mechanic_choice_then_create_and_back_to_card():
    state = fsm_context()
    await _at(state, AddWorkItemStates.waiting_for_hours_and_rate, catalog_item_id="cat1", category="maintenance", norm_hours=1.0)
    api = _api()
    message = make_message("1500")

    await receive_hours_and_rate(message, state, api=api, user=MASTER)

    assert buttons(shown(message)[1])[:2] == [("Петров", f"assign_mech:{encode_id(MECH)}"), ("Без исполнителя", "assign_mech:none")]

    callback = make_callback(f"assign_mech:{encode_id(MECH)}")
    await choose_mechanic_callback(callback, state, api=api, user=MASTER)

    api.add_work_item.assert_awaited_once_with(
        VISIT, catalog_item_id="cat1", free_text_name=None, category="maintenance",
        norm_hours=1.0, hourly_rate=1500.0, assigned_mechanic_id=MECH,
    )
    assert await state.get_state() is None
    assert (await state.get_data())["nav_stack"][-1] == ["visit", {"visit_id": VISIT}]


async def test_free_text_path_parses_hours_and_rate_and_unassigned():
    state = fsm_context()
    await _at(state, AddWorkItemStates.waiting_for_hours_and_rate, catalog_item_id=None, free_text_name="Покраска", category="body")
    api = _api()
    await receive_hours_and_rate(make_message("1.5 800"), state, api=api, user=MASTER)

    await choose_mechanic_callback(make_callback("assign_mech:none"), state, api=api, user=MASTER)

    kwargs = api.add_work_item.await_args.kwargs
    assert (kwargs["free_text_name"], kwargs["norm_hours"], kwargs["hourly_rate"], kwargs["assigned_mechanic_id"]) == (
        "Покраска", 1.5, 800.0, None,
    )


async def test_no_mechanics_creates_immediately():
    state = fsm_context()
    await _at(state, AddWorkItemStates.waiting_for_hours_and_rate, catalog_item_id="cat1", category="maintenance", norm_hours=1.0)
    api = _api()
    api.list_mechanics.return_value = []

    await receive_hours_and_rate(make_message("1500"), state, api=api, user=MASTER)

    assert api.add_work_item.await_args.kwargs["assigned_mechanic_id"] is None


async def test_bad_rate_and_bad_pair_reprompt():
    state = fsm_context()
    await _at(state, AddWorkItemStates.waiting_for_hours_and_rate, catalog_item_id="cat1", category="maintenance", norm_hours=1.0)
    message = make_message("дорого")
    await receive_hours_and_rate(message, state, api=_api(), user=MASTER)
    assert shown(message)[0] == "Введите число (часовую ставку).\n\nВведите часовую ставку:"

    await state.update_data(catalog_item_id=None)
    message = make_message("полтора")
    await receive_hours_and_rate(message, state, api=_api(), user=MASTER)
    assert shown(message)[0].startswith("Введите нормо-часы и ставку через пробел, например: 1.5 800.\n\n")


async def test_name_must_be_text():
    state = fsm_context()
    await _at(state, AddWorkItemStates.waiting_for_name)
    message = make_message(None)

    await receive_work_name(message, state, api=_api(), user=MASTER)

    assert shown(message)[0] == "Пожалуйста, отправьте ответ текстом.\n\nВведите название работы:"
```

Replace `tests/bot/test_part_items_handler.py` with:

```python
from unittest.mock import AsyncMock

from bot.handlers.part_items import receive_part_name, receive_quantity_and_price, start_add_part_item
from bot.states import AddPartItemStates
from tests.bot.helpers import MASTER, fsm_context, make_callback, make_message, on_screens, shown

VISIT = "11111111-1111-1111-1111-111111111111"
ITEM = "22222222-2222-2222-2222-222222222222"
WORK = ("work", {"visit_id": VISIT, "item_id": ITEM})


def _api():
    api = AsyncMock()
    api.get_visit.return_value = {"id": VISIT, "status": "in_progress", "total_amount": 0}
    api.list_work_items.return_value = [
        {"id": ITEM, "name": "Замена масла", "status": "in_progress", "approved_by_client": True, "assigned_mechanic_name": None},
    ]
    return api


async def test_start_from_work_screen_asks_for_name():
    state = fsm_context()
    await on_screens(state, WORK)
    callback = make_callback("act:add_part")

    await start_add_part_item(callback, state, api=_api(), user=MASTER)

    data = await state.get_data()
    assert (data["visit_id"], data["work_item_id"]) == (VISIT, ITEM)
    assert shown(callback)[0] == "Введите название запчасти:"


async def test_name_then_quantity_and_price_creates_and_returns_to_work():
    state = fsm_context()
    await on_screens(state, WORK)
    await state.set_state(AddPartItemStates.waiting_for_name)
    await state.update_data(wiz_name="add_part", wiz_steps=[], visit_id=VISIT, work_item_id=ITEM)
    api = _api()

    message = make_message("Фильтр")
    await receive_part_name(message, state, api=api, user=MASTER)
    assert shown(message)[0] == "Введите количество и цену через пробел (например: 2 350):"

    await receive_quantity_and_price(make_message("2 350"), state, api=api, user=MASTER)

    api.add_part_item.assert_awaited_once_with(visit_id=VISIT, work_item_id=ITEM, name="Фильтр", quantity=2, unit_price=350.0)
    assert await state.get_state() is None
    assert (await state.get_data())["nav_stack"][-1] == list(WORK)


async def test_malformed_quantity_reprompts():
    state = fsm_context()
    await on_screens(state, WORK)
    await state.set_state(AddPartItemStates.waiting_for_quantity_and_price)
    await state.update_data(wiz_name="add_part", wiz_steps=[], visit_id=VISIT, work_item_id=ITEM, name="Фильтр")
    message = make_message("две")

    await receive_quantity_and_price(message, state, api=_api(), user=MASTER)

    assert shown(message)[0].startswith("Введите количество и цену через пробел, например: 2 350.\n\n")


async def test_part_name_must_be_text():
    state = fsm_context()
    await state.set_state(AddPartItemStates.waiting_for_name)
    await state.update_data(wiz_name="add_part", wiz_steps=[])
    message = make_message(None)

    await receive_part_name(message, state, api=_api(), user=MASTER)

    assert shown(message)[0] == "Пожалуйста, отправьте ответ текстом.\n\nВведите название запчасти:"
```

- [ ] **Step 2: Run, expect FAIL**

Run: `.venv/bin/pytest tests/bot/test_work_items_handler.py tests/bot/test_part_items_handler.py -q`
Expected: FAIL (e.g. `start_add_work_item` reads `callback.data.split(":")` → `ValueError`, or prompt text mismatch).

- [ ] **Step 3: Implement**

In `bot/handlers/work_items.py`, delete `start_add_work_item`, `receive_work_name`, `choose_catalog_callback`, `choose_category_callback`, `receive_hours_and_rate`, `choose_mechanic_callback`, `_create_work_item`, and the imports of `refresh_visit_card` and `CANCEL_HINT`. Add `from bot import wizard`. Keep `_CATEGORY_LABELS`. Add:

```python
# --- Add-work wizard (started from the visit card).


@wizard.step(AddWorkItemStates.waiting_for_name)
async def work_name_prompt(state: FSMContext, api: ApiClient, user: dict):
    return "Введите название работы:", None


@wizard.step(AddWorkItemStates.choosing_suggestion)
async def suggestion_prompt(state: FSMContext, api: ApiClient, user: dict):
    builder = InlineKeyboardBuilder()
    for item in (await state.get_data())["suggestions"].values():
        builder.button(text=item["name"], callback_data=f"catalog_pick:{item['id']}")
    builder.button(text="Своя формулировка", callback_data="catalog_pick:none")
    builder.adjust(1)
    return "Выберите работу из справочника или укажите свою:", builder.as_markup()


@wizard.step(AddWorkItemStates.choosing_category)
async def category_prompt(state: FSMContext, api: ApiClient, user: dict):
    builder = InlineKeyboardBuilder()
    for label, value in _CATEGORY_LABELS.items():
        builder.button(text=label, callback_data=f"category_pick:{value}")
    builder.adjust(1)
    return "Выберите категорию работы:", builder.as_markup()


@wizard.step(AddWorkItemStates.waiting_for_hours_and_rate)
async def hours_and_rate_prompt(state: FSMContext, api: ApiClient, user: dict):
    if (await state.get_data()).get("catalog_item_id"):
        return "Введите часовую ставку:", None
    return "Введите нормо-часы и ставку через пробел (например: 1.5 800):", None


@wizard.step(AddWorkItemStates.choosing_mechanic)
async def mechanic_prompt(state: FSMContext, api: ApiClient, user: dict):
    builder = InlineKeyboardBuilder()
    for value, name in (await state.get_data())["mechanic_choices"]:
        builder.button(text=name, callback_data=f"assign_mech:{value}")
    builder.button(text="Без исполнителя", callback_data="assign_mech:none")
    builder.adjust(1)
    return "Кому назначить работу?", builder.as_markup()


@router.callback_query(F.data == actions.ADD_WORK)
async def start_add_work_item(callback: CallbackQuery, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    args = await nav.top_args(callback, state, "visit")
    if args is None:
        return
    await wizard.start(callback, state, api, user, "add_work", AddWorkItemStates.waiting_for_name, visit_id=args["visit_id"])


@router.message(AddWorkItemStates.waiting_for_name)
async def receive_work_name(message: Message, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    if message.text is None:
        await wizard.reprompt(message, state, api, user, TEXT_REQUIRED)
        return
    suggestions = await api.suggest_catalog(message.text)
    await state.update_data(free_text_name=message.text, suggestions={str(item["id"]): item for item in suggestions})
    await wizard.goto(message, state, api, user, AddWorkItemStates.choosing_suggestion)


@router.callback_query(AddWorkItemStates.choosing_suggestion, F.data.startswith("catalog_pick:"))
async def choose_catalog_callback(callback: CallbackQuery, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    picked = callback.data.split(":", 1)[1]
    if picked == "none":
        # Forget an earlier catalog pick (the user may have come back here).
        await state.update_data(catalog_item_id=None, norm_hours=None)
        await wizard.goto(callback, state, api, user, AddWorkItemStates.choosing_category)
        return
    suggestion = (await state.get_data())["suggestions"][picked]
    await state.update_data(catalog_item_id=picked, category=suggestion["category"], norm_hours=suggestion["default_norm_hours"])
    await wizard.goto(callback, state, api, user, AddWorkItemStates.waiting_for_hours_and_rate)


@router.callback_query(AddWorkItemStates.choosing_category, F.data.startswith("category_pick:"))
async def choose_category_callback(callback: CallbackQuery, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    await state.update_data(category=callback.data.split(":", 1)[1])
    await wizard.goto(callback, state, api, user, AddWorkItemStates.waiting_for_hours_and_rate)


@router.message(AddWorkItemStates.waiting_for_hours_and_rate)
async def receive_hours_and_rate(message: Message, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    if message.text is None:
        await wizard.reprompt(message, state, api, user, TEXT_REQUIRED)
        return
    from_catalog = bool((await state.get_data()).get("catalog_item_id"))
    try:
        if from_catalog:
            norm_hours = (await state.get_data())["norm_hours"]
            hourly_rate = float(message.text)
        else:
            norm_hours_text, hourly_rate_text = message.text.split()
            norm_hours, hourly_rate = float(norm_hours_text), float(hourly_rate_text)
    except (ValueError, TypeError):
        error = "Введите число (часовую ставку)." if from_catalog else "Введите нормо-часы и ставку через пробел, например: 1.5 800."
        await wizard.reprompt(message, state, api, user, error)
        return
    await state.update_data(norm_hours=norm_hours, hourly_rate=hourly_rate)
    mechanics = await api.list_mechanics()
    if not mechanics:
        await _create_work_item(message, state, api, user, assigned_mechanic_id=None)
        return
    await state.update_data(mechanic_choices=[[encode_id(m["id"]), m["full_name"]] for m in mechanics])
    await wizard.goto(message, state, api, user, AddWorkItemStates.choosing_mechanic)


@router.callback_query(AddWorkItemStates.choosing_mechanic, F.data.startswith("assign_mech:"))
async def choose_mechanic_callback(callback: CallbackQuery, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    picked = callback.data.split(":", 1)[1]
    await _create_work_item(callback, state, api, user, assigned_mechanic_id=None if picked == "none" else decode_id(picked))


async def _create_work_item(event: nav.Event, state: FSMContext, api: ApiClient, user: dict, assigned_mechanic_id: str | None) -> None:
    data = await state.get_data()
    await api.add_work_item(
        data["visit_id"],
        catalog_item_id=data.get("catalog_item_id"),
        free_text_name=None if data.get("catalog_item_id") else data["free_text_name"],
        category=data["category"],
        norm_hours=data["norm_hours"],
        hourly_rate=data["hourly_rate"],
        assigned_mechanic_id=assigned_mechanic_id,
    )
    await wizard.finish(state)
    await nav.refresh(event, state, api, user)  # the visit card, now with the new item
```

Replace `bot/handlers/part_items.py` with:

```python
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot import actions, nav, wizard
from bot.api_client import ApiClient
from bot.states import AddPartItemStates
from bot.texts import TEXT_REQUIRED

router = Router()


@wizard.step(AddPartItemStates.waiting_for_name)
async def part_name_prompt(state: FSMContext, api: ApiClient, user: dict):
    return "Введите название запчасти:", None


@wizard.step(AddPartItemStates.waiting_for_quantity_and_price)
async def quantity_and_price_prompt(state: FSMContext, api: ApiClient, user: dict):
    return "Введите количество и цену через пробел (например: 2 350):", None


@router.callback_query(F.data == actions.ADD_PART)
async def start_add_part_item(callback: CallbackQuery, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    args = await nav.top_args(callback, state, "work")
    if args is None:
        return
    await wizard.start(
        callback, state, api, user, "add_part", AddPartItemStates.waiting_for_name,
        visit_id=args["visit_id"], work_item_id=args["item_id"],
    )


@router.message(AddPartItemStates.waiting_for_name)
async def receive_part_name(message: Message, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    if message.text is None:
        await wizard.reprompt(message, state, api, user, TEXT_REQUIRED)
        return
    await state.update_data(name=message.text)
    await wizard.goto(message, state, api, user, AddPartItemStates.waiting_for_quantity_and_price)


@router.message(AddPartItemStates.waiting_for_quantity_and_price)
async def receive_quantity_and_price(message: Message, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    if message.text is None:
        await wizard.reprompt(message, state, api, user, TEXT_REQUIRED)
        return
    try:
        quantity_str, price_str = message.text.split()
        quantity = int(quantity_str)
        unit_price = float(price_str)
    except (ValueError, TypeError):
        await wizard.reprompt(message, state, api, user, "Введите количество и цену через пробел, например: 2 350.")
        return
    data = await state.get_data()
    await api.add_part_item(
        visit_id=data["visit_id"], work_item_id=data["work_item_id"], name=data["name"],
        quantity=quantity, unit_price=unit_price,
    )
    await wizard.finish(state)
    await nav.refresh(message, state, api, user)  # back on the work screen
```

In `bot/handlers/visits.py` delete `send_visit_card` and `refresh_visit_card`, and the now-unused imports `FROM_VISIT_CARD`, `add_work_status_buttons`, `ApiClient`-unrelated leftovers (run `grep -n "FROM_\|add_work_status_buttons\|send_visit_card\|refresh_visit_card" -r bot tests` → must print nothing). In `bot/work_item_status.py` delete `FROM_VISIT_CARD`, `FROM_MY_WORK_ITEMS`, `add_work_status_buttons` and their imports; update the module docstring's first line to `"""Work-item status labels, icons and the MVP next-status flow."""`. In `bot/states.py` delete `choosing_work_item = State()` from `AddPartItemStates`.

- [ ] **Step 4: Run, expect PASS**

Run: `.venv/bin/pytest tests/bot -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add -A bot tests/bot
git commit -m "feat(bot): add-work and add-part wizards on the stack; drop the old card

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: Staff and paper-consent wizards

**Files:**
- Rewrite: `bot/handlers/admin.py`, `bot/handlers/consent.py`
- Rewrite: `tests/bot/test_admin_handler.py`, `tests/bot/test_consent_handler.py`

**Interfaces:**
- Consumes: `wizard.*`, `nav.home`, `actions.NEW_STAFF`, `actions.PAPER_CONSENT`.
- Produces: wizard names `"new_staff"`, `"paper_consent"`. Callback data kept: `staff_role:<admin|master|mechanic>`.

- [ ] **Step 1: Write the failing tests**

`tests/bot/test_admin_handler.py`:

```python
from unittest.mock import AsyncMock

from bot.handlers.admin import choose_staff_role, receive_staff_full_name, receive_telegram_id, start_new_staff
from bot.states import NewStaffStates
from tests.bot.helpers import ADMIN, MASTER, buttons, fsm_context, make_callback, make_message, on_screens, shown


async def test_start_offers_roles_in_russian():
    state = fsm_context()
    await on_screens(state)
    callback = make_callback("wiz:new_staff")

    await start_new_staff(callback, state, api=AsyncMock(), user=ADMIN)

    text, markup = shown(callback)
    assert text == "Выберите роль:"
    assert buttons(markup)[:3] == [
        ("Администратор", "staff_role:admin"), ("Мастер", "staff_role:master"), ("Механик", "staff_role:mechanic"),
    ]


async def test_start_refused_for_master():
    state = fsm_context()
    callback = make_callback("wiz:new_staff")

    await start_new_staff(callback, state, api=AsyncMock(), user=MASTER)

    assert await state.get_state() is None
    callback.answer.assert_awaited_once_with("Недостаточно прав")


async def _at(state, step, **data):
    await on_screens(state)
    await state.set_state(step)
    await state.update_data(wiz_name="new_staff", wiz_steps=[], **data)


async def test_role_then_name_then_id_creates_user_and_shows_menu():
    state = fsm_context()
    await _at(state, NewStaffStates.choosing_role)
    api = AsyncMock()
    api.create_staff_user.return_value = {"full_name": "Сидоров"}

    callback = make_callback("staff_role:mechanic")
    await choose_staff_role(callback, state, api=api, user=ADMIN)
    assert shown(callback)[0] == "Введите ФИО сотрудника:"

    message = make_message("Сидоров")
    await receive_staff_full_name(message, state, api=api, user=ADMIN)
    assert shown(message)[0] == "Введите Telegram ID сотрудника (или «-», если пока неизвестен):"

    message = make_message("12345")
    await receive_telegram_id(message, state, api=api, user=ADMIN)

    api.create_staff_user.assert_awaited_once_with(role="mechanic", full_name="Сидоров", telegram_id=12345)
    assert shown(message)[0] == "Сотрудник создан: Сидоров\n\nГлавное меню"
    assert await state.get_state() is None


async def test_dash_means_no_telegram_id():
    state = fsm_context()
    await _at(state, NewStaffStates.waiting_for_telegram_id, role="master", full_name="Петров")
    api = AsyncMock()
    api.create_staff_user.return_value = {"full_name": "Петров"}

    await receive_telegram_id(make_message("-"), state, api=api, user=ADMIN)

    assert api.create_staff_user.await_args.kwargs["telegram_id"] is None


async def test_non_numeric_id_reprompts():
    state = fsm_context()
    await _at(state, NewStaffStates.waiting_for_telegram_id, role="master", full_name="Петров")
    api = AsyncMock()
    message = make_message("abc")

    await receive_telegram_id(message, state, api=api, user=ADMIN)

    api.create_staff_user.assert_not_awaited()
    assert shown(message)[0].startswith("Telegram ID должен быть числом или «-».\n\n")
```

`tests/bot/test_consent_handler.py`:

```python
from unittest.mock import AsyncMock

from bot.handlers.consent import receive_paper_full_name, receive_paper_phone, start_paper_consent
from bot.states import PaperConsentStates
from tests.bot.helpers import MASTER, MECHANIC, fsm_context, make_callback, make_message, on_screens, shown


async def test_start_asks_for_phone():
    state = fsm_context()
    await on_screens(state)
    callback = make_callback("wiz:paper_consent")

    await start_paper_consent(callback, state, api=AsyncMock(), user=MASTER)

    assert await state.get_state() == PaperConsentStates.waiting_for_phone.state
    assert shown(callback)[0] == "Введите телефон клиента:"


async def test_start_refused_for_mechanic():
    callback = make_callback("wiz:paper_consent")

    await start_paper_consent(callback, fsm_context(), api=AsyncMock(), user=MECHANIC)

    callback.answer.assert_awaited_once_with("Недостаточно прав")


async def test_phone_then_name_registers_and_shows_menu():
    state = fsm_context()
    await on_screens(state)
    await state.set_state(PaperConsentStates.waiting_for_phone)
    await state.update_data(wiz_name="paper_consent", wiz_steps=[])
    api = AsyncMock()

    message = make_message("79990000000")
    await receive_paper_phone(message, state, api=api, user=MASTER)
    assert shown(message)[0] == "Введите ФИО клиента:"

    message = make_message("Иван Иванов")
    await receive_paper_full_name(message, state, api=api, user=MASTER)

    api.register_paper_consent.assert_awaited_once_with(full_name="Иван Иванов", phone="79990000000")
    assert shown(message)[0] == "Клиент зарегистрирован (бумажное согласие): Иван Иванов\n\nГлавное меню"
```

- [ ] **Step 2: Run, expect FAIL**

Run: `.venv/bin/pytest tests/bot/test_admin_handler.py tests/bot/test_consent_handler.py -q`
Expected: FAIL — `ImportError` / signature mismatch.

- [ ] **Step 3: Implement**

Replace `bot/handlers/admin.py` with:

```python
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot import actions, nav, wizard
from bot.api_client import ApiClient
from bot.states import NewStaffStates
from bot.texts import TEXT_REQUIRED

router = Router()

_ROLE_LABELS = {"admin": "Администратор", "master": "Мастер", "mechanic": "Механик"}


@wizard.step(NewStaffStates.choosing_role)
async def role_prompt(state: FSMContext, api: ApiClient, user: dict):
    builder = InlineKeyboardBuilder()
    for role, label in _ROLE_LABELS.items():
        builder.button(text=label, callback_data=f"staff_role:{role}")
    builder.adjust(1)
    return "Выберите роль:", builder.as_markup()


@wizard.step(NewStaffStates.waiting_for_full_name)
async def staff_name_prompt(state: FSMContext, api: ApiClient, user: dict):
    return "Введите ФИО сотрудника:", None


@wizard.step(NewStaffStates.waiting_for_telegram_id)
async def telegram_id_prompt(state: FSMContext, api: ApiClient, user: dict):
    return "Введите Telegram ID сотрудника (или «-», если пока неизвестен):", None


@router.callback_query(F.data == actions.NEW_STAFF)
async def start_new_staff(callback: CallbackQuery, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    if user["role"] != "admin":
        await callback.answer("Недостаточно прав")
        return
    await wizard.start(callback, state, api, user, "new_staff", NewStaffStates.choosing_role)


@router.callback_query(NewStaffStates.choosing_role, F.data.startswith("staff_role:"))
async def choose_staff_role(callback: CallbackQuery, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    await state.update_data(role=callback.data.split(":", 1)[1])
    await wizard.goto(callback, state, api, user, NewStaffStates.waiting_for_full_name)


@router.message(NewStaffStates.waiting_for_full_name)
async def receive_staff_full_name(message: Message, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    if not message.text:
        await wizard.reprompt(message, state, api, user, TEXT_REQUIRED)
        return
    await state.update_data(full_name=message.text)
    await wizard.goto(message, state, api, user, NewStaffStates.waiting_for_telegram_id)


@router.message(NewStaffStates.waiting_for_telegram_id)
async def receive_telegram_id(message: Message, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    text = (message.text or "").strip()
    if text == "-":
        telegram_id = None
    else:
        try:
            telegram_id = int(text)
        except ValueError:
            await wizard.reprompt(message, state, api, user, "Telegram ID должен быть числом или «-».")
            return
    data = await state.get_data()
    staff = await api.create_staff_user(role=data["role"], full_name=data["full_name"], telegram_id=telegram_id)
    await wizard.finish(state)
    await nav.home(message, state, api, user, notice=f"Сотрудник создан: {staff['full_name']}")
```

Replace `bot/handlers/consent.py` with:

```python
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot import actions, nav, wizard
from bot.api_client import ApiClient
from bot.handlers.navigation import STAFF_ROLES
from bot.states import PaperConsentStates
from bot.texts import TEXT_REQUIRED

router = Router()


@wizard.step(PaperConsentStates.waiting_for_phone)
async def paper_phone_prompt(state: FSMContext, api: ApiClient, user: dict):
    return "Введите телефон клиента:", None


@wizard.step(PaperConsentStates.waiting_for_full_name)
async def paper_name_prompt(state: FSMContext, api: ApiClient, user: dict):
    return "Введите ФИО клиента:", None


@router.callback_query(F.data == actions.PAPER_CONSENT)
async def start_paper_consent(callback: CallbackQuery, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    if user["role"] not in STAFF_ROLES:
        await callback.answer("Недостаточно прав")
        return
    await wizard.start(callback, state, api, user, "paper_consent", PaperConsentStates.waiting_for_phone)


@router.message(PaperConsentStates.waiting_for_phone)
async def receive_paper_phone(message: Message, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    if not message.text:
        await wizard.reprompt(message, state, api, user, TEXT_REQUIRED)
        return
    await state.update_data(phone=message.text)
    await wizard.goto(message, state, api, user, PaperConsentStates.waiting_for_full_name)


@router.message(PaperConsentStates.waiting_for_full_name)
async def receive_paper_full_name(message: Message, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    if not message.text:
        await wizard.reprompt(message, state, api, user, TEXT_REQUIRED)
        return
    phone = (await state.get_data())["phone"]
    await api.register_paper_consent(full_name=message.text, phone=phone)
    await wizard.finish(state)
    await nav.home(message, state, api, user, notice=f"Клиент зарегистрирован (бумажное согласие): {message.text}")
```

- [ ] **Step 4: Run, expect PASS**

Run: `.venv/bin/pytest tests/bot -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add -A bot tests/bot
git commit -m "feat(bot): staff and paper-consent wizards start from the inline menu

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 11: Search screens

**Files:**
- Rewrite: `bot/handlers/search.py`
- Rewrite: `tests/bot/test_search_handler.py`
- Modify: `tests/bot/test_routing.py` (replace `test_search_page_button_routes_to_search_not_stale_fallback`)

**Interfaces:**
- Consumes: `nav.screen/push/replace_top/top_args/go_data`, `actions.SEARCH_PAGE`.
- Produces: screens `search`, `search_results` (args `{"query": str, "page": int}`; pushed only by text input, never by `go:`). `SEARCH_RESULTS_LIMIT = 10`.

- [ ] **Step 1: Write the failing tests** — replace `tests/bot/test_search_handler.py` with:

```python
from unittest.mock import AsyncMock

from bot.callback_ids import encode_id
from bot.handlers.search import SEARCH_RESULTS_LIMIT, receive_search_query, render_search, render_search_results, search_page_callback
from tests.bot.helpers import MASTER, MECHANIC, buttons, fsm_context, make_callback, make_message, on_screens, shown

C1 = "11111111-1111-1111-1111-111111111111"
V1 = "22222222-2222-2222-2222-222222222222"


def _vehicles(n):
    return [{"entity": "vehicle", "id": f"{i:08d}-0000-0000-0000-000000000000", "matched_field": "make"} for i in range(n)]


def _api(results):
    api = AsyncMock()
    api.search.return_value = results
    api.get_client.return_value = {"id": C1, "full_name": "Иван Иванов", "phone_display": "+7 999 123-45-67"}
    api.get_vehicle.return_value = {"id": V1, "make": "Toyota", "model": "Camry", "plate_number": "А123ВС77"}
    return api


async def test_search_prompt_depends_on_role():
    assert (await render_search(AsyncMock(), MASTER, {}))[0] == "Введите телефон, VIN, гос.номер или имя клиента:"
    assert (await render_search(AsyncMock(), MECHANIC, {}))[0] == "Введите VIN или гос.номер:"


async def test_typed_text_pushes_results_screen():
    state = fsm_context()
    await on_screens(state, ("search", {}))
    api = _api([{"entity": "client", "id": C1}, {"entity": "vehicle", "id": V1}])
    message = make_message("Иванов")

    await receive_search_query(message, state, api=api, user=MASTER)

    assert (await state.get_data())["nav_stack"][-1] == ["search_results", {"query": "Иванов", "page": 0}]
    text, markup = shown(message)
    assert text == "Найдено: 2"
    assert buttons(markup)[:2] == [
        ("👤 Иван Иванов — +7 999 123-45-67", f"go:client:{encode_id(C1)}"),
        ("🚗 Toyota Camry (А123ВС77)", f"go:vehicle:{encode_id(V1)}"),
    ]


async def test_results_over_limit_show_first_page_with_next():
    text, markup = await render_search_results(_api(_vehicles(12)), MASTER, {"query": "Toyota", "page": 0})

    assert text == "Найдено: 12 · стр. 1/2\nМожно уточнить запрос."
    assert len(buttons(markup)) == SEARCH_RESULTS_LIMIT + 1
    assert buttons(markup)[-1] == ("Далее ›", "act:spage:1")


async def test_middle_page_has_both_arrows_in_one_row():
    _, markup = await render_search_results(_api(_vehicles(25)), MASTER, {"query": "Toyota", "page": 1})

    assert [(b.text, b.callback_data) for b in markup.inline_keyboard[-1]] == [("‹ Пред.", "act:spage:0"), ("Далее ›", "act:spage:2")]


async def test_page_out_of_range_is_clamped():
    text, _ = await render_search_results(_api(_vehicles(12)), MASTER, {"query": "Toyota", "page": 9})

    assert text.startswith("Найдено: 12 · стр. 2/2")


async def test_page_button_replaces_results_in_place():
    state = fsm_context()
    await on_screens(state, ("search_results", {"query": "Toyota", "page": 0}))
    callback = make_callback("act:spage:1")

    await search_page_callback(callback, state, api=_api(_vehicles(12)), user=MASTER)

    stack = (await state.get_data())["nav_stack"]
    assert stack == [["menu", {}], ["search_results", {"query": "Toyota", "page": 1}]]
    assert shown(callback)[0].startswith("Найдено: 12 · стр. 2/2")


async def test_no_matches_texts_by_role():
    assert (await render_search_results(_api([]), MASTER, {"query": "x", "page": 0}))[0] == "Ничего не найдено."
    assert (await render_search_results(_api([]), MECHANIC, {"query": "x", "page": 0}))[0] == (
        "Ничего не найдено. Механик может искать машину по VIN или госномеру."
    )
```

In `tests/bot/test_routing.py` replace `test_search_page_button_routes_to_search_not_stale_fallback` with:

```python
async def test_search_page_button_routes_to_search_not_stale_fallback(env):
    bot, dp, state, api, user = env
    await state.update_data(nav_stack=[["menu", {}], ["search_results", {"query": "Toyota", "page": 0}]], nav_msg_id=5)
    api.search.return_value = [
        {"entity": "vehicle", "id": f"{n:08d}-0000-0000-0000-000000000000", "matched_field": "make"} for n in range(12)
    ]
    api.get_vehicle.return_value = {"make": "Toyota", "model": "Camry", "plate_number": "А1"}

    await dp.feed_update(bot, _callback("act:spage:1"), api=api, user=user)

    api.search.assert_awaited_once_with("Toyota")
    edits = [m for m in bot.sent if type(m).__name__ == "EditMessageText"]
    assert edits and edits[0].text.startswith("Найдено: 12 · стр. 2/2")
```

(`_callback` builds the callback's message with `message_id=5`, matching `nav_msg_id`.)

- [ ] **Step 2: Run, expect FAIL**

Run: `.venv/bin/pytest tests/bot/test_search_handler.py -q`
Expected: FAIL — `ImportError: cannot import name 'render_search'`.

- [ ] **Step 3: Implement** — replace `bot/handlers/search.py` with:

```python
"""Search: a prompt screen, and free text (outside wizards) as the query.

The query lives in the results screen's args, so paging needs no extra state.
"""
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot import actions, nav
from bot.api_client import ApiClient

router = Router()

SEARCH_RESULTS_LIMIT = 10


def _is_mechanic(user: dict) -> bool:
    return user["role"] == "mechanic"


@nav.screen("search")
async def render_search(api: ApiClient, user: dict, args: dict) -> nav.Rendered:
    text = "Введите VIN или гос.номер:" if _is_mechanic(user) else "Введите телефон, VIN, гос.номер или имя клиента:"
    return text, InlineKeyboardBuilder().as_markup()


@nav.screen("search_results")
async def render_search_results(api: ApiClient, user: dict, args: dict) -> nav.Rendered:
    # For mechanics the API returns vehicles only (no client personal data).
    results = await api.search(args["query"])
    builder = InlineKeyboardBuilder()
    if not results:
        if _is_mechanic(user):
            return "Ничего не найдено. Механик может искать машину по VIN или госномеру.", builder.as_markup()
        return "Ничего не найдено.", builder.as_markup()
    pages = -(-len(results) // SEARCH_RESULTS_LIMIT)
    page = min(max(args["page"], 0), pages - 1)  # results may have shrunk since the button was drawn
    for r in results[page * SEARCH_RESULTS_LIMIT : (page + 1) * SEARCH_RESULTS_LIMIT]:
        if r["entity"] == "client":
            client = await api.get_client(r["id"])
            builder.button(text=f"👤 {client['full_name']} — {client['phone_display']}", callback_data=nav.go_data("client", r["id"]))
        elif r["entity"] == "vehicle":
            vehicle = await api.get_vehicle(r["id"])
            builder.button(
                text=f"🚗 {vehicle['make']} {vehicle['model']} ({vehicle['plate_number']})",
                callback_data=nav.go_data("vehicle", r["id"]),
            )
    builder.adjust(1)
    if pages == 1:
        return f"Найдено: {len(results)}", builder.as_markup()
    arrows = []
    if page > 0:
        arrows.append(InlineKeyboardButton(text="‹ Пред.", callback_data=f"{actions.SEARCH_PAGE}:{page - 1}"))
    if page < pages - 1:
        arrows.append(InlineKeyboardButton(text="Далее ›", callback_data=f"{actions.SEARCH_PAGE}:{page + 1}"))
    builder.row(*arrows)
    return f"Найдено: {len(results)} · стр. {page + 1}/{pages}\nМожно уточнить запрос.", builder.as_markup()


@router.message(F.text)
async def receive_search_query(message: Message, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    await nav.push(message, state, api, user, "search_results", {"query": message.text, "page": 0})


@router.callback_query(F.data.startswith(f"{actions.SEARCH_PAGE}:"))
async def search_page_callback(callback: CallbackQuery, state: FSMContext, api: ApiClient, user: dict, **kwargs) -> None:
    args = await nav.top_args(callback, state, "search_results")
    if args is None:
        return
    await nav.replace_top(callback, state, api, user, {**args, "page": int(callback.data.rsplit(":", 1)[1])})
```

(The previous-page arrow is renamed `‹ Пред.` so it can't be confused with the stack's `‹ Назад`.)

- [ ] **Step 4: Run, expect PASS**

Run: `.venv/bin/pytest tests/bot -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add -A bot/handlers/search.py tests/bot/test_search_handler.py tests/bot/test_routing.py
git commit -m "feat(bot): search prompt and paged results as stack screens

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 12: End-to-end routing, callback-size guard, cleanup, docs

**Files:**
- Modify: `tests/bot/test_routing.py`
- Create: `tests/bot/test_callback_sizes.py`
- Modify: `bot/texts.py` (delete `CANCEL_HINT` if unused)
- Modify: `README.md` (bot section)
- Modify: `docs/superpowers/specs/2026-10-04-bot-screen-stack-design.md` (status)

**Interfaces:**
- Consumes: everything above, wired through `bot.main.setup_routers`.

- [ ] **Step 1: Write the tests**

`tests/bot/test_callback_sizes.py`:

```python
"""Every button of every screen fits Telegram's 64-byte callback_data limit."""
from unittest.mock import AsyncMock

from bot import nav
from tests.bot.helpers import ADMIN, MECHANIC, buttons

# UUIDs encode to 22 chars regardless of value; use distinct ones.
V, I, M, C, CAR = (f"{n}" * 8 + "-" + f"{n}" * 4 + "-" + f"{n}" * 4 + "-" + f"{n}" * 4 + "-" + f"{n}" * 12 for n in range(1, 6))


def _api():
    api = AsyncMock()
    item = {"id": I, "visit_id": V, "name": "Очень длинное название работы", "status": "waiting_parts",
            "approved_by_client": False, "assigned_mechanic_name": "Механик", "plate_number": "А123ВС77", "make_model": "X Y"}
    api.get_visit.return_value = {"id": V, "status": "in_progress", "total_amount": 1, "plate_number": "А1"}
    api.list_work_items.return_value = [item]
    api.list_my_work_items.return_value = [item]
    api.list_mechanics.return_value = [{"id": M, "full_name": "Механик"}]
    api.list_visits.return_value = {"items": [{"id": V, "status": "in_progress", "plate_number": "А1", "client_name": "К",
                                               "assigned_master_id": M, "created_at": "2026-10-02T07:00:00+00:00"}], "has_more": False}
    api.get_client.return_value = {"id": C, "full_name": "К", "phone_display": "+7"}
    api.list_client_vehicles.return_value = [{"id": CAR, "make": "A", "model": "B", "plate_number": "А1"}]
    api.get_vehicle.return_value = {"id": CAR, "make": "A", "model": "B", "plate_number": "А1", "vin": "X" * 17, "mileage_current": 1}
    api.get_vehicle_owner.return_value = {"id": C, "full_name": "К"}
    api.search.return_value = [{"entity": "vehicle", "id": CAR}] * 25
    return api


SCREEN_ARGS = {
    "menu": {}, "active_visits": {}, "my_works": {}, "search": {},
    "visit": {"visit_id": V}, "visit_status": {"visit_id": V},
    "work": {"visit_id": V, "item_id": I}, "reassign": {"visit_id": V, "item_id": I},
    "client": {"client_id": C}, "vehicle": {"vehicle_id": CAR},
    "client_visits": {"client_id": C}, "vehicle_visits": {"vehicle_id": CAR}, "work_history": {"vehicle_id": CAR},
    "search_results": {"query": "A", "page": 1},
}


def test_every_screen_is_covered():
    assert set(SCREEN_ARGS) == set(nav.SCREENS) - {name for name in nav.SCREENS if name.startswith(("t_", "w_"))}


async def test_all_screen_buttons_fit_64_bytes():
    for user in (ADMIN, MECHANIC):
        for name, args in SCREEN_ARGS.items():
            _, markup = await nav.SCREENS[name].render(_api(), user, args)
            for text, data in buttons(markup):
                assert len(data.encode()) <= 64, (name, text, data)
```

Append to `tests/bot/test_routing.py`:

```python
async def test_full_flow_menu_to_work_and_back(env):
    from bot.callback_ids import encode_id

    bot, dp, state, api, user = env
    visit_id, item_id = "11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222"
    api.list_visits.return_value = {"items": [], "has_more": False}
    api.get_visit.return_value = {"id": visit_id, "status": "in_progress", "total_amount": 0, "plate_number": "А1"}
    api.list_work_items.return_value = [
        {"id": item_id, "name": "Масло", "status": "in_progress", "approved_by_client": True, "assigned_mechanic_name": None},
    ]

    await dp.feed_update(bot, _message("/start"), api=api, user=user)
    live = (await state.get_data())["nav_msg_id"]
    for data in ("go:active_visits", f"go:visit:{encode_id(visit_id)}", f"go:work:{encode_id(visit_id)}:{encode_id(item_id)}"):
        await dp.feed_update(bot, _callback(data, message_id=live), api=api, user=user)
    assert [s[0] for s in (await state.get_data())["nav_stack"]] == ["menu", "active_visits", "visit", "work"]

    await dp.feed_update(bot, _callback("act:wstatus:ready", message_id=live), api=api, user=user)
    api.update_work_item_status.assert_awaited_once_with(visit_id, item_id, "ready")

    await dp.feed_update(bot, _callback("back", message_id=live), api=api, user=user)
    assert [s[0] for s in (await state.get_data())["nav_stack"]] == ["menu", "active_visits", "visit"]


async def test_wizard_back_and_cancel_route_through_dispatcher(env):
    bot, dp, state, api, user = env
    await state.update_data(nav_stack=[["menu", {}]], nav_msg_id=5)

    await dp.feed_update(bot, _callback("wiz:new_visit"), api=api, user=user)
    assert await state.get_state() == NewVisitStates.waiting_for_client_query.state

    await dp.feed_update(bot, _callback("wiz_cancel"), api=api, user=user)
    assert await state.get_state() is None
    assert (await state.get_data())["nav_stack"] == [["menu", {}]]


async def test_old_format_buttons_are_stale(env):
    bot, dp, state, api, user = env

    for data in ("visit_open:AAAAAAAAAAAAAAAAAAAAAA", "wsc:a:b:ready", "add_work:x", "search_page:1"):
        await dp.feed_update(bot, _callback(data), api=api, user=user)

    answers = [m.text for m in bot.sent if type(m).__name__ == "AnswerCallbackQuery"]
    assert answers == ["Кнопка устарела — начните действие заново."] * 4
```

Give `_callback` a `message_id: int = 5` parameter (used for the inner `Message(message_id=...)`).

- [ ] **Step 2: Run, expect PASS (or fix what fails)**

Run: `.venv/bin/pytest tests/bot -q`
Expected: all pass. A failure here is a wiring bug in an earlier task — fix it in place, don't weaken the test.

- [ ] **Step 3: Cleanup**

Run: `grep -rn "CANCEL_HINT\|state.clear()\|keyboards\|ReassignMechanicStates\|work_status" bot tests`
Expected: no matches. Delete `CANCEL_HINT` from `bot/texts.py` if unused; fix any `state.clear()` left in handlers by switching to `nav.clear_wizard(state)`.

- [ ] **Step 4: Docs**

In `README.md`, replace the "Что умеет бот" table and the commands line with:

```markdown
| Роль | Меню | Что внутри |
|---|---|---|
| Администратор | 🆕 Новый заезд, 🔧 Заезды в работе, 🔍 Поиск, 📝 Регистрация клиента (бумага), 👥 Добавить сотрудника | всё, что у мастера; в «Новом заезде» выбирает ответственного мастера |
| Мастер | 🆕 Новый заезд, 🔧 Заезды в работе, 🔍 Поиск, 📝 Регистрация клиента (бумага) | карточка заезда — по кнопке на работу (⏳🔧📦✅); экран работы: статус, согласование, запчасть, исполнитель; статус заезда, PDF; поиск → карточки клиента и машины → их заезды, «Новый заезд» из карточки машины |
| Механик | 🧰 Мои работы, 🔍 Поиск | свои работы (с госномером) → экран работы со сменой статуса; сообщение, когда работу назначили или сняли; поиск машины по VIN/госномеру → карточка и история работ (без данных клиента и цен) |

Бот работает в одном сообщении: экраны меняются на месте, внизу «‹ Назад» и «🏠 Меню».
В мастерах — «‹ Назад» (шаг назад) и «✖ Отмена». Состояние хранится в Redis и
переживает перезапуск бота.

Команды (кнопка «Меню» в Telegram): `/start`, `/menu`, `/cancel`, `/new_client`, `/new_vehicle`.
```

In the env-variables table of `README.md`, add a row: `| \`REDIS_URL\` | бот | FSM-хранилище; пусто — в памяти (для тестов и запуска без Docker) |`.

In the spec, change `Статус: согласовано, к планированию` to `Статус: реализовано`.

- [ ] **Step 5: Full suite**

Run: `docker compose up -d postgres && .venv/bin/pytest -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "test(bot): end-to-end stack routing and callback size guard; docs

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 7: Deploy and check live (manual)**

Run: `docker compose up -d --build` and check in Telegram:
1. Master: `/start` → old reply keyboard disappears, inline menu shows → Заезды в работе → заезд → работа → «→ Готово» → «‹ Назад» returns to the card, the list shows ✅.
2. Master: Новый заезд → type a client → «‹ Назад» → retype → … → visit card opens; «‹ Назад» returns to the menu.
3. Mechanic: Мои работы → работа (title shows plate) → change status.
4. Start «Добавить работу», type the name, then `docker compose restart bot`, then pick a suggestion — the wizard continues.
```
