# Web / Telegram Mini App (вариант B) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Мобильный веб-клиент CRM в стиле варианта B (графит + янтарь), работающий в браузере и как Telegram Mini App, с паритетом функций бота и безопасным входом.

**Architecture:** Новый модуль бэкенда `app/modules/auth` выдаёт JWT-сессии (вход по Telegram `initData` или dev-выбор сотрудника); `get_current_user` принимает Bearer, а `X-User-Id` — только с сервисным ключом бота. Фронтенд `web/` — React SPA (Vite), тонкий клиент над HTTP API через прокси `/api`; экраны повторяют карту экранов бота, ввод — формами.

**Tech Stack:** Python 3.14 / FastAPI / PyJWT / pytest (бэкенд); React 18.3, TypeScript 5.6, Vite 5.4, React Router 6.28, TanStack Query 5.62, Vitest 2.1 + Testing Library + MSW 2.6 (фронтенд); Node 20.

**Spec:** `docs/superpowers/specs/2026-10-10-web-miniapp-design.md`

## Global Constraints

- Фронтенд вызывает только HTTP API, бизнес-правил (переходы статусов и т.п.) в нём нет — берёт `allowed_next_statuses` из ответов.
- Раскладка мобильная: 360–430px; на широком экране — колонка `max-width: 430px` по центру. Цель нажатия ≥ 44px.
- Токены стиля B: фон `#1d2024`, карточка `#272b31`, текст `#f1efe9`, подсказка `#9aa0a8`, янтарь `#f2b632` (текст на нём `#1d2024`), линия `#353a42`; теги: ремонт — янтарь, запчасти `#8fb6ff`, согласование `#ff8e84`, готов `#7fd99a`. Шрифты Golos Text (текст), JetBrains Mono (госномер, VIN, суммы).
- Весь UI-текст — по-русски.
- Токен сессии: JWT HS256, `{"sub": "<uuid>", "iat", "exp"}`, срок `SESSION_TTL_HOURS` (12). Хранение на фронте — `sessionStorage['crm.token']`, доступ обёрнут в try/catch.
- `initData` старше 86400 с отвергается.
- `DEV_LOGIN=false` → `/auth/dev-users` и `/auth/dev-login` отвечают 404.
- Без `INTERNAL_API_KEY` поведение `X-User-Id` прежнее (обратная совместимость), с ключом — нужен `X-Service-Key`.
- Все существующие тесты бэкенда и бота остаются зелёными.
- Тесты бэкенда: `uv run pytest` из корня репо, нужен `docker compose up -d postgres`. Тесты фронта: `cd web && npm test`.

### Отклонения от спека (решено при планировании)

1. Telegram SDK — официальный скрипт `https://telegram.org/js/telegram-web-app.js` и тонкая обёртка `web/src/telegram/webapp.ts`, а не `@telegram-apps/sdk-react`: меньше зависимостей, API стабилен, в браузере скрипт безвреден (`initData` пустой).
2. Суммы по отдельным работам и список запчастей на карточке заезда **не показываются**: `WorkItemOut` не содержит цен (и отдаётся механикам), `GET` для запчастей нет. Карточка показывает `total_amount` заезда. Расширение API — вне рамок.
3. PDF в браузере открывается как blob (`URL.createObjectURL`). В Mini App blob-ссылки не открываются — там кнопка PDF показывает тост «PDF доступен в боте или в браузере». Полноценная отдача PDF в Mini App — вне рамок.
4. `allowed_next_statuses` реализуется `computed_field` в схеме, поэтому появляется во всех ответах с `VisitOut` (включая элементы `GET /visits`) — безвредное расширение.

## Review Focus

1. **Протухший/чужой токен при открытой вкладке** — любой 401 из любого запроса должен вернуть на `/login` без зависшего экрана; в Mini App вход повторяется автоматически. Тест: Task 9, `RequireAuth redirects to login after 401`.
2. **Двойной тап по кнопке действия** (смена статуса, «Согласовано», создание заезда) — второй запрос не уходит, пока первый не завершён. Защита — ref-замок в `useAction` и в мастере, а не только `disabled` (React не успевает перерисовать кнопку между двумя кликами). Тест: Task 8 (`Button` busy), Task 12 (`status tap sends one PATCH even on double tap`), Task 17 (`create visit submits once on double tap`).
3. **Пробег меньше последнего** при создании заезда — API отвечает 409; мастер должен показать подтверждение и повторить с `mileage_manually_confirmed: true`, а не показать «ошибка». Тест: Task 17.
4. **Механик открывает URL мастера** (`/visits/...`) вручную — экран «Нет доступа», без запросов, падающих 403 по одному. Тест: Task 9, `RoleGate shows no access for mechanic on a master route`.
5. **Ошибка 422 с ключом поля из Pydantic** (`"Value error, Неверный формат..."`) — текст без префикса `Value error, ` у правильного поля формы. Тест: Task 6, `parses 422 field errors`.

---

## File Structure

Бэкенд:
- `app/core/config.py` — новые настройки (Task 1).
- `app/modules/auth/__init__.py`, `tokens.py` (JWT, Task 1), `telegram.py` (проверка initData, Task 2), `router.py` (эндпоинты, Task 2).
- `app/modules/users/auth.py` — `get_current_user` (Bearer / X-User-Id+ключ), `require_service_key` (Task 1).
- `app/modules/users/router.py` — `by-telegram` под `require_service_key` (Task 1).
- `app/main.py` — роутер auth, предупреждение о ключе (Tasks 1–2).
- `app/modules/visits/work_item_flow.py`, `schemas.py`, `work_items_schemas.py` — `allowed_next_statuses` (Task 3).
- `bot/config.py`, `bot/api_client.py` — `X-Service-Key` (Task 4).
- `.env.example`, `pyproject.toml` (`pyjwt`).
- Тесты: `tests/conftest.py` (autouse-настройки), `tests/modules/auth/test_tokens.py`, `test_current_user.py`, `test_telegram.py`, `test_routes.py`, `tests/modules/visits/test_allowed_next_statuses.py`, `tests/bot/test_api_client.py`.

Фронтенд (`web/`):
- Конфиг: `package.json`, `tsconfig.json`, `vite.config.ts`, `index.html`, `src/test/setup.ts`, `src/test/server.ts` (MSW).
- `src/theme.css` — токены и базовые стили.
- `src/api/client.ts` (fetch, ошибки), `src/api/types.ts`, `src/api/endpoints.ts`.
- `src/auth/token.ts`, `src/auth/AuthProvider.tsx`, `src/auth/RequireAuth.tsx`, `src/auth/RoleGate.tsx`.
- `src/telegram/webapp.ts`.
- `src/lib/validators.ts`, `src/lib/labels.ts`, `src/lib/format.ts`.
- `src/ui/*` — `Button`, `Card`, `Plate`, `StatusTag`, `Field`, `Sheet`, `Toast`, `EmptyState`, `Loadable`, `ScreenHeader`, `TabBar`, `Layout`.
- `src/screens/*` — `LoginScreen`, `VisitsScreen`, `VisitScreen`, `WorkScreen`, `MyWorksScreen`, `SearchScreen`, `ClientScreen`, `VehicleScreen`, `MoreScreen`, `NoAccessScreen`.
- `src/forms/*` — `AddWorkForm`, `AddPartForm`, `ClientForm`, `VehicleForm`, `PaperConsentForm`, `StaffForm`, `CancelVisitSheet`, `NewVisitWizard`, `formErrors.ts`.
- `src/App.tsx` (маршруты), `src/main.tsx`.

---

### Task 1: Session tokens, `get_current_user` with Bearer and service key

**Files:**
- Modify: `pyproject.toml` (dependencies), `app/core/config.py`, `app/modules/users/auth.py`, `app/modules/users/router.py:53-61`, `app/main.py`, `tests/conftest.py`
- Create: `app/modules/auth/__init__.py`, `app/modules/auth/tokens.py`, `tests/modules/auth/__init__.py`, `tests/modules/auth/test_tokens.py`, `tests/modules/auth/test_current_user.py`

**Interfaces:**
- Produces: `app.modules.auth.tokens.issue_session_token(user_id: uuid.UUID, now: datetime | None = None) -> str` (raises `SessionNotConfigured`), `read_session_token(token: str) -> uuid.UUID` (raises `InvalidSessionToken`); `app.modules.users.auth.require_service_key` (FastAPI dependency); settings `session_secret: str | None`, `session_ttl_hours: int`, `internal_api_key: str | None`, `dev_login: bool`, `telegram_init_data_max_age_s: int`.

- [ ] **Step 1: Add dependency and settings**

`pyproject.toml` — в `dependencies` после `"redis>=5",` добавить `"pyjwt>=2.9",`. Затем:

Run: `uv sync --extra dev`
Expected: installs `pyjwt`.

`app/core/config.py` — в `Settings` после `telegram_bot_token`:

```python
    # Web / Mini App auth
    session_secret: str | None = None
    session_ttl_hours: int = 12
    telegram_init_data_max_age_s: int = 86400
    dev_login: bool = False
    # Bot's service key: with it set, X-User-Id is honoured only with a matching X-Service-Key.
    internal_api_key: str | None = None
```

`tests/conftest.py` — в конец файла (тесты не должны зависеть от локального `.env`):

```python
@pytest.fixture(autouse=True)
def _auth_settings(monkeypatch):
    monkeypatch.setattr(settings, "session_secret", "test-session-secret")
    monkeypatch.setattr(settings, "internal_api_key", None)
    monkeypatch.setattr(settings, "dev_login", False)
```

- [ ] **Step 2: Write failing token tests**

`tests/modules/auth/__init__.py` — пустой. `tests/modules/auth/test_tokens.py`:

```python
import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.core.config import settings
from app.modules.auth.tokens import (
    InvalidSessionToken,
    SessionNotConfigured,
    issue_session_token,
    read_session_token,
)


def test_round_trip_returns_user_id():
    user_id = uuid.uuid4()
    assert read_session_token(issue_session_token(user_id)) == user_id


def test_expired_token_rejected():
    token = issue_session_token(uuid.uuid4(), now=datetime.now(timezone.utc) - timedelta(hours=13))
    with pytest.raises(InvalidSessionToken):
        read_session_token(token)


def test_token_signed_with_other_key_rejected():
    token = jwt.encode({"sub": str(uuid.uuid4()), "exp": 9999999999}, "other-key", algorithm="HS256")
    with pytest.raises(InvalidSessionToken):
        read_session_token(token)


def test_garbage_rejected():
    with pytest.raises(InvalidSessionToken):
        read_session_token("not-a-jwt")


def test_non_uuid_subject_rejected():
    token = jwt.encode({"sub": "42", "exp": 9999999999}, settings.session_secret, algorithm="HS256")
    with pytest.raises(InvalidSessionToken):
        read_session_token(token)


def test_issue_without_secret_raises(monkeypatch):
    monkeypatch.setattr(settings, "session_secret", None)
    with pytest.raises(SessionNotConfigured):
        issue_session_token(uuid.uuid4())
```

- [ ] **Step 3: Run to verify failure**

Run: `uv run pytest tests/modules/auth/test_tokens.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.modules.auth'`.

- [ ] **Step 4: Implement tokens**

`app/modules/auth/__init__.py` — пустой. `app/modules/auth/tokens.py`:

```python
"""Session tokens for the web / Mini App channel (JWT HS256)."""
import uuid
from datetime import datetime, timedelta, timezone

import jwt

from app.core.config import settings


class SessionNotConfigured(Exception):
    """SESSION_SECRET is not set: tokens cannot be issued."""


class InvalidSessionToken(Exception):
    """Bad signature, expired, malformed or missing subject."""


def issue_session_token(user_id: uuid.UUID, now: datetime | None = None) -> str:
    if not settings.session_secret:
        raise SessionNotConfigured
    now = now or datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=settings.session_ttl_hours)).timestamp()),
    }
    return jwt.encode(payload, settings.session_secret, algorithm="HS256")


def read_session_token(token: str) -> uuid.UUID:
    if not settings.session_secret:
        raise InvalidSessionToken
    try:
        payload = jwt.decode(
            token, settings.session_secret, algorithms=["HS256"], options={"require": ["exp", "sub"]}
        )
        return uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, ValueError, KeyError) as e:
        raise InvalidSessionToken from e
```

- [ ] **Step 5: Run token tests**

Run: `uv run pytest tests/modules/auth/test_tokens.py -v`
Expected: 6 passed.

- [ ] **Step 6: Write failing `get_current_user` tests**

`tests/modules/auth/test_current_user.py`:

```python
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.core.db import get_session
from app.core.enums import UserRole
from app.main import app
from app.modules.auth.tokens import issue_session_token
from app.modules.users.models import User


@pytest.fixture
def api_app(session):
    async def override_get_session():
        yield session

    app.dependency_overrides[get_session] = override_get_session
    yield app
    app.dependency_overrides.clear()


@pytest.fixture
async def master(session):
    user = User(role=UserRole.MASTER, full_name="Мастер", branch_id=uuid.uuid4(), telegram_id=777)
    session.add(user)
    await session.flush()
    return user


async def _get(api_app, path, headers):
    async with AsyncClient(transport=ASGITransport(app=api_app), base_url="http://test") as client:
        return await client.get(path, headers=headers)


async def test_bearer_token_authenticates(api_app, master):
    resp = await _get(api_app, "/users/mechanics", {"Authorization": f"Bearer {issue_session_token(master.id)}"})
    assert resp.status_code == 200


async def test_bad_bearer_token_is_401(api_app, master):
    resp = await _get(api_app, "/users/mechanics", {"Authorization": "Bearer nope"})
    assert resp.status_code == 401


async def test_bearer_for_unknown_user_is_401(api_app):
    resp = await _get(api_app, "/users/mechanics", {"Authorization": f"Bearer {issue_session_token(uuid.uuid4())}"})
    assert resp.status_code == 401


async def test_no_credentials_is_401(api_app):
    resp = await _get(api_app, "/users/mechanics", {})
    assert resp.status_code == 401


async def test_x_user_id_without_configured_key_still_works(api_app, master):
    resp = await _get(api_app, "/users/mechanics", {"X-User-Id": str(master.id)})
    assert resp.status_code == 200


async def test_x_user_id_requires_service_key_when_configured(api_app, master, monkeypatch):
    monkeypatch.setattr(settings, "internal_api_key", "bot-key")
    assert (await _get(api_app, "/users/mechanics", {"X-User-Id": str(master.id)})).status_code == 401
    wrong = {"X-User-Id": str(master.id), "X-Service-Key": "nope"}
    assert (await _get(api_app, "/users/mechanics", wrong)).status_code == 401
    right = {"X-User-Id": str(master.id), "X-Service-Key": "bot-key"}
    assert (await _get(api_app, "/users/mechanics", right)).status_code == 200


async def test_by_telegram_requires_service_key_when_configured(api_app, master, monkeypatch):
    monkeypatch.setattr(settings, "internal_api_key", "bot-key")
    assert (await _get(api_app, "/users/by-telegram/777", {})).status_code == 401
    assert (await _get(api_app, "/users/by-telegram/777", {"X-Service-Key": "bot-key"})).status_code == 200


async def test_by_telegram_open_without_configured_key(api_app, master):
    assert (await _get(api_app, "/users/by-telegram/777", {})).status_code == 200
```

- [ ] **Step 7: Run to verify failure**

Run: `uv run pytest tests/modules/auth/test_current_user.py -v`
Expected: FAIL — bearer tests 422 (missing `X-User-Id` header), service-key tests 200 instead of 401.

- [ ] **Step 8: Implement `get_current_user` and `require_service_key`**

Replace `app/modules/users/auth.py` fully:

```python
import hmac
import uuid
from collections.abc import Callable

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import get_session
from app.core.enums import UserRole
from app.modules.auth.tokens import InvalidSessionToken, read_session_token
from app.modules.users.models import User


def _check_service_key(x_service_key: str | None) -> None:
    """With INTERNAL_API_KEY set, only the bot (holding the key) may act via X-User-Id."""
    expected = settings.internal_api_key
    if expected and not (x_service_key and hmac.compare_digest(x_service_key, expected)):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid service key")


async def require_service_key(x_service_key: str | None = Header(None, alias="X-Service-Key")) -> None:
    _check_service_key(x_service_key)


async def get_current_user(
    authorization: str | None = Header(None),
    x_user_id: uuid.UUID | None = Header(None, alias="X-User-Id"),
    x_service_key: str | None = Header(None, alias="X-Service-Key"),
    session: AsyncSession = Depends(get_session),
) -> User:
    if authorization and authorization.lower().startswith("bearer "):
        try:
            user_id = read_session_token(authorization[7:].strip())
        except InvalidSessionToken:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid session token")
    elif x_user_id is not None:
        _check_service_key(x_service_key)
        user_id = x_user_id
    else:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    user = await session.get(User, user_id)
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

`app/modules/users/router.py` — у `get_user_by_telegram` добавить зависимость в декоратор и импорт:

```python
from app.modules.users.auth import require_role, require_service_key
...
@router.get("/by-telegram/{telegram_id}", response_model=UserOut, dependencies=[Depends(require_service_key)])
```

`app/main.py` — после `install_access_log_filter()`:

```python
import logging

from app.core.config import settings

if not settings.internal_api_key:
    logging.getLogger(__name__).warning("INTERNAL_API_KEY не задан: X-User-Id принимается без сервисного ключа")
```

(импорты `logging` и `settings` поднять к остальным импортам вверху файла.)

- [ ] **Step 9: Run auth tests and full suite**

Run: `uv run pytest tests/modules/auth -v`
Expected: 14 passed.

Run: `uv run pytest -q`
Expected: all pass. If any old test asserted `422` for a missing `X-User-Id`, change its expectation to `401` (missing credentials is now an auth failure, not a validation error) — `grep -rn "422" tests | grep -i "user"` to find them.

- [ ] **Step 10: Commit**

```bash
git add pyproject.toml uv.lock app/core/config.py app/modules/auth app/modules/users/auth.py app/modules/users/router.py app/main.py tests/conftest.py tests/modules/auth
git commit -m "feat(api): JWT session tokens, X-User-Id gated by service key"
```

---

### Task 2: Auth endpoints — Telegram initData, dev login, me

**Files:**
- Create: `app/modules/auth/telegram.py`, `app/modules/auth/router.py`, `tests/modules/auth/test_telegram.py`, `tests/modules/auth/test_routes.py`
- Modify: `app/main.py` (include router)

**Interfaces:**
- Consumes: `issue_session_token`, `SessionNotConfigured` (Task 1); `UserService.get_by_telegram_id`, `UserService.list_users`; `get_current_user`.
- Produces: `verify_init_data(init_data: str, bot_token: str, max_age_s: int, now: float | None = None) -> int` (Telegram user id; raises `InitDataInvalid`). HTTP: `POST /auth/telegram {init_data}` → `{token, user: UserOut}`; `GET /auth/dev-users` → `UserOut[]`; `POST /auth/dev-login {user_id}` → `{token, user}`; `GET /auth/me` → `UserOut`.

- [ ] **Step 1: Write failing initData tests**

`tests/modules/auth/test_telegram.py`:

```python
import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest

from app.modules.auth.telegram import InitDataInvalid, verify_init_data

BOT_TOKEN = "123456:TEST-TOKEN"


def make_init_data(bot_token: str = BOT_TOKEN, user_id: int = 111, auth_date: int | None = None, **extra) -> str:
    fields = {
        "auth_date": str(auth_date if auth_date is not None else int(time.time())),
        "query_id": "AAHdF6IQAAAAAN0XohDhrOrc",
        "user": json.dumps({"id": user_id, "first_name": "Иван"}, ensure_ascii=False),
        **extra,
    }
    check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


def test_valid_init_data_returns_user_id():
    assert verify_init_data(make_init_data(user_id=4242), BOT_TOKEN, 86400) == 4242


def test_tampered_field_rejected():
    data = make_init_data(user_id=1).replace("%22id%22%3A+1", "%22id%22%3A+2")
    with pytest.raises(InitDataInvalid):
        verify_init_data(data, BOT_TOKEN, 86400)


def test_signed_by_other_bot_rejected():
    with pytest.raises(InitDataInvalid):
        verify_init_data(make_init_data(bot_token="999:OTHER"), BOT_TOKEN, 86400)


def test_expired_rejected():
    old = int(time.time()) - 86401
    with pytest.raises(InitDataInvalid):
        verify_init_data(make_init_data(auth_date=old), BOT_TOKEN, 86400)


def test_missing_hash_rejected():
    with pytest.raises(InitDataInvalid):
        verify_init_data("auth_date=1&user=%7B%7D", BOT_TOKEN, 86400)


def test_missing_user_rejected():
    fields = {"auth_date": str(int(time.time()))}
    check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    with pytest.raises(InitDataInvalid):
        verify_init_data(urlencode(fields), BOT_TOKEN, 86400)


def test_extra_signature_field_is_part_of_check_string():
    assert verify_init_data(make_init_data(user_id=5, signature="abc"), BOT_TOKEN, 86400) == 5
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/modules/auth/test_telegram.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.modules.auth.telegram'`.

- [ ] **Step 3: Implement `verify_init_data`**

`app/modules/auth/telegram.py`:

```python
"""Telegram Mini App initData check: https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app"""
import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl


class InitDataInvalid(Exception):
    pass


def verify_init_data(init_data: str, bot_token: str, max_age_s: int, now: float | None = None) -> int:
    """Returns the Telegram user id from signed, fresh initData."""
    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received = pairs.pop("hash", None)
    if not received:
        raise InitDataInvalid("no hash")
    check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received):
        raise InitDataInvalid("bad hash")
    try:
        auth_date = int(pairs["auth_date"])
    except (KeyError, ValueError):
        raise InitDataInvalid("no auth_date")
    if (now if now is not None else time.time()) - auth_date > max_age_s:
        raise InitDataInvalid("expired")
    try:
        return int(json.loads(pairs["user"])["id"])
    except (KeyError, ValueError, TypeError):
        raise InitDataInvalid("no user")
```

- [ ] **Step 4: Run initData tests**

Run: `uv run pytest tests/modules/auth/test_telegram.py -v`
Expected: 7 passed.

- [ ] **Step 5: Write failing route tests**

`tests/modules/auth/test_routes.py`:

```python
import uuid
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.core.db import get_session
from app.core.enums import UserRole
from app.main import app
from app.modules.auth.tokens import read_session_token
from app.modules.users.models import User
from tests.modules.auth.test_telegram import BOT_TOKEN, make_init_data


@pytest.fixture
def api_app(session, monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", BOT_TOKEN)

    async def override_get_session():
        yield session

    app.dependency_overrides[get_session] = override_get_session
    yield app
    app.dependency_overrides.clear()


@pytest.fixture
async def staff(session):
    master = User(role=UserRole.MASTER, full_name="Мастер Орлов", branch_id=uuid.uuid4(), telegram_id=555)
    fired = User(role=UserRole.MECHANIC, full_name="Уволенный", branch_id=uuid.uuid4(), telegram_id=666,
                 deleted_at=datetime.now(timezone.utc))
    session.add_all([master, fired])
    await session.flush()
    return master, fired


async def _call(api_app, method, path, **kwargs):
    async with AsyncClient(transport=ASGITransport(app=api_app), base_url="http://test") as client:
        return await client.request(method, path, **kwargs)


async def test_telegram_login_issues_token(api_app, staff):
    master, _ = staff
    resp = await _call(api_app, "POST", "/auth/telegram", json={"init_data": make_init_data(user_id=555)})
    assert resp.status_code == 200
    body = resp.json()
    assert body["user"]["full_name"] == "Мастер Орлов"
    assert read_session_token(body["token"]) == master.id


async def test_telegram_login_bad_signature_401(api_app, staff):
    resp = await _call(api_app, "POST", "/auth/telegram", json={"init_data": make_init_data(bot_token="1:X", user_id=555)})
    assert resp.status_code == 401


async def test_telegram_login_not_staff_403(api_app, staff):
    resp = await _call(api_app, "POST", "/auth/telegram", json={"init_data": make_init_data(user_id=999)})
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Вы не сотрудник сервиса"


async def test_telegram_login_deleted_staff_403(api_app, staff):
    resp = await _call(api_app, "POST", "/auth/telegram", json={"init_data": make_init_data(user_id=666)})
    assert resp.status_code == 403


async def test_telegram_login_unconfigured_503(api_app, staff, monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", None)
    resp = await _call(api_app, "POST", "/auth/telegram", json={"init_data": make_init_data(user_id=555)})
    assert resp.status_code == 503


async def test_dev_endpoints_404_when_disabled(api_app, staff):
    assert (await _call(api_app, "GET", "/auth/dev-users")).status_code == 404
    master, _ = staff
    assert (await _call(api_app, "POST", "/auth/dev-login", json={"user_id": str(master.id)})).status_code == 404


async def test_dev_users_lists_active_staff(api_app, staff, monkeypatch):
    monkeypatch.setattr(settings, "dev_login", True)
    resp = await _call(api_app, "GET", "/auth/dev-users")
    assert resp.status_code == 200
    names = [u["full_name"] for u in resp.json()]
    assert "Мастер Орлов" in names and "Уволенный" not in names


async def test_dev_login_issues_token(api_app, staff, monkeypatch):
    monkeypatch.setattr(settings, "dev_login", True)
    master, fired = staff
    resp = await _call(api_app, "POST", "/auth/dev-login", json={"user_id": str(master.id)})
    assert resp.status_code == 200
    assert read_session_token(resp.json()["token"]) == master.id
    assert (await _call(api_app, "POST", "/auth/dev-login", json={"user_id": str(fired.id)})).status_code == 404


async def test_me_returns_current_user(api_app, staff, monkeypatch):
    monkeypatch.setattr(settings, "dev_login", True)
    master, _ = staff
    token = (await _call(api_app, "POST", "/auth/dev-login", json={"user_id": str(master.id)})).json()["token"]
    resp = await _call(api_app, "GET", "/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["role"] == "master"


async def test_me_without_token_401(api_app):
    assert (await _call(api_app, "GET", "/auth/me")).status_code == 401
```

- [ ] **Step 6: Run to verify failure**

Run: `uv run pytest tests/modules/auth/test_routes.py -v`
Expected: FAIL — 404 on `/auth/telegram` (router not mounted).

- [ ] **Step 7: Implement router and mount it**

`app/modules/auth/router.py`:

```python
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import get_session
from app.modules.auth.telegram import InitDataInvalid, verify_init_data
from app.modules.auth.tokens import SessionNotConfigured, issue_session_token
from app.modules.users.auth import get_current_user
from app.modules.users.models import User
from app.modules.users.schemas import UserOut
from app.modules.users.service import UserService

router = APIRouter(prefix="/auth", tags=["auth"])


class TelegramLogin(BaseModel):
    init_data: str


class DevLogin(BaseModel):
    user_id: uuid.UUID


class AuthOut(BaseModel):
    token: str
    user: UserOut


def _issue(user: User) -> AuthOut:
    try:
        token = issue_session_token(user.id)
    except SessionNotConfigured:
        raise HTTPException(503, "SESSION_SECRET не задан")
    return AuthOut(token=token, user=UserOut.model_validate(user))


def _require_dev_login() -> None:
    if not settings.dev_login:
        raise HTTPException(404, "Not Found")


@router.post("/telegram", response_model=AuthOut)
async def telegram_login(data: TelegramLogin, session: AsyncSession = Depends(get_session)):
    if not settings.telegram_bot_token or not settings.session_secret:
        raise HTTPException(503, "Вход через Telegram не настроен")
    try:
        telegram_id = verify_init_data(
            data.init_data, settings.telegram_bot_token, settings.telegram_init_data_max_age_s
        )
    except InitDataInvalid:
        raise HTTPException(401, "Неверные данные Telegram")
    user = await UserService(session).get_by_telegram_id(telegram_id)
    if user is None:
        raise HTTPException(403, "Вы не сотрудник сервиса")
    return _issue(user)


@router.get("/dev-users", response_model=list[UserOut], dependencies=[Depends(_require_dev_login)])
async def dev_users(session: AsyncSession = Depends(get_session)):
    return await UserService(session).list_users()


@router.post("/dev-login", response_model=AuthOut, dependencies=[Depends(_require_dev_login)])
async def dev_login(data: DevLogin, session: AsyncSession = Depends(get_session)):
    user = await session.get(User, data.user_id)
    if user is None or user.deleted_at is not None:
        raise HTTPException(404, "User not found")
    return _issue(user)


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return user
```

`app/main.py`: `from app.modules.auth.router import router as auth_router` и `app.include_router(auth_router)` перед `users_router`.

Check `UserService.list_users` excludes deleted users: `grep -n "list_active" -A4 app/modules/users/repository.py` — it must filter `deleted_at.is_(None)`; `list_users` calls it.

- [ ] **Step 8: Run auth tests and full suite**

Run: `uv run pytest tests/modules/auth -v`
Expected: 31 passed.

Run: `uv run pytest -q`
Expected: all pass.

- [ ] **Step 9: Commit**

```bash
git add app/modules/auth app/main.py tests/modules/auth
git commit -m "feat(api): /auth endpoints — Telegram initData login, dev login, me"
```

---

### Task 3: `allowed_next_statuses` on visits and work items

**Files:**
- Create: `app/modules/visits/work_item_flow.py`, `tests/modules/visits/test_allowed_next_statuses.py`
- Modify: `app/modules/visits/schemas.py` (`VisitOut`), `app/modules/visits/work_items_schemas.py` (`WorkItemOut`, `WorkItemMineOut`)

**Interfaces:**
- Consumes: `app.modules.visits.fsm.ALLOWED_TRANSITIONS`.
- Produces: `WORK_ITEM_NEXT_STATUSES: dict[WorkItemStatus, list[WorkItemStatus]]`; JSON field `allowed_next_statuses: list[str]` on every `VisitOut`, `WorkItemOut`, `WorkItemMineOut` (order: enum declaration order for visits; flow order for work items).

- [ ] **Step 1: Write failing tests**

`tests/modules/visits/test_allowed_next_statuses.py`:

```python
import uuid
from datetime import datetime, timezone

import pytest

from app.core.enums import VisitStatus, WorkItemStatus
from app.modules.visits.fsm import ALLOWED_TRANSITIONS
from app.modules.visits.schemas import VisitOut
from app.modules.visits.work_item_flow import WORK_ITEM_NEXT_STATUSES
from app.modules.visits.work_items_schemas import WorkItemMineOut, WorkItemOut


def _visit(status: VisitStatus) -> VisitOut:
    return VisitOut(
        id=uuid.uuid4(), status=status, mileage_at_intake=1, total_amount=0, created_at=datetime.now(timezone.utc),
        client_id=uuid.uuid4(), client_name="К", vehicle_id=uuid.uuid4(), plate_number="А123ВС77",
        make_model="Kia Rio", assigned_master_id=uuid.uuid4(), master_name="М",
    )


@pytest.mark.parametrize("status", list(VisitStatus))
def test_visit_allowed_next_matches_fsm(status):
    out = _visit(status).model_dump(mode="json")
    expected = [s.value for s in VisitStatus if s in ALLOWED_TRANSITIONS[status]]
    assert out["allowed_next_statuses"] == expected


def test_in_progress_visit_order():
    assert _visit(VisitStatus.IN_PROGRESS).model_dump(mode="json")["allowed_next_statuses"] == [
        "waiting_parts", "ready", "cancelled",
    ]


def test_work_item_flow_matches_bot_hint():
    assert WORK_ITEM_NEXT_STATUSES == {
        WorkItemStatus.NOT_READY: [WorkItemStatus.IN_PROGRESS],
        WorkItemStatus.IN_PROGRESS: [WorkItemStatus.WAITING_PARTS, WorkItemStatus.READY],
        WorkItemStatus.WAITING_PARTS: [WorkItemStatus.IN_PROGRESS, WorkItemStatus.READY],
        WorkItemStatus.READY: [],
    }


@pytest.mark.parametrize("status", list(WorkItemStatus))
def test_work_item_schemas_expose_flow(status):
    common = dict(id=uuid.uuid4(), visit_id=uuid.uuid4(), name="Замена масла", status=status,
                  free_text_name=None, catalog_item_id=None)
    expected = [s.value for s in WORK_ITEM_NEXT_STATUSES[status]]
    item = WorkItemOut(**common, approved_by_client=False, assigned_mechanic_id=None)
    mine = WorkItemMineOut(**common)
    assert item.model_dump(mode="json")["allowed_next_statuses"] == expected
    assert mine.model_dump(mode="json")["allowed_next_statuses"] == expected
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/modules/visits/test_allowed_next_statuses.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.modules.visits.work_item_flow'`.

- [ ] **Step 3: Implement**

`app/modules/visits/work_item_flow.py`:

```python
"""MVP next-step flow for work items — a UI hint only.

The API still accepts any work-item status on PATCH; clients (bot, web) offer
these steps so no client keeps its own copy of the flow.
"""
from app.core.enums import WorkItemStatus

WORK_ITEM_NEXT_STATUSES: dict[WorkItemStatus, list[WorkItemStatus]] = {
    WorkItemStatus.NOT_READY: [WorkItemStatus.IN_PROGRESS],
    WorkItemStatus.IN_PROGRESS: [WorkItemStatus.WAITING_PARTS, WorkItemStatus.READY],
    WorkItemStatus.WAITING_PARTS: [WorkItemStatus.IN_PROGRESS, WorkItemStatus.READY],
    WorkItemStatus.READY: [],
}
```

`app/modules/visits/schemas.py` — импорты `computed_field` из pydantic и `ALLOWED_TRANSITIONS`; в `VisitOut` после `master_name`:

```python
from pydantic import BaseModel, ConfigDict, computed_field

from app.modules.visits.fsm import ALLOWED_TRANSITIONS
...
    @computed_field
    @property
    def allowed_next_statuses(self) -> list[VisitStatus]:
        allowed = ALLOWED_TRANSITIONS[self.status]
        return [s for s in VisitStatus if s in allowed]
```

`app/modules/visits/work_items_schemas.py` — импорты `computed_field` и `WORK_ITEM_NEXT_STATUSES`; в `WorkItemOut` и `WorkItemMineOut` после последнего поля (перед `model_config`):

```python
    @computed_field
    @property
    def allowed_next_statuses(self) -> list[WorkItemStatus]:
        return list(WORK_ITEM_NEXT_STATUSES[self.status])
```

- [ ] **Step 4: Run tests and full suite**

Run: `uv run pytest tests/modules/visits/test_allowed_next_statuses.py -v`
Expected: 14 passed.

Run: `uv run pytest -q`
Expected: all pass (existing route tests compare selected keys, not whole dicts; if one compares a full response dict, add `allowed_next_statuses` to its expected value).

- [ ] **Step 5: Commit**

```bash
git add app/modules/visits tests/modules/visits/test_allowed_next_statuses.py
git commit -m "feat(api): expose allowed_next_statuses on visits and work items"
```

---

### Task 4: Bot sends `X-Service-Key`; env example

**Files:**
- Modify: `bot/config.py`, `bot/api_client.py:64-67`, `tests/bot/conftest.py`, `tests/bot/test_api_client.py`, `.env.example`

**Interfaces:**
- Consumes: API behaviour from Task 1.
- Produces: `BotSettings.internal_api_key: str | None`; `ApiClient._headers()` adds `X-Service-Key` when set (also for user-less calls such as `get_user_by_telegram`).

- [ ] **Step 1: Write failing tests**

`tests/bot/conftest.py` — дописать:

```python
import pytest

from bot.config import settings as bot_settings


@pytest.fixture(autouse=True)
def _no_service_key(monkeypatch):
    monkeypatch.setattr(bot_settings, "internal_api_key", None)
```

`tests/bot/test_api_client.py` — дописать:

```python
from bot.config import settings as bot_settings


@respx.mock
async def test_service_key_sent_when_configured(monkeypatch):
    monkeypatch.setattr(bot_settings, "internal_api_key", "bot-key")
    route = respx.get("http://localhost:8000/clients/abc").mock(return_value=httpx.Response(200, json={}))
    await ApiClient(user_id="11111111-1111-1111-1111-111111111111").get("/clients/abc")
    headers = route.calls.last.request.headers
    assert headers["X-Service-Key"] == "bot-key"
    assert headers["X-User-Id"] == "11111111-1111-1111-1111-111111111111"


@respx.mock
async def test_service_key_sent_without_user(monkeypatch):
    monkeypatch.setattr(bot_settings, "internal_api_key", "bot-key")
    route = respx.get("http://localhost:8000/users/by-telegram/5").mock(return_value=httpx.Response(200, json={"id": "u"}))
    await ApiClient().get_user_by_telegram(5)
    assert route.calls.last.request.headers["X-Service-Key"] == "bot-key"


@respx.mock
async def test_no_service_key_header_when_not_configured():
    route = respx.get("http://localhost:8000/clients/abc").mock(return_value=httpx.Response(200, json={}))
    await ApiClient(user_id="11111111-1111-1111-1111-111111111111").get("/clients/abc")
    assert "X-Service-Key" not in route.calls.last.request.headers
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/bot/test_api_client.py -v`
Expected: FAIL — `AttributeError: ... has no attribute 'internal_api_key'` from the conftest fixture.

- [ ] **Step 3: Implement**

`bot/config.py` — в `BotSettings`:

```python
    # Same value as the API's INTERNAL_API_KEY; empty = API accepts X-User-Id without it.
    internal_api_key: str | None = None
```

`bot/api_client.py` — заменить `_headers`:

```python
    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if settings.internal_api_key:
            headers["X-Service-Key"] = settings.internal_api_key
        if self.user_id is not None:
            headers["X-User-Id"] = str(self.user_id)
        return headers
```

`.env.example` — дописать:

```bash
# Web / Mini App
# Random string, e.g. `python -c "import secrets; print(secrets.token_urlsafe(32))"`
SESSION_SECRET=
# true only for local testing: login by picking a staff member
DEV_LOGIN=true
# Shared by api and bot. When set, the API trusts X-User-Id only from the bot.
INTERNAL_API_KEY=
```

- [ ] **Step 4: Run bot tests and full suite**

Run: `uv run pytest tests/bot -q && uv run pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add bot/config.py bot/api_client.py tests/bot/conftest.py tests/bot/test_api_client.py .env.example
git commit -m "feat(bot): send X-Service-Key to the API when configured"
```

---
### Task 5: Scaffold `web/` — Vite, React, TS, Vitest, MSW, theme

**Files:**
- Create: `web/package.json`, `web/tsconfig.json`, `web/vite.config.ts`, `web/index.html`, `web/.gitignore`, `web/src/main.tsx`, `web/src/App.tsx` (placeholder), `web/src/theme.css`, `web/src/vite-env.d.ts`, `web/src/test/setup.ts`, `web/src/test/server.ts`, `web/src/App.test.tsx`

**Interfaces:**
- Produces: `npm run dev` (port 5173, `/api/*` → `http://localhost:8000/*`), `npm test`, `npm run build`, `npm run typecheck`; MSW `server` from `src/test/server.ts` (tests add handlers with `server.use(...)`; unhandled requests fail the test); CSS classes and tokens in `theme.css` used by every later task.

- [ ] **Step 1: Create config files**

`web/package.json`:

```json
{
  "name": "garage-crm-web",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc --noEmit && vite build",
    "typecheck": "tsc --noEmit",
    "test": "vitest run",
    "test:watch": "vitest"
  },
  "dependencies": {
    "@tanstack/react-query": "5.62.0",
    "react": "18.3.1",
    "react-dom": "18.3.1",
    "react-router-dom": "6.28.0"
  },
  "devDependencies": {
    "@testing-library/jest-dom": "6.6.3",
    "@testing-library/react": "16.1.0",
    "@testing-library/user-event": "14.5.2",
    "@types/react": "18.3.12",
    "@types/react-dom": "18.3.1",
    "@vitejs/plugin-react": "4.3.4",
    "jsdom": "25.0.1",
    "msw": "2.6.8",
    "typescript": "5.6.3",
    "vite": "5.4.11",
    "vitest": "2.1.8"
  }
}
```

`web/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "skipLibCheck": true,
    "isolatedModules": true,
    "resolveJsonModule": true,
    "types": ["vitest/globals", "@testing-library/jest-dom"]
  },
  "include": ["src", "vite.config.ts"]
}
```

`web/vite.config.ts`:

```ts
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    css: false,
  },
});
```

`web/.gitignore`:

```
node_modules
dist
```

`web/index.html`:

```html
<!doctype html>
<html lang="ru">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
    <meta name="theme-color" content="#1d2024" />
    <title>Гараж · CRM</title>
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Golos+Text:wght@400;500;600;700&family=JetBrains+Mono:wght@500;600&display=swap" />
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

Без `integrity` у скрипта Telegram — сознательно: Telegram обновляет `telegram-web-app.js` на месте, зафиксированный хеш сломал бы Mini App.

`web/src/vite-env.d.ts`:

```ts
/// <reference types="vite/client" />
```

- [ ] **Step 2: Install**

Run: `cd web && npm install`
Expected: `node_modules` created, `package-lock.json` written, no errors.

- [ ] **Step 3: Test setup and MSW server**

`web/src/test/server.ts` (default handlers for list endpoints that screens hit on landing; tests override them with `server.use`, and `resetHandlers()` restores them):

```ts
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';

export const server = setupServer(
  http.get('/api/visits', () => HttpResponse.json({ items: [], has_more: false })),
  http.get('/api/work-items/mine', () => HttpResponse.json([])),
  http.get('/api/search/recent', () => HttpResponse.json([])),
);
```

`web/src/test/setup.ts`:

```ts
import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterAll, afterEach, beforeAll } from 'vitest';
import { server } from './server';

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => {
  cleanup();
  server.resetHandlers();
  sessionStorage.clear();
  delete (window as { Telegram?: unknown }).Telegram;
});
afterAll(() => server.close());
```

- [ ] **Step 4: Write failing smoke test**

`web/src/App.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react';
import App from './App';

test('renders the app shell', () => {
  render(<App />);
  expect(screen.getByText('Гараж · CRM')).toBeInTheDocument();
});
```

Run: `cd web && npm test`
Expected: FAIL — `Failed to resolve import "./App"`.

- [ ] **Step 5: Theme, placeholder App, entry**

`web/src/theme.css`:

```css
/* Variant B — graphite + signal amber. One theme, independent of Telegram's. */
:root {
  --bg: #1d2024;
  --card: #272b31;
  --text: #f1efe9;
  --hint: #9aa0a8;
  --amber: #f2b632;
  --amber-ink: #1d2024;
  --line: #353a42;
  --tone-repair: #f2b632;
  --tone-parts: #8fb6ff;
  --tone-approval: #ff8e84;
  --tone-ready: #7fd99a;
  --tone-neutral: #b8bdc4;
  --danger: #ff8e84;
  --sans: "Golos Text", system-ui, -apple-system, "Segoe UI", sans-serif;
  --mono: "JetBrains Mono", ui-monospace, monospace;
  --tabbar-h: 60px;
  color-scheme: dark;
}
* { box-sizing: border-box; }
html, body { margin: 0; background: var(--bg); color: var(--text); font: 15px/1.35 var(--sans); }
a { color: inherit; text-decoration: none; }
button { font: inherit; color: inherit; }
.mono { font-family: var(--mono); font-variant-numeric: tabular-nums; }
.hint { color: var(--hint); font-size: 13px; }

.app { max-width: 430px; min-height: 100dvh; margin: 0 auto; position: relative; padding-bottom: calc(var(--tabbar-h) + env(safe-area-inset-bottom, 0px)); }
.app-main { padding: 0 14px 20px; }
.loading { padding: 40px 0; text-align: center; color: var(--hint); }
.login { padding: 32px 14px; display: grid; gap: 14px; max-width: 430px; margin: 0 auto; }
.brand { font-weight: 700; font-size: 22px; letter-spacing: -0.01em; }
.brand b { color: var(--amber); }

.screen-header { display: flex; align-items: center; gap: 10px; padding: 16px 4px 12px; }
.screen-header h1 { flex: 1; margin: 0; font-size: 20px; font-weight: 700; letter-spacing: -0.01em; }
.screen-header .back { width: 44px; height: 44px; margin-left: -10px; border: 0; background: none; color: var(--hint); font-size: 26px; cursor: pointer; }

.stack { display: grid; gap: 10px; }
.row { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.section-title { margin: 18px 4px 8px; font-size: 12px; text-transform: uppercase; letter-spacing: .06em; color: var(--hint); }

.card { display: grid; gap: 8px; background: var(--card); border-radius: 14px; padding: 12px 14px; }
.card-link { cursor: pointer; }
.card-link:active { filter: brightness(1.15); }

.btn { min-height: 44px; padding: 10px 14px; border-radius: 12px; border: 1px solid var(--line); background: transparent; font-weight: 600; cursor: pointer; display: inline-flex; align-items: center; justify-content: center; gap: 6px; }
.btn-primary { background: var(--amber); border-color: var(--amber); color: var(--amber-ink); }
.btn-ghost { border-color: transparent; color: var(--hint); }
.btn-danger { color: var(--danger); }
.btn-block { width: 100%; }
.btn:disabled { opacity: .55; cursor: default; }
.btn[aria-busy="true"] { cursor: progress; }
.actions { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }

.plate { display: inline-flex; align-items: center; gap: 6px; font: 600 15px var(--mono); background: #f1efe9; color: #1d2024; border-radius: 5px; padding: 2px 8px; border: 1.5px solid #1d2024; box-shadow: 0 0 0 1.5px #f1efe9; width: max-content; letter-spacing: .02em; }
.plate small { font-size: 11px; border-left: 1.5px solid #1d2024; padding-left: 5px; }
.plate-raw { font-size: 13px; }

.tag { font-size: 12px; font-weight: 600; padding: 3px 8px; border-radius: 6px; white-space: nowrap; }
.tag-repair { background: rgba(242,182,50,.16); color: var(--tone-repair); }
.tag-parts { background: rgba(143,182,255,.16); color: var(--tone-parts); }
.tag-approval { background: rgba(255,142,132,.16); color: var(--tone-approval); }
.tag-ready { background: rgba(127,217,154,.16); color: var(--tone-ready); }
.tag-neutral { background: rgba(184,189,196,.14); color: var(--tone-neutral); }

.chips { display: flex; gap: 6px; flex-wrap: wrap; padding: 0 0 12px; }
.chip { min-height: 36px; border: 1px solid var(--line); color: var(--hint); background: none; padding: 6px 12px; border-radius: 8px; font-size: 13px; cursor: pointer; }
.chip[aria-pressed="true"] { border-color: var(--amber); color: var(--amber); }

.field { display: grid; gap: 6px; }
.field label { font-size: 13px; color: var(--hint); }
.field input, .field select, .field textarea { min-height: 44px; background: var(--card); border: 1px solid var(--line); border-radius: 10px; color: var(--text); padding: 10px 12px; font: inherit; }
.field input:focus, .field select:focus, .field textarea:focus { outline: 2px solid var(--amber); outline-offset: 0; border-color: transparent; }
.field input[aria-invalid="true"] { border-color: var(--danger); }
.field-error { margin: 0; color: var(--danger); font-size: 13px; }
.field-hint { margin: 0; color: var(--hint); font-size: 12px; }
.form { display: grid; gap: 14px; }
.form-error { color: var(--danger); font-size: 14px; margin: 0; }
.suggest { display: grid; gap: 2px; background: var(--card); border-radius: 10px; overflow: hidden; }
.suggest button { text-align: left; background: none; border: 0; padding: 10px 12px; min-height: 44px; cursor: pointer; }
.suggest button:hover, .suggest button:focus-visible { background: var(--line); }

.list-row { display: grid; grid-template-columns: 26px 1fr auto; gap: 10px; align-items: center; padding: 10px 0; border-bottom: 1px solid var(--line); }
.list-row:last-child { border-bottom: 0; }
.total { display: flex; justify-content: space-between; align-items: baseline; padding: 4px 0; }
.total b { font: 600 22px var(--mono); }

.empty { padding: 28px 8px; text-align: center; color: var(--hint); display: grid; gap: 12px; justify-items: center; }

.tabbar { position: fixed; bottom: 0; left: 50%; transform: translateX(-50%); width: 100%; max-width: 430px; height: calc(var(--tabbar-h) + env(safe-area-inset-bottom, 0px)); padding-bottom: env(safe-area-inset-bottom, 0px); display: flex; background: var(--bg); border-top: 1px solid var(--line); z-index: 10; }
.tabbar a { flex: 1; display: grid; place-items: center; font-size: 12px; color: var(--hint); }
.tabbar a.active { color: var(--amber); }
.tabbar .tab-icon { font-size: 18px; line-height: 1; }

.sheet-backdrop { position: fixed; inset: 0; background: rgba(0,0,0,.55); display: flex; align-items: flex-end; justify-content: center; z-index: 20; }
.sheet { width: 100%; max-width: 430px; background: var(--card); border-radius: 18px 18px 0 0; padding: 16px 14px calc(16px + env(safe-area-inset-bottom, 0px)); display: grid; gap: 8px; max-height: 80dvh; overflow-y: auto; }
.sheet-title { font-weight: 700; font-size: 17px; padding: 0 2px 4px; }

.toasts { position: fixed; left: 50%; transform: translateX(-50%); bottom: calc(var(--tabbar-h) + 12px); width: calc(100% - 28px); max-width: 402px; display: grid; gap: 8px; z-index: 30; }
.toast { background: #f1efe9; color: #1d2024; border-radius: 12px; padding: 10px 12px; display: flex; justify-content: space-between; align-items: center; gap: 10px; font-size: 14px; }
.toast button { border: 0; background: none; color: #1d2024; font-weight: 700; min-height: 36px; cursor: pointer; }

.wizard-step { font-size: 13px; color: var(--hint); margin: 0 4px 10px; }
```

`web/src/App.tsx` (placeholder, replaced in Task 9):

```tsx
export default function App() {
  return (
    <div className="app">
      <div className="login">
        <div className="brand">Гараж · CRM</div>
      </div>
    </div>
  );
}
```

`web/src/main.tsx`:

```tsx
import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './theme.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
```

- [ ] **Step 6: Run test, typecheck, build**

Run: `cd web && npm test && npm run typecheck && npm run build`
Expected: 1 test passed; no type errors; `dist/` built.

- [ ] **Step 7: Commit**

```bash
git add web/package.json web/package-lock.json web/tsconfig.json web/vite.config.ts web/index.html web/.gitignore web/src
git commit -m "feat(web): scaffold Vite + React + TS app with variant B theme"
```

---

### Task 6: API client, types, endpoints, token storage

**Files:**
- Create: `web/src/auth/token.ts`, `web/src/api/client.ts`, `web/src/api/types.ts`, `web/src/api/endpoints.ts`, `web/src/api/client.test.ts`

**Interfaces:**
- Produces:
  - `getToken(): string | null`, `setToken(t: string): void`, `clearToken(): void` (sessionStorage `crm.token`, in-memory fallback).
  - `class ApiError extends Error { status: number; fields: Record<string, string> }` — `status` 0 = no connection.
  - `onUnauthorized(handler: () => void): void` — called on any 401 (after the token is cleared).
  - `parseErrorBody(body: unknown): { message: string; fields: Record<string, string> }`.
  - `api.get/post/patch<T>(path, body?)`, `requestBlob(path): Promise<Blob>` — `path` without `/api` prefix, e.g. `'/visits'`.
  - Types (`types.ts`) and endpoint groups (`endpoints.ts`): `authApi`, `visitsApi`, `workItemsApi`, `clientsApi`, `vehiclesApi`, `searchApi`, `usersApi`, `catalogApi`, `consentApi` — exact signatures below; later tasks call only these.

- [ ] **Step 1: Write failing client tests**

`web/src/api/client.test.ts`:

```ts
import { http, HttpResponse } from 'msw';
import { server } from '../test/server';
import { getToken, setToken } from '../auth/token';
import { ApiError, api, onUnauthorized, parseErrorBody } from './client';

test('sends bearer token and returns json', async () => {
  setToken('tok-1');
  server.use(
    http.get('/api/visits', ({ request }) =>
      HttpResponse.json({ auth: request.headers.get('Authorization') }),
    ),
  );
  expect(await api.get('/visits')).toEqual({ auth: 'Bearer tok-1' });
});

test('401 clears token and calls the unauthorized handler', async () => {
  setToken('tok-1');
  const handler = vi.fn();
  onUnauthorized(handler);
  server.use(http.get('/api/visits', () => HttpResponse.json({ detail: 'Invalid session token' }, { status: 401 })));
  await expect(api.get('/visits')).rejects.toMatchObject({ status: 401 });
  expect(getToken()).toBeNull();
  expect(handler).toHaveBeenCalledOnce();
});

test('parses 422 field errors and strips the pydantic prefix', async () => {
  server.use(
    http.post('/api/clients', () =>
      HttpResponse.json(
        { detail: [{ loc: ['body', 'phone'], msg: 'Value error, Неверный формат телефона', type: 'value_error' }] },
        { status: 422 },
      ),
    ),
  );
  const err = (await api.post('/clients', {}).catch((e) => e)) as ApiError;
  expect(err).toBeInstanceOf(ApiError);
  expect(err.status).toBe(422);
  expect(err.fields).toEqual({ phone: 'Неверный формат телефона' });
  expect(err.message).toBe('Неверный формат телефона');
});

test('409 keeps the detail text', async () => {
  server.use(http.post('/api/vehicles', () => HttpResponse.json({ detail: 'Машина с таким VIN уже есть' }, { status: 409 })));
  await expect(api.post('/vehicles', {})).rejects.toMatchObject({ status: 409, message: 'Машина с таким VIN уже есть' });
});

test('network failure is status 0 with a readable message', async () => {
  server.use(http.get('/api/visits', () => HttpResponse.error()));
  await expect(api.get('/visits')).rejects.toMatchObject({ status: 0, message: 'Нет связи с сервером' });
});

test('5xx reads as no connection, not as a server detail', async () => {
  server.use(http.get('/api/visits', () => HttpResponse.text('boom', { status: 502 })));
  await expect(api.get('/visits')).rejects.toMatchObject({ status: 502, message: 'Нет связи с сервером' });
});

test('model-level 422 without a field becomes a general message', () => {
  expect(parseErrorBody({ detail: [{ loc: ['body'], msg: 'Value error, Укажите ровно одно' }] })).toEqual({
    message: 'Укажите ровно одно',
    fields: {},
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd web && npx vitest run src/api`
Expected: FAIL — cannot resolve `../auth/token`.

- [ ] **Step 3: Implement token storage**

`web/src/auth/token.ts`:

```ts
const KEY = 'crm.token';
let memory: string | null = null;

export function getToken(): string | null {
  try {
    return sessionStorage.getItem(KEY) ?? memory;
  } catch {
    return memory;
  }
}

export function setToken(token: string): void {
  memory = token;
  try {
    sessionStorage.setItem(KEY, token);
  } catch {
    // storage blocked: the in-memory copy lasts until reload
  }
}

export function clearToken(): void {
  memory = null;
  try {
    sessionStorage.removeItem(KEY);
  } catch {
    // nothing stored
  }
}
```

- [ ] **Step 4: Implement client**

`web/src/api/client.ts`:

```ts
import { clearToken, getToken } from '../auth/token';

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public fields: Record<string, string> = {},
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

const NO_CONNECTION = 'Нет связи с сервером';
const DEFAULT_TEXT: Record<number, string> = {
  401: 'Требуется вход',
  403: 'Недостаточно прав',
  404: 'Не найдено',
  409: 'Конфликт',
  422: 'Некорректные данные',
};

let unauthorizedHandler: () => void = () => {};

export function onUnauthorized(handler: () => void): void {
  unauthorizedHandler = handler;
}

interface ValidationIssue {
  loc?: (string | number)[];
  msg?: string;
}

export function parseErrorBody(body: unknown): { message: string; fields: Record<string, string> } {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === 'string') return { message: detail, fields: {} };
  if (!Array.isArray(detail)) return { message: '', fields: {} };
  const fields: Record<string, string> = {};
  const messages: string[] = [];
  for (const issue of detail as ValidationIssue[]) {
    const msg = (issue.msg ?? '').replace(/^Value error, /, '');
    const key = [...(issue.loc ?? [])].reverse().find((p) => typeof p === 'string' && p !== 'body');
    if (typeof key === 'string' && !(key in fields)) fields[key] = msg;
    if (msg) messages.push(msg);
  }
  return { message: messages.join('; '), fields };
}

async function send(method: string, path: string, body?: unknown): Promise<Response> {
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  let res: Response;
  try {
    res = await fetch(`${window.location.origin}/api${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, NO_CONNECTION);
  }
  if (res.ok) return res;
  if (res.status === 401) {
    clearToken();
    unauthorizedHandler();
  }
  if (res.status >= 500) throw new ApiError(res.status, NO_CONNECTION);
  let parsed: { message: string; fields: Record<string, string> } = { message: '', fields: {} };
  try {
    parsed = parseErrorBody(await res.json());
  } catch {
    // not JSON
  }
  throw new ApiError(res.status, parsed.message || DEFAULT_TEXT[res.status] || 'Ошибка', parsed.fields);
}

export async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await send(method, path, body);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export async function requestBlob(path: string): Promise<Blob> {
  return (await send('GET', path)).blob();
}

export const api = {
  get: <T>(path: string) => request<T>('GET', path),
  post: <T>(path: string, body: unknown = {}) => request<T>('POST', path, body),
  patch: <T>(path: string, body: unknown = {}) => request<T>('PATCH', path, body),
};
```

- [ ] **Step 5: Types and endpoints**

`web/src/api/types.ts` (mirrors the Pydantic schemas in `app/modules/*/schemas.py`):

```ts
export type Role = 'admin' | 'master' | 'mechanic';
export type VisitStatus =
  | 'received' | 'diagnostics' | 'approval' | 'in_progress'
  | 'waiting_parts' | 'ready' | 'issued' | 'cancelled';
export type WorkItemStatus = 'not_ready' | 'in_progress' | 'waiting_parts' | 'ready';
export type WorkCategory = 'diagnostics' | 'maintenance' | 'body' | 'electrical' | 'chassis' | 'other';

export interface User {
  id: string;
  role: Role;
  full_name: string;
  telegram_id: number | null;
  phone: string | null;
  branch_id: string;
}

export interface AuthResponse {
  token: string;
  user: User;
}

export interface Visit {
  id: string;
  status: VisitStatus;
  mileage_at_intake: number;
  total_amount: number;
  created_at: string;
  client_id: string;
  client_name: string;
  vehicle_id: string;
  plate_number: string;
  make_model: string;
  assigned_master_id: string;
  master_name: string;
  allowed_next_statuses: VisitStatus[];
}

export interface VisitList {
  items: Visit[];
  has_more: boolean;
}

export interface VisitCreate {
  client_id: string;
  vehicle_id: string;
  assigned_master_id: string;
  mileage_at_intake: number;
  mileage_manually_confirmed: boolean;
}

export interface WorkItem {
  id: string;
  visit_id: string;
  name: string;
  status: WorkItemStatus;
  approved_by_client: boolean;
  free_text_name: string | null;
  catalog_item_id: string | null;
  assigned_mechanic_id: string | null;
  assigned_mechanic_name: string | null;
  allowed_next_statuses: WorkItemStatus[];
}

export interface MyWorkItem {
  id: string;
  visit_id: string;
  name: string;
  status: WorkItemStatus;
  free_text_name: string | null;
  catalog_item_id: string | null;
  plate_number: string | null;
  make_model: string | null;
  allowed_next_statuses: WorkItemStatus[];
}

export interface WorkItemCreate {
  catalog_item_id: string | null;
  free_text_name: string | null;
  category: WorkCategory;
  norm_hours: number;
  hourly_rate: number;
  assigned_mechanic_id: string | null;
}

export interface PartItemCreate {
  work_item_id: string;
  name: string;
  quantity: number;
  unit_price: number;
}

export interface PartItem {
  id: string;
  name: string;
  quantity: number;
  unit_price: number;
}

export interface Client {
  id: string;
  full_name: string;
  phone_display: string;
  client_type: 'individual' | 'legal';
}

export interface Vehicle {
  id: string;
  vin: string;
  plate_number: string;
  make: string;
  model: string;
  mileage_current: number;
}

export interface VehicleCreate {
  vin: string;
  plate_number: string;
  make: string;
  model: string;
}

export interface WorkHistoryItem {
  visit_id: string;
  visit_at: string;
  mileage: number;
  name: string;
  status: WorkItemStatus;
}

export interface WorkHistory {
  items: WorkHistoryItem[];
  has_more: boolean;
}

export interface CatalogItem {
  id: string;
  name: string;
  category: WorkCategory;
  default_norm_hours: number;
}

export interface SearchHit {
  entity: 'client' | 'vehicle';
  id: string;
  matched_field: string;
}

export interface RecentView {
  entity_type: 'client' | 'vehicle';
  entity_id: string;
}

export interface UserCreate {
  role: Role;
  full_name: string;
  telegram_id: number | null;
}
```

`web/src/api/endpoints.ts`:

```ts
import { api, requestBlob } from './client';
import type {
  AuthResponse, CatalogItem, Client, MyWorkItem, PartItem, PartItemCreate, RecentView, SearchHit,
  User, UserCreate, Vehicle, VehicleCreate, Visit, VisitCreate, VisitList, VisitStatus, WorkHistory,
  WorkItem, WorkItemCreate, WorkItemStatus,
} from './types';

const q = encodeURIComponent;

export const authApi = {
  telegram: (initData: string) => api.post<AuthResponse>('/auth/telegram', { init_data: initData }),
  devUsers: () => api.get<User[]>('/auth/dev-users'),
  devLogin: (userId: string) => api.post<AuthResponse>('/auth/dev-login', { user_id: userId }),
  me: () => api.get<User>('/auth/me'),
};

export const visitsApi = {
  listActive: () => api.get<VisitList>('/visits?active=true'),
  listForClient: (clientId: string) => api.get<VisitList>(`/visits?client_id=${q(clientId)}`),
  listForVehicle: (vehicleId: string) => api.get<VisitList>(`/visits?vehicle_id=${q(vehicleId)}`),
  get: (id: string) => api.get<Visit>(`/visits/${id}`),
  create: (body: VisitCreate) => api.post<Visit>('/visits', body),
  changeStatus: (id: string, newStatus: VisitStatus, reason: string | null = null) =>
    api.patch<Visit>(`/visits/${id}/status`, { new_status: newStatus, reason }),
  generateDocument: (id: string) =>
    api.post<{ document_id: string; document_url: string }>(`/visits/${id}/document`),
  documentFile: (documentId: string) => requestBlob(`/documents/${documentId}/file`),
};

export const workItemsApi = {
  list: (visitId: string) => api.get<WorkItem[]>(`/visits/${visitId}/work-items`),
  mine: () => api.get<MyWorkItem[]>('/work-items/mine'),
  add: (visitId: string, body: WorkItemCreate) => api.post<WorkItem>(`/visits/${visitId}/work-items`, body),
  changeStatus: (visitId: string, itemId: string, newStatus: WorkItemStatus) =>
    api.patch<WorkItem>(`/visits/${visitId}/work-items/${itemId}/status`, { new_status: newStatus }),
  assign: (visitId: string, itemId: string, mechanicId: string | null) =>
    api.patch<WorkItem>(`/visits/${visitId}/work-items/${itemId}/mechanic`, { assigned_mechanic_id: mechanicId }),
  approve: (visitId: string, itemId: string) =>
    api.post<WorkItem>(`/visits/${visitId}/work-items/${itemId}/approve`),
  addPart: (visitId: string, body: PartItemCreate) => api.post<PartItem>(`/visits/${visitId}/part-items`, body),
};

export const clientsApi = {
  get: (id: string) => api.get<Client>(`/clients/${id}`),
  vehicles: (id: string) => api.get<Vehicle[]>(`/clients/${id}/vehicles`),
  create: (fullName: string, phone: string) => api.post<Client>('/clients', { full_name: fullName, phone }),
};

export const vehiclesApi = {
  get: (id: string) => api.get<Vehicle>(`/vehicles/${id}`),
  owner: (id: string) => api.get<Client | null>(`/vehicles/${id}/owner`),
  workHistory: (id: string) => api.get<WorkHistory>(`/vehicles/${id}/work-history`),
  create: (body: VehicleCreate) => api.post<Vehicle>('/vehicles', body),
  attachOwner: (vehicleId: string, clientId: string) =>
    api.post<{ id: string }>(`/vehicles/${vehicleId}/owners`, {
      client_id: clientId,
      date_from: new Date().toISOString().slice(0, 10),
    }),
};

export const searchApi = {
  search: (query: string) => api.get<SearchHit[]>(`/search?q=${q(query)}`),
  recent: () => api.get<RecentView[]>('/search/recent'),
};

export const usersApi = {
  mechanics: () => api.get<User[]>('/users/mechanics'),
  masters: () => api.get<User[]>('/users/masters'),
  create: (body: UserCreate) => api.post<User>('/users', body),
};

export const catalogApi = {
  suggest: (text: string) => api.get<CatalogItem[]>(`/catalog/suggest?text=${q(text)}`),
};

export const consentApi = {
  paper: (fullName: string, phone: string) =>
    api.post<{ client_id: string }>('/consent/paper', { full_name: fullName, phone }),
};
```

- [ ] **Step 6: Run tests and typecheck**

Run: `cd web && npx vitest run src/api && npm run typecheck`
Expected: 7 passed; no type errors.

- [ ] **Step 7: Commit**

```bash
git add web/src/auth/token.ts web/src/api
git commit -m "feat(web): typed API client with auth header and error parsing"
```

---

### Task 7: Validators, labels, formatting

**Files:**
- Create: `web/src/lib/validators.ts`, `web/src/lib/labels.ts`, `web/src/lib/format.ts`, `web/src/lib/roles.ts`, `web/src/lib/lib.test.ts`

**Interfaces:**
- Produces:
  - `normalizePhone(raw): string`, `isValidPhone(raw): boolean`, `normalizeVin(raw): string`, `isValidVin(raw): boolean`, `normalizePlate(raw): string`, `looksLikePlate(raw): boolean`; `PHONE_FORMAT_ERROR`, `VIN_FORMAT_ERROR`, `PLATE_FORMAT_ERROR` strings.
  - `VISIT_STATUS_LABELS: Record<VisitStatus, string>`, `WORK_STATUS_LABELS: Record<WorkItemStatus, string>`, `WORK_STATUS_ICONS: Record<WorkItemStatus, string>`, `ROLE_LABELS: Record<Role, string>`, `WORK_CATEGORY_LABELS: Record<WorkCategory, string>`.
  - `formatRub(n: number): string` (`9 850 ₽`), `formatKm(n: number): string` (`120 500 км`), `formatDate(iso: string): string` (`10.10.2026`).
  - `STAFF: Role[]`, `ALL_ROLES: Role[]`, `homePath(role: Role): string`, `ROOT_PATHS: string[]`.

- [ ] **Step 1: Write failing tests**

`web/src/lib/lib.test.ts` (cases copied from `tests/bot/test_validators.py`):

```ts
import { formatDate, formatKm, formatRub } from './format';
import { WORK_STATUS_ICONS } from './labels';
import { homePath } from './roles';
import { isValidPhone, isValidVin, looksLikePlate, normalizePlate, normalizeVin } from './validators';

test.each(['+7 (999) 123-45-67', '89991234567', '9991234567'])('valid phone %s', (raw) => {
  expect(isValidPhone(raw)).toBe(true);
});
test.each(['', '123', '+380 99 123 45 67', '799912345678', 'Иванов'])('invalid phone %s', (raw) => {
  expect(isValidPhone(raw)).toBe(false);
});
test.each(['JTDBR32E720012345', 'jtdbr32e 720012345', 'GX110-6012345'])('valid vin %s', (raw) => {
  expect(isValidVin(raw)).toBe(true);
});
test.each(['', 'ABC12', 'JTDBR32E72001234O', 'А123ВС77', 'ABCDEFG'])('invalid vin %s', (raw) => {
  expect(isValidVin(raw)).toBe(false);
});
test('normalizeVin', () => expect(normalizeVin(' gx110-6012345 ')).toBe('GX110-6012345'));
test.each(['А123ВС77', 'а 123 вс 777', 'A123BC77', 'Х000ХХ-99'])('plate %s', (raw) => {
  expect(looksLikePlate(raw)).toBe(true);
});
test.each(['JTDBR32E720012345', 'GX110-6012345', 'А123', 'Иванов'])('not plate %s', (raw) => {
  expect(looksLikePlate(raw)).toBe(false);
});
test('normalizePlate', () => {
  expect(normalizePlate('а 123 вс-77')).toBe('А123ВС77');
  expect(normalizePlate('a123bc77')).toBe('А123ВС77');
});
test('format', () => {
  expect(formatRub(9850)).toBe('9 850 ₽');
  expect(formatRub(1200.5)).toBe('1 200,5 ₽');
  expect(formatKm(120500)).toBe('120 500 км');
  expect(formatDate('2026-10-10T09:30:00Z')).toBe('10.10.2026');
});
test('labels and roles', () => {
  expect(WORK_STATUS_ICONS.waiting_parts).toBe('📦');
  expect(homePath('mechanic')).toBe('/my');
  expect(homePath('master')).toBe('/visits');
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd web && npx vitest run src/lib`
Expected: FAIL — cannot resolve `./format`.

- [ ] **Step 3: Implement**

`web/src/lib/validators.ts`:

```ts
// Same rules as bot/validators.py and app/core/{phone,vin,plate}.py — the API has the final say.
export const PHONE_FORMAT_ERROR = 'Неверный формат телефона. Пример: +7 900 123-45-67';
export const VIN_FORMAT_ERROR =
  'Неверный формат VIN: 17 символов (латиница и цифры без I, O, Q) или номер кузова, например GX110-6012345';
export const PLATE_FORMAT_ERROR = 'Неверный госномер. Пример: А123ВС77';

const VIN_RE = /^[A-HJ-NPR-Z0-9]{17}$/;
const FRAME_RE = /^(?=.*\d)[A-Z0-9]+(-[A-Z0-9]+)*$/;
const PLATE_LETTERS = 'АВЕКМНОРСТУХ';
const PLATE_RE = new RegExp(`^[${PLATE_LETTERS}]\\d{3}[${PLATE_LETTERS}]{2}\\d{2,3}$`);
const LATIN = 'ABEKMHOPCTYX';

export function normalizePhone(raw: string): string {
  let digits = raw.replace(/\D/g, '');
  if (digits.length === 11 && digits[0] === '8') digits = '7' + digits.slice(1);
  if (digits.length === 10) digits = '7' + digits;
  return digits;
}

export function isValidPhone(raw: string): boolean {
  const digits = normalizePhone(raw);
  return digits.length === 11 && digits[0] === '7';
}

export function normalizeVin(raw: string): string {
  return raw.replace(/\s/g, '').toUpperCase();
}

export function isValidVin(raw: string): boolean {
  const vin = normalizeVin(raw);
  if (vin.length === 17 && !vin.includes('-')) return VIN_RE.test(vin);
  return vin.length >= 6 && vin.length <= 17 && FRAME_RE.test(vin);
}

export function normalizePlate(raw: string): string {
  return [...raw.replace(/[\s-]/g, '').toUpperCase()]
    .map((ch) => {
      const i = LATIN.indexOf(ch);
      return i === -1 ? ch : PLATE_LETTERS[i];
    })
    .join('');
}

export function looksLikePlate(raw: string): boolean {
  return PLATE_RE.test(normalizePlate(raw));
}
```

`web/src/lib/labels.ts`:

```ts
import type { Role, VisitStatus, WorkCategory, WorkItemStatus } from '../api/types';

export const VISIT_STATUS_LABELS: Record<VisitStatus, string> = {
  received: 'Принят',
  diagnostics: 'Диагностика',
  approval: 'Согласование',
  in_progress: 'Ремонт',
  waiting_parts: 'Ждём запчасти',
  ready: 'Готов',
  issued: 'Выдан',
  cancelled: 'Отменён',
};

export const WORK_STATUS_LABELS: Record<WorkItemStatus, string> = {
  not_ready: 'Не начата',
  in_progress: 'В работе',
  waiting_parts: 'Ждёт запчасти',
  ready: 'Готово',
};

export const WORK_STATUS_ICONS: Record<WorkItemStatus, string> = {
  not_ready: '⏳',
  in_progress: '🔧',
  waiting_parts: '📦',
  ready: '✅',
};

export const ROLE_LABELS: Record<Role, string> = { admin: 'Админ', master: 'Мастер', mechanic: 'Механик' };

export const WORK_CATEGORY_LABELS: Record<WorkCategory, string> = {
  diagnostics: 'Диагностика',
  maintenance: 'ТО',
  body: 'Кузовные',
  electrical: 'Электрика',
  chassis: 'Ходовая',
  other: 'Прочее',
};
```

`web/src/lib/format.ts`:

```ts
const NBSP = / | /g;
const number = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 });

export function formatRub(n: number): string {
  return `${number.format(n).replace(NBSP, ' ')} ₽`;
}

export function formatKm(n: number): string {
  return `${number.format(n).replace(NBSP, ' ')} км`;
}

export function formatDate(iso: string): string {
  const d = new Date(iso);
  const dd = String(d.getUTCDate()).padStart(2, '0');
  const mm = String(d.getUTCMonth() + 1).padStart(2, '0');
  return `${dd}.${mm}.${d.getUTCFullYear()}`;
}
```

`web/src/lib/roles.ts`:

```ts
import type { Role } from '../api/types';

export const STAFF: Role[] = ['admin', 'master'];
export const ALL_ROLES: Role[] = ['admin', 'master', 'mechanic'];
/** Tab roots: no back button here. */
export const ROOT_PATHS = ['/visits', '/my', '/search', '/more'];

export function homePath(role: Role): string {
  return role === 'mechanic' ? '/my' : '/visits';
}
```

- [ ] **Step 4: Run tests**

Run: `cd web && npx vitest run src/lib && npm run typecheck`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add web/src/lib
git commit -m "feat(web): validators, status labels and formatting matching the bot"
```

---

### Task 8: UI kit

**Files:**
- Create: `web/src/ui/Button.tsx`, `Card.tsx`, `Plate.tsx`, `StatusTag.tsx`, `Field.tsx`, `Sheet.tsx`, `Toast.tsx`, `EmptyState.tsx`, `Loadable.tsx`, `web/src/ui/ui.test.tsx`

**Interfaces:**
- Consumes: `ApiError` (Task 6); `looksLikePlate`, `normalizePlate`, labels (Task 7).
- Produces (all named exports):
  - `Button(props: ButtonHTMLAttributes & { variant?: 'primary' | 'secondary' | 'ghost' | 'danger'; busy?: boolean; block?: boolean })` — `busy` disables and sets `aria-busy`.
  - `Card({ to?: string; children; className? })` — with `to` renders a `Link`.
  - `Plate({ value: string })`.
  - `StatusTag({ kind: 'visit', status: VisitStatus } | { kind: 'work', status: WorkItemStatus })`.
  - `Field(props: InputHTMLAttributes & { label: string; error?: string; hint?: string })`.
  - `Sheet({ open: boolean; title: string; onClose: () => void; children })`.
  - `ToastProvider({ children })`, `useToast(): { show(text: string, retry?: () => void): void }`.
  - `EmptyState({ text: string; action?: ReactNode })`.
  - `Loadable<T>({ query: UseQueryResult<T, Error>; children: (data: T) => ReactNode; notFound?: string; backTo?: string })` — pending → «Загрузка…»; error without data → 404 «notFound» + «К списку», 403 «Нет доступа к этому разделу», other → message + «Повторить»; data present → children (even if a refetch failed).

- [ ] **Step 1: Write failing tests**

`web/src/ui/ui.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { ApiError } from '../api/client';
import { Button } from './Button';
import { Loadable } from './Loadable';
import { Plate } from './Plate';
import { StatusTag } from './StatusTag';
import { ToastProvider, useToast } from './Toast';

test('busy button is disabled and ignores clicks', async () => {
  const onClick = vi.fn();
  render(<Button busy onClick={onClick}>Сохранить</Button>);
  const btn = screen.getByRole('button', { name: 'Сохранить' });
  expect(btn).toBeDisabled();
  expect(btn).toHaveAttribute('aria-busy', 'true');
  await userEvent.click(btn);
  expect(onClick).not.toHaveBeenCalled();
});

test('plate splits region for russian plates, raw otherwise', () => {
  const { rerender } = render(<Plate value="a123bc77" />);
  expect(screen.getByLabelText('Госномер А123ВС77')).toHaveTextContent('А123ВС77');
  rerender(<Plate value="GX110-6012345" />);
  expect(screen.getByText('GX110-6012345')).toHaveClass('plate-raw');
});

test('status tag shows russian label and tone', () => {
  render(<StatusTag kind="visit" status="waiting_parts" />);
  expect(screen.getByText('Ждём запчасти')).toHaveClass('tag-parts');
});

function Harness({ error }: { error: Error }) {
  const query = useQuery({ queryKey: ['x', error.message], queryFn: () => Promise.reject(error), retry: false });
  return <Loadable query={query} notFound="Заезд не найден" backTo="/visits">{() => <p>data</p>}</Loadable>;
}

function renderLoadable(error: Error) {
  const client = new QueryClient();
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <Harness error={error} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

test('loadable 404 shows not found with a link back', async () => {
  renderLoadable(new ApiError(404, 'Visit not found'));
  expect(await screen.findByText('Заезд не найден')).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'К списку' })).toHaveAttribute('href', '/visits');
});

test('loadable 403 shows no access', async () => {
  renderLoadable(new ApiError(403, 'Role not permitted'));
  expect(await screen.findByText('Нет доступа к этому разделу')).toBeInTheDocument();
});

test('loadable network error offers retry', async () => {
  renderLoadable(new ApiError(0, 'Нет связи с сервером'));
  expect(await screen.findByText('Нет связи с сервером')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Повторить' })).toBeInTheDocument();
});

test('toast shows text and retry', async () => {
  const retry = vi.fn();
  function Trigger() {
    const toast = useToast();
    return <button onClick={() => toast.show('Нет связи с сервером', retry)}>go</button>;
  }
  render(<ToastProvider><Trigger /></ToastProvider>);
  await userEvent.click(screen.getByText('go'));
  expect(screen.getByText('Нет связи с сервером')).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: 'Повторить' }));
  expect(retry).toHaveBeenCalledOnce();
  expect(screen.queryByText('Нет связи с сервером')).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd web && npx vitest run src/ui`
Expected: FAIL — cannot resolve `./Button`.

- [ ] **Step 3: Implement components**

`web/src/ui/Button.tsx`:

```tsx
import type { ButtonHTMLAttributes } from 'react';

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger';
  busy?: boolean;
  block?: boolean;
}

export function Button({ variant = 'secondary', busy = false, block = false, disabled, className = '', type = 'button', ...rest }: Props) {
  const classes = ['btn', `btn-${variant}`, block ? 'btn-block' : '', className].filter(Boolean).join(' ');
  return <button type={type} className={classes} disabled={disabled || busy} aria-busy={busy || undefined} {...rest} />;
}
```

`web/src/ui/Card.tsx`:

```tsx
import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';

export function Card({ to, children, className = '' }: { to?: string; children: ReactNode; className?: string }) {
  if (to) {
    return <Link to={to} className={`card card-link ${className}`.trim()}>{children}</Link>;
  }
  return <div className={`card ${className}`.trim()}>{children}</div>;
}
```

`web/src/ui/Plate.tsx`:

```tsx
import { looksLikePlate, normalizePlate } from '../lib/validators';

export function Plate({ value }: { value: string }) {
  const plate = normalizePlate(value);
  if (!looksLikePlate(plate)) return <span className="plate plate-raw">{value}</span>;
  return (
    <span className="plate" aria-label={`Госномер ${plate}`}>
      {plate.slice(0, 6)}
      <small>{plate.slice(6)}</small>
    </span>
  );
}
```

`web/src/ui/StatusTag.tsx`:

```tsx
import type { VisitStatus, WorkItemStatus } from '../api/types';
import { VISIT_STATUS_LABELS, WORK_STATUS_LABELS } from '../lib/labels';

const VISIT_TONE: Record<VisitStatus, string> = {
  received: 'neutral', diagnostics: 'neutral', approval: 'approval', in_progress: 'repair',
  waiting_parts: 'parts', ready: 'ready', issued: 'neutral', cancelled: 'neutral',
};
const WORK_TONE: Record<WorkItemStatus, string> = {
  not_ready: 'neutral', in_progress: 'repair', waiting_parts: 'parts', ready: 'ready',
};

type Props = { kind: 'visit'; status: VisitStatus } | { kind: 'work'; status: WorkItemStatus };

export function StatusTag(props: Props) {
  const [tone, label] =
    props.kind === 'visit'
      ? [VISIT_TONE[props.status], VISIT_STATUS_LABELS[props.status]]
      : [WORK_TONE[props.status], WORK_STATUS_LABELS[props.status]];
  return <span className={`tag tag-${tone}`}>{label}</span>;
}
```

`web/src/ui/Field.tsx`:

```tsx
import { useId, type InputHTMLAttributes } from 'react';

interface Props extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  error?: string;
  hint?: string;
}

export function Field({ label, error, hint, id, ...rest }: Props) {
  const autoId = useId();
  const fieldId = id ?? autoId;
  return (
    <div className="field">
      <label htmlFor={fieldId}>{label}</label>
      <input id={fieldId} aria-invalid={error ? true : undefined} aria-describedby={error ? `${fieldId}-err` : undefined} {...rest} />
      {error ? (
        <p className="field-error" id={`${fieldId}-err`} role="alert">{error}</p>
      ) : hint ? (
        <p className="field-hint">{hint}</p>
      ) : null}
    </div>
  );
}
```

`web/src/ui/Sheet.tsx`:

```tsx
import type { ReactNode } from 'react';
import { Button } from './Button';

export function Sheet({ open, title, onClose, children }: { open: boolean; title: string; onClose: () => void; children: ReactNode }) {
  if (!open) return null;
  return (
    <div className="sheet-backdrop" onClick={onClose}>
      <div className="sheet" role="dialog" aria-modal="true" aria-label={title} onClick={(e) => e.stopPropagation()}>
        <div className="sheet-title">{title}</div>
        {children}
        <Button variant="ghost" block onClick={onClose}>Закрыть</Button>
      </div>
    </div>
  );
}
```

`web/src/ui/Toast.tsx`:

```tsx
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';

interface ToastItem {
  id: number;
  text: string;
  retry?: () => void;
}

interface ToastApi {
  show(text: string, retry?: () => void): void;
}

const ToastContext = createContext<ToastApi>({ show: () => {} });
let nextId = 1;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const dismiss = useCallback((id: number) => setItems((xs) => xs.filter((x) => x.id !== id)), []);
  const show = useCallback(
    (text: string, retry?: () => void) => {
      const id = nextId++;
      setItems((xs) => [...xs.slice(-2), { id, text, retry }]);
      window.setTimeout(() => dismiss(id), 5000);
    },
    [dismiss],
  );
  const value = useMemo(() => ({ show }), [show]);
  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {items.map((t) => (
          <div key={t.id} className="toast">
            <span>{t.text}</span>
            {t.retry && (
              <button type="button" onClick={() => { dismiss(t.id); t.retry!(); }}>Повторить</button>
            )}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastApi {
  return useContext(ToastContext);
}
```

`web/src/ui/EmptyState.tsx`:

```tsx
import type { ReactNode } from 'react';

export function EmptyState({ text, action }: { text: string; action?: ReactNode }) {
  return (
    <div className="empty">
      <span>{text}</span>
      {action}
    </div>
  );
}
```

`web/src/ui/Loadable.tsx`:

```tsx
import type { UseQueryResult } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { ApiError } from '../api/client';
import { Button } from './Button';
import { EmptyState } from './EmptyState';

interface Props<T> {
  query: UseQueryResult<T, Error>;
  children: (data: T) => ReactNode;
  notFound?: string;
  backTo?: string;
}

export function Loadable<T>({ query, children, notFound = 'Не найдено', backTo }: Props<T>) {
  if (query.data !== undefined) return <>{children(query.data)}</>;
  if (query.isPending) return <div className="loading" aria-busy="true">Загрузка…</div>;
  const err = query.error;
  if (err instanceof ApiError && err.status === 404) {
    return <EmptyState text={notFound} action={backTo ? <Link className="btn btn-secondary" to={backTo}>К списку</Link> : undefined} />;
  }
  if (err instanceof ApiError && err.status === 403) return <EmptyState text="Нет доступа к этому разделу" />;
  return (
    <EmptyState
      text={err?.message || 'Нет связи с сервером'}
      action={<Button onClick={() => query.refetch()}>Повторить</Button>}
    />
  );
}
```

- [ ] **Step 4: Run tests**

Run: `cd web && npx vitest run src/ui && npm run typecheck`
Expected: 7 passed; no type errors.

- [ ] **Step 5: Commit**

```bash
git add web/src/ui
git commit -m "feat(web): variant B UI kit — button, card, plate, status tag, field, sheet, toast, loadable"
```

---

### Task 9: Telegram wrapper, auth, routing shell, login

**Files:**
- Create: `web/src/telegram/webapp.ts`, `web/src/auth/AuthProvider.tsx`, `web/src/auth/RequireAuth.tsx`, `web/src/auth/RoleGate.tsx`, `web/src/lib/useGoBack.ts`, `web/src/ui/ScreenHeader.tsx`, `web/src/ui/TabBar.tsx`, `web/src/ui/Layout.tsx`, `web/src/screens/LoginScreen.tsx`, `web/src/screens/NoAccessScreen.tsx`, `web/src/screens/Placeholder.tsx`, `web/src/routes.tsx`, `web/src/test/render.tsx`, `web/src/auth/auth.test.tsx`
- Modify: `web/src/App.tsx` (replace placeholder), `web/src/main.tsx`, `web/src/App.test.tsx`

**Interfaces:**
- Consumes: `authApi`, `onUnauthorized`, token functions (Task 6); `homePath`, `ROOT_PATHS`, `STAFF`, `ALL_ROLES`, `ROLE_LABELS` (Task 7); `Button`, `EmptyState`, `ToastProvider` (Task 8).
- Produces:
  - `telegram`: `{ isMiniApp(): boolean; initData(): string; init(): void; showBack(onClick: () => void): () => void; haptic(kind: 'success' | 'error'): void }`.
  - `AuthProvider`, `useAuth(): { status: 'loading' | 'anon' | 'authed'; user: User | null; signIn(r: AuthResponse): void; signOut(): void }`. `signIn`/`signOut` clear the query cache.
  - `RequireAuth` (layout route: redirects to `/login` with `state.from`), `RoleGate({ roles: Role[]; children })`.
  - `useGoBack(): () => void` — `navigate(-1)` if there is in-app history, else to `homePath`.
  - `ScreenHeader({ title: string; back?: boolean; right?: ReactNode })` — in-page `‹` only outside Telegram.
  - `AppRoutes` in `src/routes.tsx` — the single route table; later tasks replace `Placeholder` elements with real screens.
  - `AppProviders({ queryClient, children })` and default `App` in `App.tsx`.
  - Test helper `renderApp(path: string, opts?: { as?: Role }): { user: UserEvent; ... }` and `USERS: Record<Role, User>` in `src/test/render.tsx`; renders a hidden `data-testid="location"` element with the current `pathname + search`.

- [ ] **Step 1: Write the test helper**

`web/src/test/render.tsx`:

```tsx
import { QueryClient } from '@tanstack/react-query';
import { render } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { MemoryRouter, useLocation } from 'react-router-dom';
import type { Role, User } from '../api/types';
import { AppProviders } from '../App';
import { setToken } from '../auth/token';
import { AppRoutes } from '../routes';
import { server } from './server';

export const USERS: Record<Role, User> = {
  admin: { id: 'u-admin', role: 'admin', full_name: 'Админ Админов', telegram_id: 1, phone: null, branch_id: 'b1' },
  master: { id: 'u-master', role: 'master', full_name: 'Орлов Пётр', telegram_id: 2, phone: null, branch_id: 'b1' },
  mechanic: { id: 'u-mech', role: 'mechanic', full_name: 'Сидоров Иван', telegram_id: 3, phone: null, branch_id: 'b1' },
};

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location" hidden>{location.pathname + location.search}</div>;
}

export function renderApp(path: string, opts: { as?: Role } = {}) {
  if (opts.as) {
    setToken('test-token');
    const me = USERS[opts.as];
    server.use(http.get('/api/auth/me', () => HttpResponse.json(me)));
  }
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const user = userEvent.setup();
  const utils = render(
    <MemoryRouter initialEntries={[path]}>
      <AppProviders queryClient={queryClient}>
        <AppRoutes />
        <LocationProbe />
      </AppProviders>
    </MemoryRouter>,
  );
  return { user, queryClient, ...utils };
}
```

- [ ] **Step 2: Write failing auth/routing tests**

`web/src/auth/auth.test.tsx`:

```tsx
import { act, screen, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { api } from '../api/client';
import { getToken, setToken } from './token';
import { server } from '../test/server';
import { USERS, renderApp } from '../test/render';

test('browser without token shows dev login and signs in as the picked user', async () => {
  server.use(
    http.get('/api/auth/dev-users', () => HttpResponse.json([USERS.master, USERS.mechanic])),
    http.post('/api/auth/dev-login', async ({ request }) => {
      const { user_id } = (await request.json()) as { user_id: string };
      const user = Object.values(USERS).find((u) => u.id === user_id)!;
      return HttpResponse.json({ token: 'tok-mech', user });
    }),
  );
  const { user } = renderApp('/');
  await user.click(await screen.findByRole('button', { name: /Сидоров Иван/ }));
  await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/my'));
  expect(getToken()).toBe('tok-mech');
});

test('dev login disabled tells to open from Telegram', async () => {
  server.use(http.get('/api/auth/dev-users', () => HttpResponse.json({ detail: 'Not Found' }, { status: 404 })));
  renderApp('/visits');
  expect(await screen.findByText('Откройте приложение из Telegram')).toBeInTheDocument();
});

test('mini app signs in with initData automatically', async () => {
  const webApp = {
    initData: 'query_id=1&hash=abc', ready: vi.fn(), expand: vi.fn(),
    BackButton: { show: vi.fn(), hide: vi.fn(), onClick: vi.fn(), offClick: vi.fn() },
  };
  (window as { Telegram?: unknown }).Telegram = { WebApp: webApp };
  let sent = '';
  server.use(
    http.post('/api/auth/telegram', async ({ request }) => {
      sent = ((await request.json()) as { init_data: string }).init_data;
      return HttpResponse.json({ token: 'tok-tg', user: USERS.master });
    }),
  );
  renderApp('/visits');
  await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/visits'));
  expect(sent).toBe('query_id=1&hash=abc');
});

test('mini app non-staff sees the refusal', async () => {
  (window as { Telegram?: unknown }).Telegram = {
    WebApp: { initData: 'x', ready: vi.fn(), expand: vi.fn(), BackButton: { show: vi.fn(), hide: vi.fn(), onClick: vi.fn(), offClick: vi.fn() } },
  };
  server.use(http.post('/api/auth/telegram', () => HttpResponse.json({ detail: 'Вы не сотрудник сервиса' }, { status: 403 })));
  renderApp('/');
  expect(await screen.findByText('Вы не сотрудник сервиса')).toBeInTheDocument();
});

test('stored token is checked with /auth/me and lands on the role home', async () => {
  renderApp('/', { as: 'master' });
  await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/visits'));
  expect(screen.getByRole('link', { name: /Заезды/ })).toBeInTheDocument();
});

test('mechanic tab bar has only my works and search', async () => {
  renderApp('/my', { as: 'mechanic' });
  expect(await screen.findByRole('link', { name: /Мои работы/ })).toBeInTheDocument();
  expect(screen.getByRole('link', { name: /Поиск/ })).toBeInTheDocument();
  expect(screen.queryByRole('link', { name: /Заезды/ })).not.toBeInTheDocument();
});

test('RoleGate shows no access for mechanic on a master route', async () => {
  renderApp('/more', { as: 'mechanic' });
  expect(await screen.findByText('Нет доступа к этому разделу')).toBeInTheDocument();
});

test('RequireAuth redirects to login after 401', async () => {
  server.use(
    http.get('/api/auth/dev-users', () => HttpResponse.json([USERS.master])),
    http.get('/api/visits', () => HttpResponse.json({ detail: 'Invalid session token' }, { status: 401 })),
  );
  renderApp('/more', { as: 'master' });
  await screen.findByRole('link', { name: /Заезды/ });
  await act(async () => {
    await api.get('/visits').catch(() => {});
  });
  await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/login'));
  expect(getToken()).toBeNull();
});

test('stored but rejected token falls back to login', async () => {
  setToken('stale');
  server.use(
    http.get('/api/auth/me', () => HttpResponse.json({ detail: 'Invalid session token' }, { status: 401 })),
    http.get('/api/auth/dev-users', () => HttpResponse.json([USERS.master])),
  );
  renderApp('/visits');
  await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/login'));
  expect(getToken()).toBeNull();
});
```

Update `web/src/App.test.tsx`:

```tsx
import { screen } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { server } from './test/server';
import { renderApp } from './test/render';

test('renders the brand on the login screen', async () => {
  server.use(http.get('/api/auth/dev-users', () => HttpResponse.json([])));
  renderApp('/login');
  expect(await screen.findByText(/Гараж/)).toBeInTheDocument();
});
```

- [ ] **Step 3: Run to verify failure**

Run: `cd web && npx vitest run src/auth src/App.test.tsx`
Expected: FAIL — cannot resolve `../routes` / `AppProviders` not exported.

- [ ] **Step 4: Telegram wrapper**

`web/src/telegram/webapp.ts`:

```ts
// Thin wrapper over https://telegram.org/js/telegram-web-app.js. In a plain browser
// the script still defines WebApp but initData is empty — every call is a no-op then.
interface TelegramWebApp {
  initData: string;
  ready(): void;
  expand(): void;
  setHeaderColor?(color: string): void;
  setBackgroundColor?(color: string): void;
  BackButton: { show(): void; hide(): void; onClick(cb: () => void): void; offClick(cb: () => void): void };
  HapticFeedback?: { notificationOccurred(kind: 'success' | 'error' | 'warning'): void };
}

function webApp(): TelegramWebApp | null {
  const app = (window as { Telegram?: { WebApp?: TelegramWebApp } }).Telegram?.WebApp;
  return app && app.initData ? app : null;
}

export const telegram = {
  isMiniApp: (): boolean => webApp() !== null,
  initData: (): string => webApp()?.initData ?? '',
  init(): void {
    const app = webApp();
    if (!app) return;
    app.ready();
    app.expand();
    app.setHeaderColor?.('#1d2024');
    app.setBackgroundColor?.('#1d2024');
  },
  showBack(onClick: () => void): () => void {
    const app = webApp();
    if (!app) return () => {};
    app.BackButton.onClick(onClick);
    app.BackButton.show();
    return () => {
      app.BackButton.offClick(onClick);
      app.BackButton.hide();
    };
  },
  haptic(kind: 'success' | 'error'): void {
    webApp()?.HapticFeedback?.notificationOccurred(kind);
  },
};
```

- [ ] **Step 5: Auth provider, guards, go-back**

`web/src/auth/AuthProvider.tsx`:

```tsx
import { useQueryClient } from '@tanstack/react-query';
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { onUnauthorized } from '../api/client';
import { authApi } from '../api/endpoints';
import type { AuthResponse, User } from '../api/types';
import { clearToken, getToken, setToken } from './token';

type Status = 'loading' | 'anon' | 'authed';

interface AuthContextValue {
  status: Status;
  user: User | null;
  signIn(response: AuthResponse): void;
  signOut(): void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [state, setState] = useState<{ status: Status; user: User | null }>(() => ({
    status: getToken() ? 'loading' : 'anon',
    user: null,
  }));

  const signIn = useCallback(
    (response: AuthResponse) => {
      queryClient.clear();
      setToken(response.token);
      setState({ status: 'authed', user: response.user });
    },
    [queryClient],
  );

  const signOut = useCallback(() => {
    clearToken();
    queryClient.clear();
    setState({ status: 'anon', user: null });
  }, [queryClient]);

  useEffect(() => {
    onUnauthorized(() => setState({ status: 'anon', user: null }));
  }, []);

  useEffect(() => {
    if (!getToken()) return;
    let cancelled = false;
    authApi
      .me()
      .then((user) => !cancelled && setState({ status: 'authed', user }))
      .catch(() => {
        if (cancelled) return;
        clearToken();
        setState({ status: 'anon', user: null });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const value = useMemo(() => ({ ...state, signIn, signOut }), [state, signIn, signOut]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth outside AuthProvider');
  return ctx;
}
```

`web/src/auth/RequireAuth.tsx`:

```tsx
import { Navigate, useLocation } from 'react-router-dom';
import { Layout } from '../ui/Layout';
import { useAuth } from './AuthProvider';

export function RequireAuth() {
  const { status } = useAuth();
  const location = useLocation();
  if (status === 'loading') return <div className="loading">Загрузка…</div>;
  if (status !== 'authed') {
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  }
  return <Layout />;
}
```

`web/src/auth/RoleGate.tsx`:

```tsx
import type { ReactNode } from 'react';
import type { Role } from '../api/types';
import { NoAccessScreen } from '../screens/NoAccessScreen';
import { useAuth } from './AuthProvider';

export function RoleGate({ roles, children }: { roles: Role[]; children: ReactNode }) {
  const { user } = useAuth();
  if (!user || !roles.includes(user.role)) return <NoAccessScreen />;
  return <>{children}</>;
}
```

`web/src/lib/useGoBack.ts`:

```ts
import { useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthProvider';
import { homePath } from './roles';

export function useGoBack(): () => void {
  const navigate = useNavigate();
  const { user } = useAuth();
  return useCallback(() => {
    const idx = (window.history.state as { idx?: number } | null)?.idx ?? 0;
    if (idx > 0) navigate(-1);
    else navigate(user ? homePath(user.role) : '/', { replace: true });
  }, [navigate, user]);
}
```

- [ ] **Step 6: Shell UI and screens**

`web/src/ui/ScreenHeader.tsx`:

```tsx
import type { ReactNode } from 'react';
import { useGoBack } from '../lib/useGoBack';
import { telegram } from '../telegram/webapp';

export function ScreenHeader({ title, back = false, right }: { title: string; back?: boolean; right?: ReactNode }) {
  const goBack = useGoBack();
  return (
    <header className="screen-header">
      {back && !telegram.isMiniApp() && (
        <button type="button" className="back" aria-label="Назад" onClick={goBack}>‹</button>
      )}
      <h1>{title}</h1>
      {right}
    </header>
  );
}
```

`web/src/ui/TabBar.tsx`:

```tsx
import { NavLink } from 'react-router-dom';
import { useAuth } from '../auth/AuthProvider';

const STAFF_TABS = [
  { to: '/visits', icon: '🔧', label: 'Заезды', end: true },
  { to: '/search', icon: '🔍', label: 'Поиск', end: false },
  { to: '/visits/new', icon: '＋', label: 'Заезд', end: false },
  { to: '/more', icon: '☰', label: 'Ещё', end: false },
];
const MECHANIC_TABS = [
  { to: '/my', icon: '🧰', label: 'Мои работы', end: false },
  { to: '/search', icon: '🔍', label: 'Поиск', end: false },
];

export function TabBar() {
  const { user } = useAuth();
  const tabs = user?.role === 'mechanic' ? MECHANIC_TABS : STAFF_TABS;
  return (
    <nav className="tabbar" aria-label="Разделы">
      {tabs.map((t) => (
        <NavLink key={t.to} to={t.to} end={t.end}>
          <span className="tab-icon" aria-hidden="true">{t.icon}</span>
          <span>{t.label}</span>
        </NavLink>
      ))}
    </nav>
  );
}
```

`web/src/ui/Layout.tsx`:

```tsx
import { useEffect } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { ROOT_PATHS } from '../lib/roles';
import { useGoBack } from '../lib/useGoBack';
import { telegram } from '../telegram/webapp';
import { TabBar } from './TabBar';

export function Layout() {
  const { pathname } = useLocation();
  const goBack = useGoBack();
  useEffect(() => {
    if (ROOT_PATHS.includes(pathname)) return;
    return telegram.showBack(goBack);
  }, [pathname, goBack]);
  return (
    <div className="app">
      <main className="app-main">
        <Outlet />
      </main>
      <TabBar />
    </div>
  );
}
```

`web/src/screens/NoAccessScreen.tsx`:

```tsx
import { ScreenHeader } from '../ui/ScreenHeader';
import { EmptyState } from '../ui/EmptyState';

export function NoAccessScreen() {
  return (
    <>
      <ScreenHeader title="Нет доступа" back />
      <EmptyState text="Нет доступа к этому разделу" />
    </>
  );
}
```

`web/src/screens/Placeholder.tsx` (removed in Task 18 when the last screen lands):

```tsx
import { ScreenHeader } from '../ui/ScreenHeader';

export function Placeholder({ title }: { title: string }) {
  return <ScreenHeader title={title} back />;
}
```

`web/src/screens/LoginScreen.tsx`:

```tsx
import { useMutation, useQuery } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { ApiError } from '../api/client';
import { authApi } from '../api/endpoints';
import type { AuthResponse } from '../api/types';
import { useAuth } from '../auth/AuthProvider';
import { ROLE_LABELS } from '../lib/labels';
import { homePath } from '../lib/roles';
import { telegram } from '../telegram/webapp';
import { Button } from '../ui/Button';
import { EmptyState } from '../ui/EmptyState';

function Brand() {
  return <div className="brand">Гараж <b>·</b> CRM</div>;
}

function TelegramLogin({ onSignedIn }: { onSignedIn: (r: AuthResponse) => void }) {
  const [error, setError] = useState('');
  useEffect(() => {
    let cancelled = false;
    authApi
      .telegram(telegram.initData())
      .then((r) => !cancelled && onSignedIn(r))
      .catch((e) => !cancelled && setError(e instanceof ApiError ? e.message : 'Не удалось войти'));
    return () => {
      cancelled = true;
    };
  }, [onSignedIn]);
  return error ? <EmptyState text={error} /> : <div className="loading">Вход…</div>;
}

function DevLogin({ onSignedIn }: { onSignedIn: (r: AuthResponse) => void }) {
  const users = useQuery({ queryKey: ['devUsers'], queryFn: authApi.devUsers, retry: false });
  const login = useMutation({ mutationFn: authApi.devLogin, onSuccess: onSignedIn });
  if (users.isPending) return <div className="loading">Загрузка…</div>;
  if (users.isError) return <EmptyState text="Откройте приложение из Telegram" />;
  return (
    <div className="stack">
      <p className="hint">Режим разработки: войти как сотрудник</p>
      {users.data.map((u) => (
        <Button key={u.id} block busy={login.isPending && login.variables === u.id} disabled={login.isPending} onClick={() => login.mutate(u.id)}>
          {u.full_name} · {ROLE_LABELS[u.role]}
        </Button>
      ))}
      {login.isError && <p className="form-error">{login.error.message}</p>}
    </div>
  );
}

export function LoginScreen() {
  const { status, user, signIn } = useAuth();
  const location = useLocation();
  if (status === 'authed' && user) {
    const from = (location.state as { from?: string } | null)?.from;
    return <Navigate to={from && from !== '/login' ? from : homePath(user.role)} replace />;
  }
  return (
    <div className="login">
      <Brand />
      {status === 'loading' ? (
        <div className="loading">Загрузка…</div>
      ) : telegram.isMiniApp() ? (
        <TelegramLogin onSignedIn={signIn} />
      ) : (
        <DevLogin onSignedIn={signIn} />
      )}
    </div>
  );
}
```

`web/src/routes.tsx`:

```tsx
import { Navigate, Route, Routes } from 'react-router-dom';
import { useAuth } from './auth/AuthProvider';
import { RequireAuth } from './auth/RequireAuth';
import { RoleGate } from './auth/RoleGate';
import { ALL_ROLES, STAFF, homePath } from './lib/roles';
import { LoginScreen } from './screens/LoginScreen';
import { Placeholder } from './screens/Placeholder';

function HomeRedirect() {
  const { user } = useAuth();
  return <Navigate to={user ? homePath(user.role) : '/login'} replace />;
}

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginScreen />} />
      <Route element={<RequireAuth />}>
        <Route path="/visits" element={<RoleGate roles={STAFF}><Placeholder title="Заезды в работе" /></RoleGate>} />
        <Route path="/visits/new" element={<RoleGate roles={STAFF}><Placeholder title="Новый заезд" /></RoleGate>} />
        <Route path="/visits/:visitId" element={<RoleGate roles={STAFF}><Placeholder title="Заезд" /></RoleGate>} />
        <Route path="/visits/:visitId/works/new" element={<RoleGate roles={STAFF}><Placeholder title="Новая работа" /></RoleGate>} />
        <Route path="/visits/:visitId/works/:itemId" element={<RoleGate roles={ALL_ROLES}><Placeholder title="Работа" /></RoleGate>} />
        <Route path="/visits/:visitId/works/:itemId/parts/new" element={<RoleGate roles={STAFF}><Placeholder title="Запчасть" /></RoleGate>} />
        <Route path="/my" element={<RoleGate roles={['mechanic']}><Placeholder title="Мои работы" /></RoleGate>} />
        <Route path="/search" element={<RoleGate roles={ALL_ROLES}><Placeholder title="Поиск" /></RoleGate>} />
        <Route path="/clients/new" element={<RoleGate roles={STAFF}><Placeholder title="Новый клиент" /></RoleGate>} />
        <Route path="/clients/:clientId" element={<RoleGate roles={STAFF}><Placeholder title="Клиент" /></RoleGate>} />
        <Route path="/vehicles/new" element={<RoleGate roles={STAFF}><Placeholder title="Новая машина" /></RoleGate>} />
        <Route path="/vehicles/:vehicleId" element={<RoleGate roles={ALL_ROLES}><Placeholder title="Машина" /></RoleGate>} />
        <Route path="/more" element={<RoleGate roles={STAFF}><Placeholder title="Ещё" /></RoleGate>} />
        <Route path="/consent/paper" element={<RoleGate roles={STAFF}><Placeholder title="Бумажное согласие" /></RoleGate>} />
        <Route path="/staff/new" element={<RoleGate roles={['admin']}><Placeholder title="Новый сотрудник" /></RoleGate>} />
        <Route path="*" element={<HomeRedirect />} />
      </Route>
    </Routes>
  );
}
```

`web/src/App.tsx` (replace fully):

```tsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { BrowserRouter } from 'react-router-dom';
import { AuthProvider } from './auth/AuthProvider';
import { AppRoutes } from './routes';
import { ToastProvider } from './ui/Toast';

export function AppProviders({ queryClient, children }: { queryClient: QueryClient; children: ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <AuthProvider>{children}</AuthProvider>
      </ToastProvider>
    </QueryClientProvider>
  );
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 15_000,
      retry: (count, error) => {
        const status = (error as { status?: number }).status ?? 0;
        return count < 1 && !(status >= 400 && status < 500);
      },
    },
  },
});

export default function App() {
  return (
    <BrowserRouter>
      <AppProviders queryClient={queryClient}>
        <AppRoutes />
      </AppProviders>
    </BrowserRouter>
  );
}
```

`web/src/main.tsx` — before `ReactDOM.createRoot(...)` add:

```tsx
import { telegram } from './telegram/webapp';

telegram.init();
```

(keep imports at the top of the file.)

- [ ] **Step 7: Run tests, typecheck**

Run: `cd web && npm test && npm run typecheck`
Expected: all pass (auth 9, App 1, earlier tasks).

- [ ] **Step 8: Commit**

```bash
git add web/src
git commit -m "feat(web): auth (Telegram initData + dev login), role routes, tab bar, Telegram back button"
```

---
### Task 10: Visits list screen

**Files:**
- Create: `web/src/lib/useAction.ts`, `web/src/test/fixtures.ts`, `web/src/screens/VisitsScreen.tsx`, `web/src/screens/VisitsScreen.test.tsx`
- Modify: `web/src/routes.tsx` (route `/visits`)

**Interfaces:**
- Consumes: `visitsApi.listActive`, `useAuth`, UI kit, `ScreenHeader`.
- Produces:
  - `useAction<TVars = void, TData = unknown>(fn: (vars: TVars) => Promise<TData>, opts?: { invalidate?: QueryKey[]; onSuccess?: (data: TData) => void })` → the `useMutation` result with `mutate(vars?)` replaced by a ref-locked version (a second call while one is in flight is dropped); on success: haptic + invalidate + `onSuccess`; on error: haptic + toast with `error.message`.
  - Fixtures: `makeVisit(over?)`, `makeWorkItem(over?)`, `makeMyWork(over?)`, `CLIENT`, `VEHICLE`, `mockVisitPage(visit?, works?)` (registers `GET /api/visits/:id` and `GET /api/visits/:id/work-items`).
  - Query key `['visits', 'active']` (invalidated by `['visits']`).

- [ ] **Step 1: Fixtures and `useAction`**

`web/src/test/fixtures.ts`:

```ts
import { http, HttpResponse } from 'msw';
import type { Client, MyWorkItem, Vehicle, Visit, WorkItem } from '../api/types';
import { server } from './server';

export function makeVisit(over: Partial<Visit> = {}): Visit {
  return {
    id: 'v1', status: 'in_progress', mileage_at_intake: 120500, total_amount: 9850,
    created_at: '2026-10-10T09:00:00Z', client_id: 'c1', client_name: 'Петров Иван',
    vehicle_id: 'veh1', plate_number: 'А123ВС77', make_model: 'Toyota Camry',
    assigned_master_id: 'u-master', master_name: 'Орлов Пётр',
    allowed_next_statuses: ['waiting_parts', 'ready', 'cancelled'], ...over,
  };
}

export function makeWorkItem(over: Partial<WorkItem> = {}): WorkItem {
  return {
    id: 'w1', visit_id: 'v1', name: 'Замена масла ДВС', status: 'in_progress', approved_by_client: false,
    free_text_name: null, catalog_item_id: 'cat1', assigned_mechanic_id: 'u-mech',
    assigned_mechanic_name: 'Сидоров Иван', allowed_next_statuses: ['waiting_parts', 'ready'], ...over,
  };
}

export function makeMyWork(over: Partial<MyWorkItem> = {}): MyWorkItem {
  return {
    id: 'w1', visit_id: 'v1', name: 'Замена масла ДВС', status: 'not_ready', free_text_name: null,
    catalog_item_id: 'cat1', plate_number: 'А123ВС77', make_model: 'Toyota Camry',
    allowed_next_statuses: ['in_progress'], ...over,
  };
}

export const CLIENT: Client = { id: 'c1', full_name: 'Петров Иван', phone_display: '+7 900 123-45-67', client_type: 'individual' };
export const VEHICLE: Vehicle = {
  id: 'veh1', vin: 'JTDBR32E720012345', plate_number: 'А123ВС77', make: 'Toyota', model: 'Camry', mileage_current: 120500,
};

export function mockVisitPage(visit: Visit = makeVisit(), works: WorkItem[] = [makeWorkItem()]) {
  server.use(
    http.get(`/api/visits/${visit.id}`, () => HttpResponse.json(visit)),
    http.get(`/api/visits/${visit.id}/work-items`, () => HttpResponse.json(works)),
  );
}
```

`web/src/lib/useAction.ts`:

```ts
import { useMutation, useQueryClient, type QueryKey } from '@tanstack/react-query';
import { useCallback, useRef } from 'react';
import { telegram } from '../telegram/webapp';
import { useToast } from '../ui/Toast';

/**
 * One-tap actions (status, approve, assign): the button shows busy, failures go to a toast.
 * `mutate` is ref-locked: a double tap lands before React re-renders the button as disabled.
 */
export function useAction<TVars = void, TData = unknown>(
  fn: (vars: TVars) => Promise<TData>,
  opts: { invalidate?: QueryKey[]; onSuccess?: (data: TData) => void } = {},
) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const inFlight = useRef(false);
  const mutation = useMutation<TData, Error, TVars>({
    mutationFn: fn,
    onSuccess: async (data) => {
      telegram.haptic('success');
      await Promise.all((opts.invalidate ?? []).map((queryKey) => queryClient.invalidateQueries({ queryKey })));
      opts.onSuccess?.(data);
    },
    onError: (error) => {
      telegram.haptic('error');
      toast.show(error.message);
    },
    onSettled: () => {
      inFlight.current = false;
    },
  });
  const { mutate: rawMutate } = mutation;
  const mutate = useCallback(
    (vars?: TVars) => {
      if (inFlight.current) return;
      inFlight.current = true;
      rawMutate(vars as TVars);
    },
    [rawMutate],
  );
  return { ...mutation, mutate };
}
```

- [ ] **Step 2: Write failing screen tests**

`web/src/screens/VisitsScreen.test.tsx`:

```tsx
import { screen, waitFor, within } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { makeVisit, mockVisitPage } from '../test/fixtures';
import { renderApp } from '../test/render';
import { server } from '../test/server';

const visits = [
  makeVisit({ id: 'v1', plate_number: 'А123ВС77', status: 'in_progress', assigned_master_id: 'u-master' }),
  makeVisit({ id: 'v2', plate_number: 'Х777ХХ99', make_model: 'Kia Rio', status: 'waiting_parts', assigned_master_id: 'u-other', master_name: 'Другой' }),
];

test('lists active visits as cards', async () => {
  server.use(http.get('/api/visits', () => HttpResponse.json({ items: visits, has_more: false })));
  renderApp('/visits', { as: 'master' });
  expect(await screen.findByLabelText('Госномер А123ВС77')).toBeInTheDocument();
  expect(screen.getByLabelText('Госномер Х777ХХ99')).toBeInTheDocument();
  expect(screen.getByText('Ждём запчасти')).toBeInTheDocument();
});

test('filters by mine and waiting parts', async () => {
  server.use(http.get('/api/visits', () => HttpResponse.json({ items: visits, has_more: false })));
  const { user } = renderApp('/visits', { as: 'master' });
  await screen.findByLabelText('Госномер А123ВС77');
  await user.click(screen.getByRole('button', { name: 'Мои' }));
  expect(screen.getByLabelText('Госномер А123ВС77')).toBeInTheDocument();
  expect(screen.queryByLabelText('Госномер Х777ХХ99')).not.toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Ждут запчасти' }));
  expect(screen.getByLabelText('Госномер Х777ХХ99')).toBeInTheDocument();
  expect(screen.queryByLabelText('Госномер А123ВС77')).not.toBeInTheDocument();
});

test('empty list offers a new visit', async () => {
  server.use(http.get('/api/visits', () => HttpResponse.json({ items: [], has_more: false })));
  renderApp('/visits', { as: 'master' });
  const empty = await screen.findByText('Нет заездов в работе');
  expect(within(empty.parentElement!).getByRole('link', { name: '+ Новый заезд' })).toHaveAttribute('href', '/visits/new');
});

test('card opens the visit', async () => {
  server.use(http.get('/api/visits', () => HttpResponse.json({ items: visits, has_more: false })));
  mockVisitPage();
  const { user } = renderApp('/visits', { as: 'master' });
  await user.click(await screen.findByLabelText('Госномер А123ВС77'));
  await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/visits/v1'));
});
```

- [ ] **Step 3: Run to verify failure**

Run: `cd web && npx vitest run src/screens/VisitsScreen.test.tsx`
Expected: FAIL — cards not found (placeholder screen).

- [ ] **Step 4: Implement**

`web/src/screens/VisitsScreen.tsx`:

```tsx
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { visitsApi } from '../api/endpoints';
import type { Visit } from '../api/types';
import { useAuth } from '../auth/AuthProvider';
import { Card } from '../ui/Card';
import { EmptyState } from '../ui/EmptyState';
import { Loadable } from '../ui/Loadable';
import { Plate } from '../ui/Plate';
import { ScreenHeader } from '../ui/ScreenHeader';
import { StatusTag } from '../ui/StatusTag';

type Filter = 'all' | 'mine' | 'parts' | 'ready';

const FILTERS: { key: Filter; label: string }[] = [
  { key: 'all', label: 'Все' },
  { key: 'mine', label: 'Мои' },
  { key: 'parts', label: 'Ждут запчасти' },
  { key: 'ready', label: 'Готовы' },
];

function matches(visit: Visit, filter: Filter, userId: string): boolean {
  switch (filter) {
    case 'mine':
      return visit.assigned_master_id === userId;
    case 'parts':
      return visit.status === 'waiting_parts';
    case 'ready':
      return visit.status === 'ready';
    default:
      return true;
  }
}

function VisitCard({ visit }: { visit: Visit }) {
  return (
    <Card to={`/visits/${visit.id}`}>
      <div className="row">
        <Plate value={visit.plate_number} />
        <StatusTag kind="visit" status={visit.status} />
      </div>
      <div className="row">
        <span>{visit.make_model}</span>
        <span className="hint">{visit.client_name}</span>
      </div>
      <span className="hint">Мастер: {visit.master_name}</span>
    </Card>
  );
}

export function VisitsScreen() {
  const { user } = useAuth();
  const [filter, setFilter] = useState<Filter>('all');
  const query = useQuery({ queryKey: ['visits', 'active'], queryFn: visitsApi.listActive });
  return (
    <>
      <ScreenHeader title="В работе" right={<Link className="btn btn-primary" to="/visits/new">+ Заезд</Link>} />
      <div className="chips" role="group" aria-label="Фильтр">
        {FILTERS.map((f) => (
          <button key={f.key} type="button" className="chip" aria-pressed={filter === f.key} onClick={() => setFilter(f.key)}>
            {f.label}
          </button>
        ))}
      </div>
      <Loadable query={query}>
        {(data) => {
          const items = data.items.filter((v) => matches(v, filter, user!.id));
          if (items.length === 0) {
            return filter === 'all' ? (
              <EmptyState text="Нет заездов в работе" action={<Link className="btn btn-primary" to="/visits/new">+ Новый заезд</Link>} />
            ) : (
              <EmptyState text="Нет заездов с этим фильтром" />
            );
          }
          return (
            <div className="stack">
              {items.map((v) => <VisitCard key={v.id} visit={v} />)}
              {data.has_more && <p className="hint">Показаны не все заезды</p>}
            </div>
          );
        }}
      </Loadable>
    </>
  );
}
```

`web/src/routes.tsx` — import `VisitsScreen` and replace the `/visits` element:

```tsx
import { VisitsScreen } from './screens/VisitsScreen';
...
        <Route path="/visits" element={<RoleGate roles={STAFF}><VisitsScreen /></RoleGate>} />
```

- [ ] **Step 5: Run tests**

Run: `cd web && npm test && npm run typecheck`
Expected: all pass. (The last test lands on the `/visits/v1` placeholder; `mockVisitPage` handlers are unused until Task 11.)

- [ ] **Step 6: Commit**

```bash
git add web/src
git commit -m "feat(web): active visits screen with filters"
```

---

### Task 11: Visit card — works, status change, cancel, PDF

**Files:**
- Create: `web/src/screens/VisitScreen.tsx`, `web/src/forms/CancelVisitSheet.tsx`, `web/src/screens/VisitScreen.test.tsx`
- Modify: `web/src/routes.tsx` (route `/visits/:visitId`), `web/src/theme.css` (append)

**Interfaces:**
- Consumes: `visitsApi.get/changeStatus/generateDocument/documentFile`, `workItemsApi.list`, `useAction`, `telegram.isMiniApp`, labels, `formatRub`, `formatKm`.
- Produces: query keys `['visit', visitId]`, `['workItems', visitId]`; `CancelVisitSheet({ visitId: string; open: boolean; onClose: () => void })`.

- [ ] **Step 1: Write failing tests**

`web/src/screens/VisitScreen.test.tsx`:

```tsx
import { screen, waitFor, within } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { makeVisit, makeWorkItem, mockVisitPage } from '../test/fixtures';
import { renderApp } from '../test/render';
import { server } from '../test/server';

test('shows header, total and works', async () => {
  mockVisitPage(makeVisit(), [makeWorkItem(), makeWorkItem({ id: 'w2', name: 'Колодки передние', status: 'ready', assigned_mechanic_name: null, approved_by_client: true })]);
  renderApp('/visits/v1', { as: 'master' });
  expect(await screen.findByLabelText('Госномер А123ВС77')).toBeInTheDocument();
  expect(screen.getByText('Toyota Camry')).toBeInTheDocument();
  expect(screen.getByText('9 850 ₽')).toBeInTheDocument();
  expect(screen.getByRole('link', { name: /Колодки передние/ })).toHaveAttribute('href', '/visits/v1/works/w2');
  expect(screen.getByText(/без исполнителя/)).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Петров Иван ›' })).toHaveAttribute('href', '/clients/c1');
});

test('status sheet offers only allowed statuses and patches', async () => {
  mockVisitPage();
  let body: unknown;
  server.use(
    http.patch('/api/visits/v1/status', async ({ request }) => {
      body = await request.json();
      return HttpResponse.json(makeVisit({ status: 'ready', allowed_next_statuses: ['issued', 'cancelled'] }));
    }),
  );
  const { user } = renderApp('/visits/v1', { as: 'master' });
  await user.click(await screen.findByRole('button', { name: 'Сменить статус' }));
  const sheet = screen.getByRole('dialog', { name: 'Сменить статус заезда' });
  expect(within(sheet).getAllByRole('button').map((b) => b.textContent)).toEqual(['Ждём запчасти', 'Готов', 'Отменён', 'Закрыть']);
  await user.click(within(sheet).getByRole('button', { name: 'Готов' }));
  await waitFor(() => expect(body).toEqual({ new_status: 'ready', reason: null }));
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
});

test('409 on status shows the API text in a toast', async () => {
  mockVisitPage();
  server.use(http.patch('/api/visits/v1/status', () => HttpResponse.json({ detail: "Не все работы в статусе 'готово'" }, { status: 409 })));
  const { user } = renderApp('/visits/v1', { as: 'master' });
  await user.click(await screen.findByRole('button', { name: 'Сменить статус' }));
  await user.click(screen.getByRole('button', { name: 'Готов' }));
  expect(await screen.findByText("Не все работы в статусе 'готово'")).toBeInTheDocument();
});

test('cancel asks for a reason', async () => {
  mockVisitPage();
  let body: unknown;
  server.use(
    http.patch('/api/visits/v1/status', async ({ request }) => {
      body = await request.json();
      return HttpResponse.json(makeVisit({ status: 'cancelled', allowed_next_statuses: [] }));
    }),
  );
  const { user } = renderApp('/visits/v1', { as: 'master' });
  await user.click(await screen.findByRole('button', { name: 'Сменить статус' }));
  await user.click(screen.getByRole('button', { name: 'Отменён' }));
  const sheet = screen.getByRole('dialog', { name: 'Отменить заезд' });
  await user.click(within(sheet).getByRole('button', { name: 'Отменить заезд' }));
  expect(within(sheet).getByText('Укажите причину')).toBeInTheDocument();
  expect(body).toBeUndefined();
  await user.type(within(sheet).getByLabelText('Причина отмены'), 'Клиент передумал');
  await user.click(within(sheet).getByRole('button', { name: 'Отменить заезд' }));
  await waitFor(() => expect(body).toEqual({ new_status: 'cancelled', reason: 'Клиент передумал' }));
});

test('unknown visit shows not found', async () => {
  server.use(http.get('/api/visits/nope', () => HttpResponse.json({ detail: 'Visit not found' }, { status: 404 })),
    http.get('/api/visits/nope/work-items', () => HttpResponse.json({ detail: 'Visit not found' }, { status: 404 })));
  renderApp('/visits/nope', { as: 'master' });
  expect(await screen.findByText('Заезд не найден')).toBeInTheDocument();
});

test('PDF in Mini App explains where to get it', async () => {
  (window as { Telegram?: unknown }).Telegram = {
    WebApp: { initData: 'x', ready: vi.fn(), expand: vi.fn(), BackButton: { show: vi.fn(), hide: vi.fn(), onClick: vi.fn(), offClick: vi.fn() } },
  };
  mockVisitPage();
  const { user } = renderApp('/visits/v1', { as: 'master' });
  await user.click(await screen.findByRole('button', { name: 'PDF' }));
  expect(screen.getByText('PDF доступен в боте или в браузере')).toBeInTheDocument();
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd web && npx vitest run src/screens/VisitScreen.test.tsx`
Expected: FAIL — placeholder has no plate.

- [ ] **Step 3: Implement**

`web/src/forms/CancelVisitSheet.tsx`:

```tsx
import { useState } from 'react';
import { visitsApi } from '../api/endpoints';
import { useAction } from '../lib/useAction';
import { Button } from '../ui/Button';
import { Field } from '../ui/Field';
import { Sheet } from '../ui/Sheet';

export function CancelVisitSheet({ visitId, open, onClose }: { visitId: string; open: boolean; onClose: () => void }) {
  const [reason, setReason] = useState('');
  const [error, setError] = useState('');
  const cancel = useAction(() => visitsApi.changeStatus(visitId, 'cancelled', reason.trim()), {
    invalidate: [['visit', visitId], ['visits']],
    onSuccess: onClose,
  });
  return (
    <Sheet open={open} title="Отменить заезд" onClose={onClose}>
      <form
        className="form"
        noValidate
        onSubmit={(e) => {
          e.preventDefault();
          if (!reason.trim()) {
            setError('Укажите причину');
            return;
          }
          setError('');
          cancel.mutate();
        }}
      >
        <Field label="Причина отмены" value={reason} onChange={(e) => setReason(e.target.value)} error={error} autoFocus />
        <Button type="submit" variant="danger" block busy={cancel.isPending}>Отменить заезд</Button>
      </form>
    </Sheet>
  );
}
```

`web/src/screens/VisitScreen.tsx`:

```tsx
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { visitsApi, workItemsApi } from '../api/endpoints';
import type { VisitStatus } from '../api/types';
import { CancelVisitSheet } from '../forms/CancelVisitSheet';
import { formatKm, formatRub } from '../lib/format';
import { VISIT_STATUS_LABELS, WORK_STATUS_ICONS } from '../lib/labels';
import { useAction } from '../lib/useAction';
import { telegram } from '../telegram/webapp';
import { Button } from '../ui/Button';
import { EmptyState } from '../ui/EmptyState';
import { Loadable } from '../ui/Loadable';
import { Plate } from '../ui/Plate';
import { ScreenHeader } from '../ui/ScreenHeader';
import { Sheet } from '../ui/Sheet';
import { StatusTag } from '../ui/StatusTag';
import { useToast } from '../ui/Toast';

export function VisitScreen() {
  const { visitId = '' } = useParams();
  const toast = useToast();
  const visit = useQuery({ queryKey: ['visit', visitId], queryFn: () => visitsApi.get(visitId) });
  const works = useQuery({ queryKey: ['workItems', visitId], queryFn: () => workItemsApi.list(visitId) });
  const [statusOpen, setStatusOpen] = useState(false);
  const [cancelOpen, setCancelOpen] = useState(false);
  const changeStatus = useAction((status: VisitStatus) => visitsApi.changeStatus(visitId, status), {
    invalidate: [['visit', visitId], ['visits']],
    onSuccess: () => setStatusOpen(false),
  });
  const pdf = useAction(async () => {
    const doc = await visitsApi.generateDocument(visitId);
    const blob = await visitsApi.documentFile(doc.document_id);
    window.open(URL.createObjectURL(blob), '_blank');
  });

  function openPdf() {
    if (telegram.isMiniApp()) {
      toast.show('PDF доступен в боте или в браузере');
      return;
    }
    pdf.mutate();
  }

  return (
    <>
      <ScreenHeader title="Заезд" back />
      <Loadable query={visit} notFound="Заезд не найден" backTo="/visits">
        {(v) => (
          <div className="stack">
            <div className="row">
              <Plate value={v.plate_number} />
              <StatusTag kind="visit" status={v.status} />
            </div>
            <div className="visit-car">{v.make_model}</div>
            <Link className="hint" to={`/clients/${v.client_id}`}>{v.client_name} ›</Link>
            <span className="hint">{formatKm(v.mileage_at_intake)} · мастер {v.master_name}</span>
            <div className="total">
              <span className="hint">Итого по заезду</span>
              <b>{formatRub(v.total_amount)}</b>
            </div>
            <h2 className="section-title">Работы</h2>
            <Loadable query={works}>
              {(items) =>
                items.length === 0 ? (
                  <EmptyState text="Работ пока нет" />
                ) : (
                  <div className="card">
                    {items.map((w) => (
                      <Link key={w.id} className="list-row" to={`/visits/${visitId}/works/${w.id}`}>
                        <span aria-hidden="true">{WORK_STATUS_ICONS[w.status]}</span>
                        <span>
                          <span className="block">{w.name}</span>
                          <span className="hint block">
                            {w.assigned_mechanic_name ?? 'без исполнителя'}
                            {w.approved_by_client ? '' : ' · не согласовано'}
                          </span>
                        </span>
                        <span className="hint" aria-hidden="true">›</span>
                      </Link>
                    ))}
                  </div>
                )
              }
            </Loadable>
            <div className="actions">
              <Link className="btn" to={`/visits/${visitId}/works/new`}>+ Работа</Link>
              <Button onClick={openPdf} busy={pdf.isPending}>PDF</Button>
              <Button variant="primary" className="span-2" disabled={v.allowed_next_statuses.length === 0} onClick={() => setStatusOpen(true)}>
                Сменить статус
              </Button>
            </div>
            <Sheet open={statusOpen} title="Сменить статус заезда" onClose={() => setStatusOpen(false)}>
              {v.allowed_next_statuses.map((s) => (
                <Button
                  key={s}
                  block
                  variant={s === 'cancelled' ? 'danger' : 'secondary'}
                  busy={changeStatus.isPending && changeStatus.variables === s}
                  disabled={changeStatus.isPending}
                  onClick={() => {
                    if (s === 'cancelled') {
                      setStatusOpen(false);
                      setCancelOpen(true);
                    } else {
                      changeStatus.mutate(s);
                    }
                  }}
                >
                  {VISIT_STATUS_LABELS[s]}
                </Button>
              ))}
            </Sheet>
            <CancelVisitSheet visitId={visitId} open={cancelOpen} onClose={() => setCancelOpen(false)} />
          </div>
        )}
      </Loadable>
    </>
  );
}
```

`web/src/theme.css` — append:

```css
.visit-car { font-size: 20px; font-weight: 700; }
.span-2 { grid-column: 1 / -1; }
.block { display: block; }
```

`web/src/routes.tsx` — import `VisitScreen`; replace the `/visits/:visitId` element with `<RoleGate roles={STAFF}><VisitScreen /></RoleGate>`.

- [ ] **Step 4: Run tests**

Run: `cd web && npm test && npm run typecheck`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add web/src
git commit -m "feat(web): visit card with works, status sheet, cancel reason, PDF"
```

---

### Task 12: Work screen — status, approve, reassign (staff and mechanic)

**Files:**
- Create: `web/src/screens/WorkScreen.tsx`, `web/src/screens/WorkScreen.test.tsx`
- Modify: `web/src/routes.tsx` (route `/visits/:visitId/works/:itemId`)

**Interfaces:**
- Consumes: `workItemsApi.list/mine/changeStatus/approve/assign`, `usersApi.mechanics`, `useAction`.
- Produces: query keys `['myWorks']`, `['mechanics']`; invalidates `['workItems', visitId]`, `['myWorks']`, `['visit', visitId]` after any action.

- [ ] **Step 1: Write failing tests**

`web/src/screens/WorkScreen.test.tsx`:

```tsx
import { screen, waitFor, within } from '@testing-library/react';
import { delay, http, HttpResponse } from 'msw';
import { USERS, renderApp } from '../test/render';
import { makeMyWork, makeWorkItem } from '../test/fixtures';
import { server } from '../test/server';

function staffItem(over = {}) {
  server.use(http.get('/api/visits/v1/work-items', () => HttpResponse.json([makeWorkItem(over)])));
}

test('staff sees status steps, approve, part and reassign', async () => {
  staffItem();
  renderApp('/visits/v1/works/w1', { as: 'master' });
  expect(await screen.findByText('Замена масла ДВС')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /Ждёт запчасти/ })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /Готово/ })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Согласовано клиентом' })).toBeInTheDocument();
  expect(screen.getByRole('link', { name: '+ Запчасть' })).toHaveAttribute('href', '/visits/v1/works/w1/parts/new');
  expect(screen.getByRole('button', { name: 'Сменить исполнителя' })).toBeInTheDocument();
});

test('mechanic sees only status steps', async () => {
  server.use(http.get('/api/work-items/mine', () => HttpResponse.json([makeMyWork()])));
  renderApp('/visits/v1/works/w1', { as: 'mechanic' });
  expect(await screen.findByRole('button', { name: /В работе/ })).toBeInTheDocument();
  expect(screen.getByLabelText('Госномер А123ВС77')).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Согласовано клиентом' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Сменить исполнителя' })).not.toBeInTheDocument();
});

test('status tap sends one PATCH even on double tap', async () => {
  staffItem();
  const calls: unknown[] = [];
  server.use(
    http.patch('/api/visits/v1/work-items/w1/status', async ({ request }) => {
      calls.push(await request.json());
      await delay(50);
      return HttpResponse.json(makeWorkItem({ status: 'ready', allowed_next_statuses: [] }));
    }),
  );
  const { user } = renderApp('/visits/v1/works/w1', { as: 'master' });
  const btn = await screen.findByRole('button', { name: /Готово/ });
  await user.dblClick(btn);
  await waitFor(() => expect(calls).toEqual([{ new_status: 'ready' }]));
});

test('reassign picks a mechanic or none', async () => {
  staffItem();
  const bodies: unknown[] = [];
  server.use(
    http.get('/api/users/mechanics', () => HttpResponse.json([USERS.mechanic, { ...USERS.mechanic, id: 'u-m2', full_name: 'Ахмедов Руслан' }])),
    http.patch('/api/visits/v1/work-items/w1/mechanic', async ({ request }) => {
      bodies.push(await request.json());
      return HttpResponse.json(makeWorkItem());
    }),
  );
  const { user } = renderApp('/visits/v1/works/w1', { as: 'master' });
  await user.click(await screen.findByRole('button', { name: 'Сменить исполнителя' }));
  const sheet = screen.getByRole('dialog', { name: 'Кому передать работу?' });
  await user.click(await within(sheet).findByRole('button', { name: 'Ахмедов Руслан' }));
  await waitFor(() => expect(bodies).toEqual([{ assigned_mechanic_id: 'u-m2' }]));
  await user.click(screen.getByRole('button', { name: 'Сменить исполнителя' }));
  await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Без исполнителя' }));
  await waitFor(() => expect(bodies[1]).toEqual({ assigned_mechanic_id: null }));
});

test('approve posts and hides the button', async () => {
  let approved = false;
  server.use(
    http.get('/api/visits/v1/work-items', () => HttpResponse.json([makeWorkItem({ approved_by_client: approved })])),
    http.post('/api/visits/v1/work-items/w1/approve', () => {
      approved = true;
      return HttpResponse.json(makeWorkItem({ approved_by_client: true }));
    }),
  );
  const { user } = renderApp('/visits/v1/works/w1', { as: 'master' });
  await user.click(await screen.findByRole('button', { name: 'Согласовано клиентом' }));
  await waitFor(() => expect(screen.queryByRole('button', { name: 'Согласовано клиентом' })).not.toBeInTheDocument());
  expect(screen.getByText('✅ Согласовано клиентом')).toBeInTheDocument();
});

test('missing item shows not found', async () => {
  server.use(http.get('/api/work-items/mine', () => HttpResponse.json([])));
  renderApp('/visits/v1/works/zzz', { as: 'mechanic' });
  expect(await screen.findByText('Работа не найдена')).toBeInTheDocument();
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd web && npx vitest run src/screens/WorkScreen.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Implement**

`web/src/screens/WorkScreen.tsx`:

```tsx
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { usersApi, workItemsApi } from '../api/endpoints';
import type { MyWorkItem, WorkItem, WorkItemStatus } from '../api/types';
import { useAuth } from '../auth/AuthProvider';
import { WORK_STATUS_ICONS, WORK_STATUS_LABELS } from '../lib/labels';
import { useAction } from '../lib/useAction';
import { Button } from '../ui/Button';
import { EmptyState } from '../ui/EmptyState';
import { Loadable } from '../ui/Loadable';
import { Plate } from '../ui/Plate';
import { ScreenHeader } from '../ui/ScreenHeader';
import { Sheet } from '../ui/Sheet';
import { StatusTag } from '../ui/StatusTag';

type AnyWork = WorkItem | MyWorkItem;

function isStaffItem(w: AnyWork): w is WorkItem {
  return 'approved_by_client' in w;
}

export function WorkScreen() {
  const { visitId = '', itemId = '' } = useParams();
  const { user } = useAuth();
  const isMechanic = user!.role === 'mechanic';
  const [assignOpen, setAssignOpen] = useState(false);
  const query = useQuery<AnyWork[], Error>({
    queryKey: isMechanic ? ['myWorks'] : ['workItems', visitId],
    queryFn: () => (isMechanic ? workItemsApi.mine() : workItemsApi.list(visitId)),
  });
  const mechanics = useQuery({ queryKey: ['mechanics'], queryFn: usersApi.mechanics, enabled: assignOpen });
  const invalidate = [['workItems', visitId], ['myWorks'], ['visit', visitId]];
  const status = useAction((s: WorkItemStatus) => workItemsApi.changeStatus(visitId, itemId, s), { invalidate });
  const approve = useAction(() => workItemsApi.approve(visitId, itemId), { invalidate });
  const assign = useAction((mechanicId: string | null) => workItemsApi.assign(visitId, itemId, mechanicId), {
    invalidate,
    onSuccess: () => setAssignOpen(false),
  });
  const busy = status.isPending || approve.isPending || assign.isPending;

  return (
    <>
      <ScreenHeader title="Работа" back />
      <Loadable query={query}>
        {(items) => {
          const w = items.find((x) => x.id === itemId);
          if (!w) return <EmptyState text="Работа не найдена" />;
          return (
            <div className="stack">
              <div className="card">
                <div className="row">
                  <b>{w.name}</b>
                  <StatusTag kind="work" status={w.status} />
                </div>
                {!isStaffItem(w) && w.plate_number && (
                  <div className="row">
                    <Plate value={w.plate_number} />
                    <span className="hint">{w.make_model}</span>
                  </div>
                )}
                {isStaffItem(w) && (
                  <>
                    <span className="hint">Исполнитель: {w.assigned_mechanic_name ?? 'не назначен'}</span>
                    <span className="hint">{w.approved_by_client ? '✅ Согласовано клиентом' : 'Не согласовано клиентом'}</span>
                  </>
                )}
              </div>
              {w.allowed_next_statuses.length > 0 && (
                <>
                  <h2 className="section-title">Статус</h2>
                  {w.allowed_next_statuses.map((s) => (
                    <Button key={s} block busy={status.isPending && status.variables === s} disabled={busy} onClick={() => status.mutate(s)}>
                      {WORK_STATUS_ICONS[s]} {WORK_STATUS_LABELS[s]}
                    </Button>
                  ))}
                </>
              )}
              {!isMechanic && isStaffItem(w) && (
                <>
                  <h2 className="section-title">Действия</h2>
                  {!w.approved_by_client && (
                    <Button variant="primary" block busy={approve.isPending} disabled={busy} onClick={() => approve.mutate()}>
                      Согласовано клиентом
                    </Button>
                  )}
                  <Link className="btn btn-block" to={`/visits/${visitId}/works/${itemId}/parts/new`}>+ Запчасть</Link>
                  <Button block disabled={busy} onClick={() => setAssignOpen(true)}>Сменить исполнителя</Button>
                </>
              )}
              <Sheet open={assignOpen} title="Кому передать работу?" onClose={() => setAssignOpen(false)}>
                <Loadable query={mechanics}>
                  {(list) => (
                    <>
                      {list.map((m) => (
                        <Button key={m.id} block busy={assign.isPending && assign.variables === m.id} disabled={assign.isPending} onClick={() => assign.mutate(m.id)}>
                          {m.full_name}
                        </Button>
                      ))}
                      <Button block variant="ghost" disabled={assign.isPending} onClick={() => assign.mutate(null)}>Без исполнителя</Button>
                    </>
                  )}
                </Loadable>
              </Sheet>
            </div>
          );
        }}
      </Loadable>
    </>
  );
}
```

`web/src/routes.tsx` — import `WorkScreen`; replace the `/visits/:visitId/works/:itemId` element with `<RoleGate roles={ALL_ROLES}><WorkScreen /></RoleGate>`.

- [ ] **Step 4: Run tests**

Run: `cd web && npm test && npm run typecheck`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add web/src
git commit -m "feat(web): work screen — status steps, approval, reassign; mechanic view"
```

---

### Task 13: My works (mechanic)

**Files:**
- Create: `web/src/screens/MyWorksScreen.tsx`, `web/src/screens/MyWorksScreen.test.tsx`
- Modify: `web/src/routes.tsx` (route `/my`)

**Interfaces:**
- Consumes: `workItemsApi.mine`, query key `['myWorks']` (shared with Task 12).

- [ ] **Step 1: Write failing tests**

`web/src/screens/MyWorksScreen.test.tsx`:

```tsx
import { screen } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { makeMyWork } from '../test/fixtures';
import { renderApp } from '../test/render';
import { server } from '../test/server';

test('lists assigned works linking to the work screen', async () => {
  server.use(http.get('/api/work-items/mine', () => HttpResponse.json([makeMyWork(), makeMyWork({ id: 'w2', name: 'Диагностика подвески', plate_number: null, make_model: null })])));
  renderApp('/my', { as: 'mechanic' });
  const link = await screen.findByRole('link', { name: /Замена масла ДВС/ });
  expect(link).toHaveAttribute('href', '/visits/v1/works/w1');
  expect(screen.getByLabelText('Госномер А123ВС77')).toBeInTheDocument();
  expect(screen.getByText('Диагностика подвески')).toBeInTheDocument();
});

test('empty state', async () => {
  server.use(http.get('/api/work-items/mine', () => HttpResponse.json([])));
  renderApp('/my', { as: 'mechanic' });
  expect(await screen.findByText('Нет назначенных работ')).toBeInTheDocument();
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd web && npx vitest run src/screens/MyWorksScreen.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Implement**

`web/src/screens/MyWorksScreen.tsx`:

```tsx
import { useQuery } from '@tanstack/react-query';
import { workItemsApi } from '../api/endpoints';
import { WORK_STATUS_ICONS } from '../lib/labels';
import { Card } from '../ui/Card';
import { EmptyState } from '../ui/EmptyState';
import { Loadable } from '../ui/Loadable';
import { Plate } from '../ui/Plate';
import { ScreenHeader } from '../ui/ScreenHeader';
import { StatusTag } from '../ui/StatusTag';

export function MyWorksScreen() {
  const query = useQuery({ queryKey: ['myWorks'], queryFn: workItemsApi.mine });
  return (
    <>
      <ScreenHeader title="Мои работы" />
      <Loadable query={query}>
        {(items) =>
          items.length === 0 ? (
            <EmptyState text="Нет назначенных работ" />
          ) : (
            <div className="stack">
              {items.map((w) => (
                <Card key={w.id} to={`/visits/${w.visit_id}/works/${w.id}`}>
                  <div className="row">
                    <span>
                      <span aria-hidden="true">{WORK_STATUS_ICONS[w.status]} </span>
                      {w.name}
                    </span>
                    <StatusTag kind="work" status={w.status} />
                  </div>
                  {w.plate_number && (
                    <div className="row">
                      <Plate value={w.plate_number} />
                      <span className="hint">{w.make_model}</span>
                    </div>
                  )}
                </Card>
              ))}
            </div>
          )
        }
      </Loadable>
    </>
  );
}
```

`web/src/routes.tsx` — import; replace `/my` element with `<RoleGate roles={['mechanic']}><MyWorksScreen /></RoleGate>`.

- [ ] **Step 4: Run tests**

Run: `cd web && npm test && npm run typecheck`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add web/src
git commit -m "feat(web): mechanic's my works screen"
```

---

### Task 14: Search, client card, vehicle card

**Files:**
- Create: `web/src/lib/useDebounced.ts`, `web/src/screens/hits.tsx`, `web/src/screens/VisitHistory.tsx`, `web/src/screens/SearchScreen.tsx`, `web/src/screens/ClientScreen.tsx`, `web/src/screens/VehicleScreen.tsx`, `web/src/screens/browse.test.tsx`
- Modify: `web/src/routes.tsx` (routes `/search`, `/clients/:clientId`, `/vehicles/:vehicleId`), `web/src/theme.css` (append)

**Interfaces:**
- Consumes: `searchApi`, `clientsApi.get/vehicles`, `vehiclesApi.get/owner/workHistory`, `visitsApi.listForClient/listForVehicle`.
- Produces:
  - `useDebounced<T>(value: T, ms: number): T`.
  - `ClientHit({ id: string; onPick?: (c: Client) => void })`, `VehicleHit({ id: string; onPick?: (v: Vehicle) => void })`, `HitList({ hits: { entity: 'client' | 'vehicle'; id: string }[] })` — with `onPick` render a button, else a link card.
  - `VisitHistory({ visits: Visit[] })`.
  - Query keys `['client', id]`, `['clientVehicles', id]`, `['vehicle', id]`, `['vehicleOwner', id]`, `['workHistory', id]`, `['visitsFor', 'client' | 'vehicle', id]`, `['search', q]`, `['recent']`.

- [ ] **Step 1: Write failing tests**

`web/src/screens/browse.test.tsx`:

```tsx
import { screen, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { CLIENT, VEHICLE, makeVisit } from '../test/fixtures';
import { renderApp } from '../test/render';
import { server } from '../test/server';

function mockEntities() {
  server.use(
    http.get('/api/clients/c1', () => HttpResponse.json(CLIENT)),
    http.get('/api/vehicles/veh1', () => HttpResponse.json(VEHICLE)),
  );
}

test('search waits for input, then shows client and vehicle hits', async () => {
  mockEntities();
  const queries: string[] = [];
  server.use(
    http.get('/api/search/recent', () => HttpResponse.json([])),
    http.get('/api/search', ({ request }) => {
      queries.push(new URL(request.url).searchParams.get('q')!);
      return HttpResponse.json([
        { entity: 'client', id: 'c1', matched_field: 'full_name' },
        { entity: 'vehicle', id: 'veh1', matched_field: 'plate_number' },
      ]);
    }),
  );
  const { user } = renderApp('/search', { as: 'master' });
  expect(await screen.findByText('Введите госномер, VIN, телефон или ФИО')).toBeInTheDocument();
  await user.type(screen.getByRole('searchbox', { name: 'Поиск' }), 'Петров');
  expect(await screen.findByRole('link', { name: /Петров Иван/ })).toHaveAttribute('href', '/clients/c1');
  expect(screen.getByRole('link', { name: /Toyota Camry/ })).toHaveAttribute('href', '/vehicles/veh1');
  expect(queries).toEqual(['Петров']);
  expect(screen.getByTestId('location')).toHaveTextContent('/search?q=');
});

test('search with no results says so', async () => {
  server.use(
    http.get('/api/search/recent', () => HttpResponse.json([])),
    http.get('/api/search', () => HttpResponse.json([])),
  );
  const { user } = renderApp('/search', { as: 'master' });
  await user.type(await screen.findByRole('searchbox', { name: 'Поиск' }), 'zzzz');
  expect(await screen.findByText('Ничего не найдено')).toBeInTheDocument();
});

test('mechanic gets the vehicle-only hint', async () => {
  server.use(http.get('/api/search/recent', () => HttpResponse.json([{ entity_type: 'client', entity_id: 'c1' }])));
  renderApp('/search', { as: 'mechanic' });
  expect(await screen.findByText('Введите госномер или VIN')).toBeInTheDocument();
});

test('client card shows vehicles and visits', async () => {
  mockEntities();
  server.use(
    http.get('/api/clients/c1/vehicles', () => HttpResponse.json([VEHICLE])),
    http.get('/api/visits', ({ request }) => {
      expect(new URL(request.url).searchParams.get('client_id')).toBe('c1');
      return HttpResponse.json({ items: [makeVisit({ status: 'issued' })], has_more: false });
    }),
  );
  renderApp('/clients/c1', { as: 'master' });
  expect(await screen.findByText('Петров Иван')).toBeInTheDocument();
  expect(screen.getByRole('link', { name: '+7 900 123-45-67' })).toHaveAttribute('href', 'tel:+79001234567');
  const links = await screen.findAllByRole('link', { name: /Toyota Camry/ });
  expect(links.map((l) => l.getAttribute('href'))).toContain('/vehicles/veh1');
  expect(await screen.findByText('Выдан')).toBeInTheDocument();
  expect(screen.getByRole('link', { name: '+ Автомобиль' })).toHaveAttribute('href', '/vehicles/new?client_id=c1');
});

test('vehicle card for staff shows owner, visits, history and new visit', async () => {
  mockEntities();
  server.use(
    http.get('/api/vehicles/veh1/owner', () => HttpResponse.json(CLIENT)),
    http.get('/api/vehicles/veh1/work-history', () =>
      HttpResponse.json({ items: [{ visit_id: 'v1', visit_at: '2026-09-01T10:00:00Z', mileage: 110000, name: 'Замена масла ДВС', status: 'ready' }], has_more: false })),
    http.get('/api/visits', () => HttpResponse.json({ items: [makeVisit()], has_more: false })),
  );
  renderApp('/vehicles/veh1', { as: 'master' });
  expect(await screen.findByRole('link', { name: /Петров Иван/ })).toHaveAttribute('href', '/clients/c1');
  expect(screen.getByRole('link', { name: '+ Новый заезд' })).toHaveAttribute('href', '/visits/new?vehicle_id=veh1');
  expect(await screen.findByText('Замена масла ДВС')).toBeInTheDocument();
  expect(screen.getByText('01.09.2026 · 110 000 км')).toBeInTheDocument();
});

test('vehicle card for mechanic asks for neither owner nor visits', async () => {
  mockEntities();
  const visitsCalled = vi.fn();
  server.use(
    http.get('/api/vehicles/veh1/work-history', () => HttpResponse.json({ items: [], has_more: false })),
    http.get('/api/visits', () => {
      visitsCalled();
      return HttpResponse.json({ items: [], has_more: false });
    }),
  );
  renderApp('/vehicles/veh1', { as: 'mechanic' });
  expect(await screen.findByText('Работ по машине ещё не было')).toBeInTheDocument();
  expect(screen.queryByText('Владелец')).not.toBeInTheDocument();
  expect(screen.queryByRole('link', { name: '+ Новый заезд' })).not.toBeInTheDocument();
  await waitFor(() => expect(screen.getByText('Toyota Camry')).toBeInTheDocument());
  expect(visitsCalled).not.toHaveBeenCalled();
});
```

(`/owner` has no default handler, so an owner request would surface as an MSW unhandled-request error; `/visits` has a default one, hence the explicit spy.)

- [ ] **Step 2: Run to verify failure**

Run: `cd web && npx vitest run src/screens/browse.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Implement**

`web/src/lib/useDebounced.ts`:

```ts
import { useEffect, useState } from 'react';

export function useDebounced<T>(value: T, ms: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = window.setTimeout(() => setDebounced(value), ms);
    return () => window.clearTimeout(id);
  }, [value, ms]);
  return debounced;
}
```

`web/src/screens/hits.tsx`:

```tsx
import { useQuery } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { clientsApi, vehiclesApi } from '../api/endpoints';
import type { Client, Vehicle } from '../api/types';
import { Card } from '../ui/Card';
import { Plate } from '../ui/Plate';

function Hit({ to, onPick, children }: { to: string; onPick?: () => void; children: ReactNode }) {
  if (onPick) {
    return <button type="button" className="card card-link hit" onClick={onPick}>{children}</button>;
  }
  return <Card to={to}>{children}</Card>;
}

export function ClientHit({ id, onPick }: { id: string; onPick?: (c: Client) => void }) {
  const q = useQuery({ queryKey: ['client', id], queryFn: () => clientsApi.get(id) });
  if (!q.data) return null;
  const client = q.data;
  return (
    <Hit to={`/clients/${id}`} onPick={onPick && (() => onPick(client))}>
      <b>{client.full_name}</b>
      <span className="hint">{client.phone_display}</span>
    </Hit>
  );
}

export function VehicleHit({ id, onPick }: { id: string; onPick?: (v: Vehicle) => void }) {
  const q = useQuery({ queryKey: ['vehicle', id], queryFn: () => vehiclesApi.get(id) });
  if (!q.data) return null;
  const vehicle = q.data;
  return (
    <Hit to={`/vehicles/${id}`} onPick={onPick && (() => onPick(vehicle))}>
      <div className="row">
        <Plate value={vehicle.plate_number} />
        <span>{vehicle.make} {vehicle.model}</span>
      </div>
      <span className="hint mono">{vehicle.vin}</span>
    </Hit>
  );
}

export function HitList({ hits }: { hits: { entity: 'client' | 'vehicle'; id: string }[] }) {
  return (
    <div className="stack">
      {hits.map((h) =>
        h.entity === 'client' ? <ClientHit key={`c-${h.id}`} id={h.id} /> : <VehicleHit key={`v-${h.id}`} id={h.id} />,
      )}
    </div>
  );
}
```

`web/src/screens/VisitHistory.tsx`:

```tsx
import type { Visit } from '../api/types';
import { formatDate } from '../lib/format';
import { Card } from '../ui/Card';
import { EmptyState } from '../ui/EmptyState';
import { StatusTag } from '../ui/StatusTag';

export function VisitHistory({ visits }: { visits: Visit[] }) {
  if (visits.length === 0) return <EmptyState text="Заездов нет" />;
  return (
    <div className="stack">
      {visits.map((v) => (
        <Card key={v.id} to={`/visits/${v.id}`}>
          <div className="row">
            <span>{formatDate(v.created_at)} · {v.make_model}</span>
            <StatusTag kind="visit" status={v.status} />
          </div>
        </Card>
      ))}
    </div>
  );
}
```

`web/src/screens/SearchScreen.tsx`:

```tsx
import { useQuery } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { searchApi } from '../api/endpoints';
import { useAuth } from '../auth/AuthProvider';
import { useDebounced } from '../lib/useDebounced';
import { EmptyState } from '../ui/EmptyState';
import { Loadable } from '../ui/Loadable';
import { ScreenHeader } from '../ui/ScreenHeader';
import { HitList } from './hits';

export function SearchScreen() {
  const { user } = useAuth();
  const isMechanic = user!.role === 'mechanic';
  const [params, setParams] = useSearchParams();
  const [text, setText] = useState(params.get('q') ?? '');
  const query = useDebounced(text.trim(), 300);
  useEffect(() => {
    setParams(query ? { q: query } : {}, { replace: true });
  }, [query, setParams]);
  const active = query.length >= 2;
  const results = useQuery({ queryKey: ['search', query], queryFn: () => searchApi.search(query), enabled: active });
  const recent = useQuery({ queryKey: ['recent'], queryFn: searchApi.recent, enabled: !active });
  const prompt = isMechanic ? 'Госномер или VIN' : 'Госномер, VIN, телефон или ФИО';
  return (
    <>
      <ScreenHeader title="Поиск" />
      <div className="field search-field">
        <input type="search" aria-label="Поиск" placeholder={prompt} value={text} onChange={(e) => setText(e.target.value)} autoFocus />
      </div>
      {active ? (
        <Loadable query={results}>
          {(hits) => (hits.length ? <HitList hits={hits} /> : <EmptyState text="Ничего не найдено" />)}
        </Loadable>
      ) : (
        <Loadable query={recent}>
          {(views) => {
            const hits = views
              .map((v) => ({ entity: v.entity_type, id: v.entity_id }))
              .filter((h) => !isMechanic || h.entity === 'vehicle');
            if (hits.length === 0) return <EmptyState text={`Введите ${prompt.charAt(0).toLowerCase()}${prompt.slice(1)}`} />;
            return (
              <>
                <h2 className="section-title">Недавние</h2>
                <HitList hits={hits} />
              </>
            );
          }}
        </Loadable>
      )}
    </>
  );
}
```

`web/src/screens/ClientScreen.tsx`:

```tsx
import { useQuery } from '@tanstack/react-query';
import { Link, useParams } from 'react-router-dom';
import { clientsApi, visitsApi } from '../api/endpoints';
import { Card } from '../ui/Card';
import { EmptyState } from '../ui/EmptyState';
import { Loadable } from '../ui/Loadable';
import { Plate } from '../ui/Plate';
import { ScreenHeader } from '../ui/ScreenHeader';
import { VisitHistory } from './VisitHistory';

export function ClientScreen() {
  const { clientId = '' } = useParams();
  const client = useQuery({ queryKey: ['client', clientId], queryFn: () => clientsApi.get(clientId) });
  const vehicles = useQuery({ queryKey: ['clientVehicles', clientId], queryFn: () => clientsApi.vehicles(clientId) });
  const visits = useQuery({ queryKey: ['visitsFor', 'client', clientId], queryFn: () => visitsApi.listForClient(clientId) });
  return (
    <>
      <ScreenHeader title="Клиент" back />
      <Loadable query={client} notFound="Клиент не найден">
        {(c) => (
          <div className="stack">
            <div className="card">
              <b className="title">{c.full_name}</b>
              <a className="hint" href={`tel:${c.phone_display.replace(/[^\d+]/g, '')}`}>{c.phone_display}</a>
            </div>
            <h2 className="section-title">Автомобили</h2>
            <Loadable query={vehicles}>
              {(list) =>
                list.length === 0 ? (
                  <EmptyState text="Машин нет" />
                ) : (
                  <div className="stack">
                    {list.map((v) => (
                      <Card key={v.id} to={`/vehicles/${v.id}`}>
                        <div className="row">
                          <Plate value={v.plate_number} />
                          <span>{v.make} {v.model}</span>
                        </div>
                      </Card>
                    ))}
                  </div>
                )
              }
            </Loadable>
            <Link className="btn btn-block" to={`/vehicles/new?client_id=${clientId}`}>+ Автомобиль</Link>
            <h2 className="section-title">Заезды</h2>
            <Loadable query={visits}>{(d) => <VisitHistory visits={d.items} />}</Loadable>
          </div>
        )}
      </Loadable>
    </>
  );
}
```

`web/src/screens/VehicleScreen.tsx`:

```tsx
import { useQuery } from '@tanstack/react-query';
import { Link, useParams } from 'react-router-dom';
import { vehiclesApi, visitsApi } from '../api/endpoints';
import { useAuth } from '../auth/AuthProvider';
import { formatDate, formatKm } from '../lib/format';
import { WORK_STATUS_ICONS } from '../lib/labels';
import { Card } from '../ui/Card';
import { EmptyState } from '../ui/EmptyState';
import { Loadable } from '../ui/Loadable';
import { Plate } from '../ui/Plate';
import { ScreenHeader } from '../ui/ScreenHeader';
import { VisitHistory } from './VisitHistory';

export function VehicleScreen() {
  const { vehicleId = '' } = useParams();
  const { user } = useAuth();
  const isStaff = user!.role !== 'mechanic';
  const vehicle = useQuery({ queryKey: ['vehicle', vehicleId], queryFn: () => vehiclesApi.get(vehicleId) });
  const owner = useQuery({ queryKey: ['vehicleOwner', vehicleId], queryFn: () => vehiclesApi.owner(vehicleId), enabled: isStaff });
  const visits = useQuery({ queryKey: ['visitsFor', 'vehicle', vehicleId], queryFn: () => visitsApi.listForVehicle(vehicleId), enabled: isStaff });
  const history = useQuery({ queryKey: ['workHistory', vehicleId], queryFn: () => vehiclesApi.workHistory(vehicleId) });
  return (
    <>
      <ScreenHeader title="Машина" back />
      <Loadable query={vehicle} notFound="Машина не найдена">
        {(v) => (
          <div className="stack">
            <div className="card">
              <Plate value={v.plate_number} />
              <b className="title">{v.make} {v.model}</b>
              <span className="hint mono">VIN {v.vin}</span>
              <span className="hint">Пробег {formatKm(v.mileage_current)}</span>
            </div>
            {isStaff && (
              <>
                <Loadable query={owner}>
                  {(o) =>
                    o ? (
                      <Card to={`/clients/${o.id}`}>
                        <span className="hint">Владелец</span>
                        <b>{o.full_name}</b>
                      </Card>
                    ) : (
                      <EmptyState text="Владелец не указан" />
                    )
                  }
                </Loadable>
                <Link className="btn btn-primary btn-block" to={`/visits/new?vehicle_id=${v.id}`}>+ Новый заезд</Link>
                <h2 className="section-title">Заезды</h2>
                <Loadable query={visits}>{(d) => <VisitHistory visits={d.items} />}</Loadable>
              </>
            )}
            <h2 className="section-title">История работ</h2>
            <Loadable query={history}>
              {(h) =>
                h.items.length === 0 ? (
                  <EmptyState text="Работ по машине ещё не было" />
                ) : (
                  <div className="card">
                    {h.items.map((w, i) => (
                      <div key={`${w.visit_id}-${i}`} className="list-row">
                        <span aria-hidden="true">{WORK_STATUS_ICONS[w.status]}</span>
                        <span>
                          <span className="block">{w.name}</span>
                          <span className="hint block">{formatDate(w.visit_at)} · {formatKm(w.mileage)}</span>
                        </span>
                        <span />
                      </div>
                    ))}
                  </div>
                )
              }
            </Loadable>
          </div>
        )}
      </Loadable>
    </>
  );
}
```

`web/src/theme.css` — append:

```css
.hit { text-align: left; border: 0; width: 100%; color: inherit; font: inherit; }
.title { font-size: 18px; }
.search-field { margin-bottom: 12px; }
```

`web/src/routes.tsx` — import the three screens; replace elements: `/search` → `<RoleGate roles={ALL_ROLES}><SearchScreen /></RoleGate>`, `/clients/:clientId` → `<RoleGate roles={STAFF}><ClientScreen /></RoleGate>`, `/vehicles/:vehicleId` → `<RoleGate roles={ALL_ROLES}><VehicleScreen /></RoleGate>`.

- [ ] **Step 4: Run tests**

Run: `cd web && npm test && npm run typecheck`
Expected: all pass. If the "search waits for input" test records more than one query (the debounce firing on an intermediate value), `user.type` types fast enough that only the final value survives 300 ms; if it is flaky, assert `queries.at(-1) === 'Петров'` and `queries.every((q) => q.length >= 2)` instead.

- [ ] **Step 5: Commit**

```bash
git add web/src
git commit -m "feat(web): search with recent views, client and vehicle cards"
```

---

### Task 15: Forms — add work, add part

**Files:**
- Create: `web/src/ui/SelectField.tsx`, `web/src/forms/formErrors.ts`, `web/src/forms/AddWorkForm.tsx`, `web/src/forms/AddPartForm.tsx`, `web/src/forms/workForms.test.tsx`
- Modify: `web/src/lib/format.ts` (add `parseNumber`), `web/src/routes.tsx` (routes `works/new`, `parts/new`)

**Interfaces:**
- Consumes: `catalogApi.suggest`, `usersApi.mechanics`, `workItemsApi.add/addPart`, `ApiError`, `useDebounced`.
- Produces:
  - `SelectField(props: SelectHTMLAttributes & { label: string; error?: string; options: { value: string; label: string }[] })`.
  - `interface FormErrors { fields: Record<string, string>; general: string }`, `NO_ERRORS`, `toFormErrors(error: unknown, known: string[], conflictField?: string): FormErrors` — 409 goes to `conflictField`; 422 field keys in `known` go to fields, others to `general`.
  - `parseNumber(raw: string): number | null` — accepts `,` as decimal separator; empty/invalid → `null`.

- [ ] **Step 1: Write failing tests**

`web/src/forms/workForms.test.tsx`:

```tsx
import { screen, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { USERS, renderApp } from '../test/render';
import { makeWorkItem, mockVisitPage } from '../test/fixtures';
import { server } from '../test/server';

function mockCommon() {
  server.use(
    http.get('/api/users/mechanics', () => HttpResponse.json([USERS.mechanic])),
    http.get('/api/catalog/suggest', () =>
      HttpResponse.json([{ id: 'cat1', name: 'Замена масла ДВС', category: 'maintenance', default_norm_hours: 0.5 }])),
  );
}

test('picking from the catalog fills category and hours, posts and returns to the visit', async () => {
  mockCommon();
  mockVisitPage();
  let body: unknown;
  server.use(http.post('/api/visits/v1/work-items', async ({ request }) => {
    body = await request.json();
    return HttpResponse.json(makeWorkItem(), { status: 201 });
  }));
  const { user } = renderApp('/visits/v1/works/new', { as: 'master' });
  await user.type(await screen.findByLabelText('Название'), 'Замена');
  await user.click(await screen.findByRole('option', { name: /Замена масла ДВС/ }));
  expect(screen.queryByLabelText('Категория')).not.toBeInTheDocument();
  expect(screen.getByLabelText('Нормо-часы')).toHaveValue('0.5');
  await user.type(screen.getByLabelText('Ставка, ₽/ч'), '2400');
  await user.selectOptions(screen.getByLabelText('Исполнитель'), 'u-mech');
  await user.click(screen.getByRole('button', { name: 'Добавить работу' }));
  await waitFor(() =>
    expect(body).toEqual({
      catalog_item_id: 'cat1', free_text_name: null, category: 'maintenance',
      norm_hours: 0.5, hourly_rate: 2400, assigned_mechanic_id: 'u-mech',
    }),
  );
  await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/visits/v1'));
});

test('free-text work needs a category and numbers; nothing is sent until valid', async () => {
  mockCommon();
  const post = vi.fn();
  server.use(http.post('/api/visits/v1/work-items', () => {
    post();
    return HttpResponse.json(makeWorkItem(), { status: 201 });
  }));
  const { user } = renderApp('/visits/v1/works/new', { as: 'master' });
  await user.type(await screen.findByLabelText('Название'), 'Своя работа');
  await user.type(screen.getByLabelText('Нормо-часы'), 'abc');
  await user.click(screen.getByRole('button', { name: 'Добавить работу' }));
  expect(screen.getByText('Выберите категорию')).toBeInTheDocument();
  expect(screen.getByText('Нормо-часы — число больше 0')).toBeInTheDocument();
  expect(post).not.toHaveBeenCalled();
});

test('API 422 lands on the field', async () => {
  mockCommon();
  server.use(http.post('/api/visits/v1/work-items', () =>
    HttpResponse.json({ detail: [{ loc: ['body', 'hourly_rate'], msg: 'Input should be greater than 0' }] }, { status: 422 })));
  const { user } = renderApp('/visits/v1/works/new', { as: 'master' });
  await user.type(await screen.findByLabelText('Название'), 'Своя работа');
  await user.selectOptions(screen.getByLabelText('Категория'), 'other');
  await user.type(screen.getByLabelText('Нормо-часы'), '1,5');
  await user.type(screen.getByLabelText('Ставка, ₽/ч'), '0');
  await user.click(screen.getByRole('button', { name: 'Добавить работу' }));
  expect(await screen.findByText('Input should be greater than 0')).toBeInTheDocument();
  expect(screen.getByLabelText('Название')).toHaveValue('Своя работа');
});

test('add part posts and returns to the work', async () => {
  let body: unknown;
  server.use(
    http.post('/api/visits/v1/part-items', async ({ request }) => {
      body = await request.json();
      return HttpResponse.json({ id: 'p1', name: 'Фильтр', quantity: 2, unit_price: 450.5 }, { status: 201 });
    }),
    http.get('/api/visits/v1/work-items', () => HttpResponse.json([makeWorkItem()])),
  );
  const { user } = renderApp('/visits/v1/works/w1/parts/new', { as: 'master' });
  await user.type(await screen.findByLabelText('Название'), 'Фильтр');
  await user.clear(screen.getByLabelText('Количество'));
  await user.type(screen.getByLabelText('Количество'), '2');
  await user.type(screen.getByLabelText('Цена за штуку, ₽'), '450,5');
  await user.click(screen.getByRole('button', { name: 'Добавить запчасть' }));
  await waitFor(() => expect(body).toEqual({ work_item_id: 'w1', name: 'Фильтр', quantity: 2, unit_price: 450.5 }));
  await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/visits/v1/works/w1'));
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd web && npx vitest run src/forms/workForms.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Implement helpers**

`web/src/lib/format.ts` — append:

```ts
export function parseNumber(raw: string): number | null {
  const text = raw.trim().replace(',', '.');
  if (!text) return null;
  const n = Number(text);
  return Number.isFinite(n) ? n : null;
}
```

`web/src/ui/SelectField.tsx`:

```tsx
import { useId, type SelectHTMLAttributes } from 'react';

interface Props extends SelectHTMLAttributes<HTMLSelectElement> {
  label: string;
  error?: string;
  options: { value: string; label: string }[];
}

export function SelectField({ label, error, options, id, ...rest }: Props) {
  const autoId = useId();
  const fieldId = id ?? autoId;
  return (
    <div className="field">
      <label htmlFor={fieldId}>{label}</label>
      <select id={fieldId} aria-invalid={error ? true : undefined} {...rest}>
        {options.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
      {error && <p className="field-error" role="alert">{error}</p>}
    </div>
  );
}
```

`web/src/forms/formErrors.ts`:

```ts
import { ApiError } from '../api/client';

export interface FormErrors {
  fields: Record<string, string>;
  general: string;
}

export const NO_ERRORS: FormErrors = { fields: {}, general: '' };

export function toFormErrors(error: unknown, known: string[], conflictField?: string): FormErrors {
  if (!(error instanceof ApiError)) return { fields: {}, general: 'Ошибка' };
  if (error.status === 409 && conflictField) return { fields: { [conflictField]: error.message }, general: '' };
  const fields: Record<string, string> = {};
  const other: string[] = [];
  for (const [key, msg] of Object.entries(error.fields)) {
    if (known.includes(key)) fields[key] = msg;
    else other.push(msg);
  }
  const general = Object.keys(fields).length === 0 ? error.message : other.join('; ');
  return { fields, general };
}
```

- [ ] **Step 4: Implement forms**

`web/src/forms/AddWorkForm.tsx`:

```tsx
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { catalogApi, usersApi, workItemsApi } from '../api/endpoints';
import type { CatalogItem, WorkCategory, WorkItemCreate } from '../api/types';
import { parseNumber } from '../lib/format';
import { WORK_CATEGORY_LABELS } from '../lib/labels';
import { useDebounced } from '../lib/useDebounced';
import { telegram } from '../telegram/webapp';
import { Button } from '../ui/Button';
import { Field } from '../ui/Field';
import { ScreenHeader } from '../ui/ScreenHeader';
import { SelectField } from '../ui/SelectField';
import { NO_ERRORS, toFormErrors, type FormErrors } from './formErrors';

const KNOWN = ['free_text_name', 'category', 'norm_hours', 'hourly_rate', 'assigned_mechanic_id'];
const CATEGORY_OPTIONS = [
  { value: '', label: 'Выберите…' },
  ...Object.entries(WORK_CATEGORY_LABELS).map(([value, label]) => ({ value, label })),
];

export function AddWorkForm() {
  const { visitId = '' } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [name, setName] = useState('');
  const [picked, setPicked] = useState<CatalogItem | null>(null);
  const [category, setCategory] = useState<WorkCategory | ''>('');
  const [hours, setHours] = useState('');
  const [rate, setRate] = useState('');
  const [mechanicId, setMechanicId] = useState('');
  const [errors, setErrors] = useState<FormErrors>(NO_ERRORS);
  const debouncedName = useDebounced(name.trim(), 300);
  const suggestions = useQuery({
    queryKey: ['catalog', debouncedName],
    queryFn: () => catalogApi.suggest(debouncedName),
    enabled: !picked && debouncedName.length >= 2,
  });
  const mechanics = useQuery({ queryKey: ['mechanics'], queryFn: usersApi.mechanics });
  const save = useMutation({
    mutationFn: (body: WorkItemCreate) => workItemsApi.add(visitId, body),
    onSuccess: async () => {
      telegram.haptic('success');
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['workItems', visitId] }),
        queryClient.invalidateQueries({ queryKey: ['visit', visitId] }),
      ]);
      navigate(`/visits/${visitId}`, { replace: true });
    },
    onError: (e) => {
      telegram.haptic('error');
      setErrors(toFormErrors(e, KNOWN));
    },
  });

  function pick(item: CatalogItem) {
    setPicked(item);
    setName(item.name);
    setCategory(item.category);
    setHours(String(item.default_norm_hours));
  }

  function changeName(value: string) {
    setName(value);
    if (picked && value !== picked.name) setPicked(null);
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    const h = parseNumber(hours);
    const r = parseNumber(rate);
    const fields: Record<string, string> = {};
    if (!name.trim()) fields.free_text_name = 'Введите название работы';
    if (!picked && !category) fields.category = 'Выберите категорию';
    if (h === null || h <= 0) fields.norm_hours = 'Нормо-часы — число больше 0';
    if (r === null || r < 0) fields.hourly_rate = 'Ставка — число';
    if (Object.keys(fields).length) {
      setErrors({ fields, general: '' });
      return;
    }
    setErrors(NO_ERRORS);
    save.mutate({
      catalog_item_id: picked?.id ?? null,
      free_text_name: picked ? null : name.trim(),
      category: (picked?.category ?? category) as WorkCategory,
      norm_hours: h!,
      hourly_rate: r!,
      assigned_mechanic_id: mechanicId || null,
    });
  }

  return (
    <>
      <ScreenHeader title="Новая работа" back />
      <form className="form" noValidate onSubmit={submit}>
        <Field label="Название" value={name} autoComplete="off" onChange={(e) => changeName(e.target.value)}
          error={errors.fields.free_text_name} hint={picked ? 'Из справочника' : undefined} />
        {!picked && suggestions.data && suggestions.data.length > 0 && (
          <div className="suggest" role="listbox" aria-label="Справочник работ">
            {suggestions.data.map((s) => (
              <button key={s.id} type="button" role="option" aria-selected={false} onClick={() => pick(s)}>
                {s.name} <span className="hint">· {s.default_norm_hours} н/ч</span>
              </button>
            ))}
          </div>
        )}
        {!picked && (
          <SelectField label="Категория" value={category} options={CATEGORY_OPTIONS}
            onChange={(e) => setCategory(e.target.value as WorkCategory | '')} error={errors.fields.category} />
        )}
        <Field label="Нормо-часы" inputMode="decimal" value={hours} onChange={(e) => setHours(e.target.value)} error={errors.fields.norm_hours} />
        <Field label="Ставка, ₽/ч" inputMode="decimal" value={rate} onChange={(e) => setRate(e.target.value)} error={errors.fields.hourly_rate} />
        <SelectField label="Исполнитель" value={mechanicId} onChange={(e) => setMechanicId(e.target.value)}
          error={errors.fields.assigned_mechanic_id}
          options={[{ value: '', label: 'Без исполнителя' }, ...(mechanics.data ?? []).map((m) => ({ value: m.id, label: m.full_name }))]} />
        {errors.general && <p className="form-error" role="alert">{errors.general}</p>}
        <Button type="submit" variant="primary" block busy={save.isPending}>Добавить работу</Button>
      </form>
    </>
  );
}
```

`web/src/forms/AddPartForm.tsx`:

```tsx
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { workItemsApi } from '../api/endpoints';
import type { PartItemCreate } from '../api/types';
import { parseNumber } from '../lib/format';
import { telegram } from '../telegram/webapp';
import { Button } from '../ui/Button';
import { Field } from '../ui/Field';
import { ScreenHeader } from '../ui/ScreenHeader';
import { NO_ERRORS, toFormErrors, type FormErrors } from './formErrors';

export function AddPartForm() {
  const { visitId = '', itemId = '' } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [name, setName] = useState('');
  const [quantity, setQuantity] = useState('1');
  const [price, setPrice] = useState('');
  const [errors, setErrors] = useState<FormErrors>(NO_ERRORS);
  const save = useMutation({
    mutationFn: (body: PartItemCreate) => workItemsApi.addPart(visitId, body),
    onSuccess: async () => {
      telegram.haptic('success');
      await queryClient.invalidateQueries({ queryKey: ['visit', visitId] });
      navigate(`/visits/${visitId}/works/${itemId}`, { replace: true });
    },
    onError: (e) => {
      telegram.haptic('error');
      setErrors(toFormErrors(e, ['name', 'quantity', 'unit_price']));
    },
  });

  function submit(e: FormEvent) {
    e.preventDefault();
    const q = parseNumber(quantity);
    const p = parseNumber(price);
    const fields: Record<string, string> = {};
    if (!name.trim()) fields.name = 'Введите название запчасти';
    if (q === null || q < 1 || !Number.isInteger(q)) fields.quantity = 'Количество — целое число от 1';
    if (p === null || p < 0) fields.unit_price = 'Цена — число';
    if (Object.keys(fields).length) {
      setErrors({ fields, general: '' });
      return;
    }
    setErrors(NO_ERRORS);
    save.mutate({ work_item_id: itemId, name: name.trim(), quantity: q!, unit_price: p! });
  }

  return (
    <>
      <ScreenHeader title="Новая запчасть" back />
      <form className="form" noValidate onSubmit={submit}>
        <Field label="Название" value={name} onChange={(e) => setName(e.target.value)} error={errors.fields.name} />
        <Field label="Количество" inputMode="numeric" value={quantity} onChange={(e) => setQuantity(e.target.value)} error={errors.fields.quantity} />
        <Field label="Цена за штуку, ₽" inputMode="decimal" value={price} onChange={(e) => setPrice(e.target.value)} error={errors.fields.unit_price} />
        {errors.general && <p className="form-error" role="alert">{errors.general}</p>}
        <Button type="submit" variant="primary" block busy={save.isPending}>Добавить запчасть</Button>
      </form>
    </>
  );
}
```

`web/src/routes.tsx` — import both; replace `/visits/:visitId/works/new` → `<RoleGate roles={STAFF}><AddWorkForm /></RoleGate>`, `/visits/:visitId/works/:itemId/parts/new` → `<RoleGate roles={STAFF}><AddPartForm /></RoleGate>`.

- [ ] **Step 5: Run tests**

Run: `cd web && npm test && npm run typecheck`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add web/src
git commit -m "feat(web): add work (catalog suggest) and add part forms"
```

---

### Task 16: Forms — client, vehicle, paper consent, staff; More screen

**Files:**
- Create: `web/src/forms/ClientForm.tsx`, `web/src/forms/VehicleForm.tsx`, `web/src/forms/PaperConsentForm.tsx`, `web/src/forms/StaffForm.tsx`, `web/src/forms/entryRoutes.tsx`, `web/src/screens/MoreScreen.tsx`, `web/src/forms/entityForms.test.tsx`
- Modify: `web/src/routes.tsx` (routes `/clients/new`, `/vehicles/new`, `/consent/paper`, `/staff/new`, `/more`)

**Interfaces:**
- Consumes: `clientsApi.create`, `vehiclesApi.create/attachOwner`, `consentApi.paper`, `usersApi.create`, validators, `toFormErrors`, `useAuth().signOut`.
- Produces (reused by the wizard in Task 17):
  - `ClientForm({ initialQuery?: string; submitLabel?: string; onCreated: (c: Client) => void })` — prefills phone if `initialQuery` is a valid phone, else full name.
  - `VehicleForm({ clientId?: string; initialQuery?: string; submitLabel?: string; onCreated: (v: Vehicle) => void })` — prefills plate or VIN from `initialQuery`; sends normalized VIN and plate; attaches owner when `clientId` given.
  - Route wrappers `NewClientRoute`, `NewVehicleRoute` in `entryRoutes.tsx`.

- [ ] **Step 1: Write failing tests**

`web/src/forms/entityForms.test.tsx`:

```tsx
import { screen, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { CLIENT, VEHICLE } from '../test/fixtures';
import { USERS, renderApp } from '../test/render';
import { server } from '../test/server';

function mockClientPage() {
  server.use(
    http.get('/api/clients/c1', () => HttpResponse.json(CLIENT)),
    http.get('/api/clients/c1/vehicles', () => HttpResponse.json([])),
    http.get('/api/visits', () => HttpResponse.json({ items: [], has_more: false })),
  );
}

test('new client: bad phone blocked locally, 409 shown at phone', async () => {
  const post = vi.fn();
  server.use(http.post('/api/clients', () => {
    post();
    return HttpResponse.json({ detail: 'Клиент с таким телефоном уже есть' }, { status: 409 });
  }));
  const { user } = renderApp('/clients/new', { as: 'master' });
  await user.type(await screen.findByLabelText('Телефон'), '123');
  await user.type(screen.getByLabelText('ФИО'), 'Петров Иван');
  await user.click(screen.getByRole('button', { name: 'Создать клиента' }));
  expect(screen.getByText('Неверный формат телефона. Пример: +7 900 123-45-67')).toBeInTheDocument();
  expect(post).not.toHaveBeenCalled();
  await user.clear(screen.getByLabelText('Телефон'));
  await user.type(screen.getByLabelText('Телефон'), '+7 900 123-45-67');
  await user.click(screen.getByRole('button', { name: 'Создать клиента' }));
  expect(await screen.findByText('Клиент с таким телефоном уже есть')).toBeInTheDocument();
});

test('new client success opens the client card', async () => {
  mockClientPage();
  server.use(http.post('/api/clients', () => HttpResponse.json(CLIENT, { status: 201 })));
  const { user } = renderApp('/clients/new', { as: 'master' });
  await user.type(await screen.findByLabelText('Телефон'), '89001234567');
  await user.type(screen.getByLabelText('ФИО'), 'Петров Иван');
  await user.click(screen.getByRole('button', { name: 'Создать клиента' }));
  await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/clients/c1'));
});

test('new vehicle for a client normalizes input and attaches the owner', async () => {
  let created: unknown;
  let owner: unknown;
  server.use(
    http.post('/api/vehicles', async ({ request }) => {
      created = await request.json();
      return HttpResponse.json(VEHICLE, { status: 201 });
    }),
    http.post('/api/vehicles/veh1/owners', async ({ request }) => {
      owner = await request.json();
      return HttpResponse.json({ id: 'o1' }, { status: 201 });
    }),
    http.get('/api/vehicles/veh1', () => HttpResponse.json(VEHICLE)),
    http.get('/api/vehicles/veh1/owner', () => HttpResponse.json(CLIENT)),
    http.get('/api/vehicles/veh1/work-history', () => HttpResponse.json({ items: [], has_more: false })),
    http.get('/api/visits', () => HttpResponse.json({ items: [], has_more: false })),
  );
  const { user } = renderApp('/vehicles/new?client_id=c1', { as: 'master' });
  await user.type(await screen.findByLabelText('VIN или номер кузова'), 'jtdbr32e 720012345');
  await user.type(screen.getByLabelText('Госномер'), 'a123bc77');
  await user.type(screen.getByLabelText('Марка'), 'Toyota');
  await user.type(screen.getByLabelText('Модель'), 'Camry');
  await user.click(screen.getByRole('button', { name: 'Добавить автомобиль' }));
  await waitFor(() => expect(created).toEqual({ vin: 'JTDBR32E720012345', plate_number: 'А123ВС77', make: 'Toyota', model: 'Camry' }));
  await waitFor(() => expect(owner).toMatchObject({ client_id: 'c1' }));
  await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/vehicles/veh1'));
});

test('duplicate VIN shows at the VIN field', async () => {
  server.use(http.post('/api/vehicles', () => HttpResponse.json({ detail: 'Машина с таким VIN уже есть' }, { status: 409 })));
  const { user } = renderApp('/vehicles/new', { as: 'master' });
  await user.type(await screen.findByLabelText('VIN или номер кузова'), 'JTDBR32E720012345');
  await user.type(screen.getByLabelText('Госномер'), 'А123ВС77');
  await user.type(screen.getByLabelText('Марка'), 'Toyota');
  await user.type(screen.getByLabelText('Модель'), 'Camry');
  await user.click(screen.getByRole('button', { name: 'Добавить автомобиль' }));
  expect(await screen.findByText('Машина с таким VIN уже есть')).toBeInTheDocument();
});

test('paper consent registers and opens the client', async () => {
  mockClientPage();
  server.use(http.post('/api/consent/paper', () => HttpResponse.json({ client_id: 'c1' })));
  const { user } = renderApp('/consent/paper', { as: 'master' });
  await user.type(await screen.findByLabelText('Телефон'), '+79001234567');
  await user.type(screen.getByLabelText('ФИО'), 'Петров Иван');
  await user.click(screen.getByRole('button', { name: 'Зарегистрировать' }));
  await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/clients/c1'));
});

test('admin adds staff', async () => {
  let body: unknown;
  server.use(http.post('/api/users', async ({ request }) => {
    body = await request.json();
    return HttpResponse.json({ ...USERS.mechanic, id: 'u-new' }, { status: 201 });
  }));
  const { user } = renderApp('/staff/new', { as: 'admin' });
  await user.selectOptions(await screen.findByLabelText('Роль'), 'mechanic');
  await user.type(screen.getByLabelText('ФИО'), 'Ким Алексей');
  await user.type(screen.getByLabelText('Telegram ID'), '123456789');
  await user.click(screen.getByRole('button', { name: 'Добавить сотрудника' }));
  await waitFor(() => expect(body).toEqual({ role: 'mechanic', full_name: 'Ким Алексей', telegram_id: 123456789 }));
  expect(await screen.findByText('Сотрудник добавлен')).toBeInTheDocument();
  await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/more'));
});

test('more: staff link only for admin; sign out returns to login', async () => {
  server.use(http.get('/api/auth/dev-users', () => HttpResponse.json([])));
  const { user } = renderApp('/more', { as: 'master' });
  expect(await screen.findByRole('link', { name: 'Бумажное согласие' })).toBeInTheDocument();
  expect(screen.queryByRole('link', { name: 'Добавить сотрудника' })).not.toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Выйти' }));
  await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/login'));
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd web && npx vitest run src/forms/entityForms.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Implement forms**

`web/src/forms/ClientForm.tsx`:

```tsx
import { useMutation } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { clientsApi } from '../api/endpoints';
import type { Client } from '../api/types';
import { PHONE_FORMAT_ERROR, isValidPhone } from '../lib/validators';
import { telegram } from '../telegram/webapp';
import { Button } from '../ui/Button';
import { Field } from '../ui/Field';
import { NO_ERRORS, toFormErrors, type FormErrors } from './formErrors';

interface Props {
  initialQuery?: string;
  submitLabel?: string;
  onCreated: (client: Client) => void;
}

export function ClientForm({ initialQuery = '', submitLabel = 'Создать клиента', onCreated }: Props) {
  const queryIsPhone = isValidPhone(initialQuery);
  const [phone, setPhone] = useState(queryIsPhone ? initialQuery : '');
  const [fullName, setFullName] = useState(queryIsPhone ? '' : initialQuery);
  const [errors, setErrors] = useState<FormErrors>(NO_ERRORS);
  const save = useMutation({
    mutationFn: () => clientsApi.create(fullName.trim(), phone.trim()),
    onSuccess: (client) => {
      telegram.haptic('success');
      onCreated(client);
    },
    onError: (e) => {
      telegram.haptic('error');
      setErrors(toFormErrors(e, ['phone', 'full_name'], 'phone'));
    },
  });

  function submit(e: FormEvent) {
    e.preventDefault();
    const fields: Record<string, string> = {};
    if (!isValidPhone(phone)) fields.phone = PHONE_FORMAT_ERROR;
    if (!fullName.trim()) fields.full_name = 'Введите ФИО';
    if (Object.keys(fields).length) {
      setErrors({ fields, general: '' });
      return;
    }
    setErrors(NO_ERRORS);
    save.mutate();
  }

  return (
    <form className="form" noValidate onSubmit={submit}>
      <Field label="Телефон" type="tel" inputMode="tel" value={phone} onChange={(e) => setPhone(e.target.value)} error={errors.fields.phone} />
      <Field label="ФИО" value={fullName} onChange={(e) => setFullName(e.target.value)} error={errors.fields.full_name} />
      {errors.general && <p className="form-error" role="alert">{errors.general}</p>}
      <Button type="submit" variant="primary" block busy={save.isPending}>{submitLabel}</Button>
    </form>
  );
}
```

`web/src/forms/VehicleForm.tsx`:

```tsx
import { useMutation } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { vehiclesApi } from '../api/endpoints';
import type { Vehicle } from '../api/types';
import {
  PLATE_FORMAT_ERROR, VIN_FORMAT_ERROR, isValidVin, looksLikePlate, normalizePlate, normalizeVin,
} from '../lib/validators';
import { telegram } from '../telegram/webapp';
import { Button } from '../ui/Button';
import { Field } from '../ui/Field';
import { NO_ERRORS, toFormErrors, type FormErrors } from './formErrors';

interface Props {
  clientId?: string;
  initialQuery?: string;
  submitLabel?: string;
  onCreated: (vehicle: Vehicle) => void;
}

export function VehicleForm({ clientId, initialQuery = '', submitLabel = 'Добавить автомобиль', onCreated }: Props) {
  const [vin, setVin] = useState(!looksLikePlate(initialQuery) && isValidVin(initialQuery) ? initialQuery : '');
  const [plate, setPlate] = useState(looksLikePlate(initialQuery) ? initialQuery : '');
  const [make, setMake] = useState('');
  const [model, setModel] = useState('');
  const [errors, setErrors] = useState<FormErrors>(NO_ERRORS);
  const save = useMutation({
    mutationFn: async () => {
      const vehicle = await vehiclesApi.create({
        vin: normalizeVin(vin), plate_number: normalizePlate(plate), make: make.trim(), model: model.trim(),
      });
      if (clientId) await vehiclesApi.attachOwner(vehicle.id, clientId);
      return vehicle;
    },
    onSuccess: (vehicle) => {
      telegram.haptic('success');
      onCreated(vehicle);
    },
    onError: (e) => {
      telegram.haptic('error');
      setErrors(toFormErrors(e, ['vin', 'plate_number', 'make', 'model'], 'vin'));
    },
  });

  function submit(e: FormEvent) {
    e.preventDefault();
    const fields: Record<string, string> = {};
    if (!isValidVin(vin)) fields.vin = VIN_FORMAT_ERROR;
    if (!looksLikePlate(plate)) fields.plate_number = PLATE_FORMAT_ERROR;
    if (!make.trim()) fields.make = 'Введите марку';
    if (!model.trim()) fields.model = 'Введите модель';
    if (Object.keys(fields).length) {
      setErrors({ fields, general: '' });
      return;
    }
    setErrors(NO_ERRORS);
    save.mutate();
  }

  return (
    <form className="form" noValidate onSubmit={submit}>
      <Field label="VIN или номер кузова" className="mono" autoCapitalize="characters" value={vin} onChange={(e) => setVin(e.target.value)} error={errors.fields.vin} />
      <Field label="Госномер" autoCapitalize="characters" value={plate} onChange={(e) => setPlate(e.target.value)} error={errors.fields.plate_number} />
      <Field label="Марка" value={make} onChange={(e) => setMake(e.target.value)} error={errors.fields.make} />
      <Field label="Модель" value={model} onChange={(e) => setModel(e.target.value)} error={errors.fields.model} />
      {errors.general && <p className="form-error" role="alert">{errors.general}</p>}
      <Button type="submit" variant="primary" block busy={save.isPending}>{submitLabel}</Button>
    </form>
  );
}
```

(If `create` succeeds but `attachOwner` fails, the error shows as `general`; the vehicle exists and can be found by search — acceptable for this cycle.)

`web/src/forms/entryRoutes.tsx`:

```tsx
import { useNavigate, useSearchParams } from 'react-router-dom';
import { ScreenHeader } from '../ui/ScreenHeader';
import { ClientForm } from './ClientForm';
import { VehicleForm } from './VehicleForm';

export function NewClientRoute() {
  const navigate = useNavigate();
  return (
    <>
      <ScreenHeader title="Новый клиент" back />
      <ClientForm onCreated={(c) => navigate(`/clients/${c.id}`, { replace: true })} />
    </>
  );
}

export function NewVehicleRoute() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  return (
    <>
      <ScreenHeader title="Новый автомобиль" back />
      <VehicleForm clientId={params.get('client_id') ?? undefined} onCreated={(v) => navigate(`/vehicles/${v.id}`, { replace: true })} />
    </>
  );
}
```

`web/src/forms/PaperConsentForm.tsx`:

```tsx
import { useMutation } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { consentApi } from '../api/endpoints';
import { PHONE_FORMAT_ERROR, isValidPhone } from '../lib/validators';
import { telegram } from '../telegram/webapp';
import { Button } from '../ui/Button';
import { Field } from '../ui/Field';
import { ScreenHeader } from '../ui/ScreenHeader';
import { NO_ERRORS, toFormErrors, type FormErrors } from './formErrors';

export function PaperConsentForm() {
  const navigate = useNavigate();
  const [phone, setPhone] = useState('');
  const [fullName, setFullName] = useState('');
  const [errors, setErrors] = useState<FormErrors>(NO_ERRORS);
  const save = useMutation({
    mutationFn: () => consentApi.paper(fullName.trim(), phone.trim()),
    onSuccess: (r) => {
      telegram.haptic('success');
      navigate(`/clients/${r.client_id}`, { replace: true });
    },
    onError: (e) => {
      telegram.haptic('error');
      setErrors(toFormErrors(e, ['phone', 'full_name'], 'phone'));
    },
  });

  function submit(e: FormEvent) {
    e.preventDefault();
    const fields: Record<string, string> = {};
    if (!isValidPhone(phone)) fields.phone = PHONE_FORMAT_ERROR;
    if (!fullName.trim()) fields.full_name = 'Введите ФИО';
    if (Object.keys(fields).length) {
      setErrors({ fields, general: '' });
      return;
    }
    setErrors(NO_ERRORS);
    save.mutate();
  }

  return (
    <>
      <ScreenHeader title="Бумажное согласие" back />
      <p className="hint">Клиент подписал согласие на бумаге — зарегистрируйте его.</p>
      <form className="form" noValidate onSubmit={submit}>
        <Field label="Телефон" type="tel" inputMode="tel" value={phone} onChange={(e) => setPhone(e.target.value)} error={errors.fields.phone} />
        <Field label="ФИО" value={fullName} onChange={(e) => setFullName(e.target.value)} error={errors.fields.full_name} />
        {errors.general && <p className="form-error" role="alert">{errors.general}</p>}
        <Button type="submit" variant="primary" block busy={save.isPending}>Зарегистрировать</Button>
      </form>
    </>
  );
}
```

`web/src/forms/StaffForm.tsx`:

```tsx
import { useMutation } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { usersApi } from '../api/endpoints';
import type { Role } from '../api/types';
import { ROLE_LABELS } from '../lib/labels';
import { telegram } from '../telegram/webapp';
import { Button } from '../ui/Button';
import { Field } from '../ui/Field';
import { ScreenHeader } from '../ui/ScreenHeader';
import { SelectField } from '../ui/SelectField';
import { useToast } from '../ui/Toast';
import { NO_ERRORS, toFormErrors, type FormErrors } from './formErrors';

const ROLE_OPTIONS = (['master', 'mechanic', 'admin'] as Role[]).map((r) => ({ value: r, label: ROLE_LABELS[r] }));

export function StaffForm() {
  const navigate = useNavigate();
  const toast = useToast();
  const [role, setRole] = useState<Role>('master');
  const [fullName, setFullName] = useState('');
  const [telegramId, setTelegramId] = useState('');
  const [errors, setErrors] = useState<FormErrors>(NO_ERRORS);
  const save = useMutation({
    mutationFn: () => usersApi.create({ role, full_name: fullName.trim(), telegram_id: Number(telegramId.trim()) }),
    onSuccess: () => {
      telegram.haptic('success');
      toast.show('Сотрудник добавлен');
      navigate('/more', { replace: true });
    },
    onError: (e) => {
      telegram.haptic('error');
      setErrors(toFormErrors(e, ['role', 'full_name', 'telegram_id'], 'telegram_id'));
    },
  });

  function submit(e: FormEvent) {
    e.preventDefault();
    const fields: Record<string, string> = {};
    if (!fullName.trim()) fields.full_name = 'Введите ФИО';
    if (!/^\d{5,15}$/.test(telegramId.trim())) fields.telegram_id = 'Telegram ID — число (узнать: @userinfobot)';
    if (Object.keys(fields).length) {
      setErrors({ fields, general: '' });
      return;
    }
    setErrors(NO_ERRORS);
    save.mutate();
  }

  return (
    <>
      <ScreenHeader title="Новый сотрудник" back />
      <form className="form" noValidate onSubmit={submit}>
        <SelectField label="Роль" value={role} options={ROLE_OPTIONS} onChange={(e) => setRole(e.target.value as Role)} />
        <Field label="ФИО" value={fullName} onChange={(e) => setFullName(e.target.value)} error={errors.fields.full_name} />
        <Field label="Telegram ID" inputMode="numeric" value={telegramId} onChange={(e) => setTelegramId(e.target.value)} error={errors.fields.telegram_id} />
        {errors.general && <p className="form-error" role="alert">{errors.general}</p>}
        <Button type="submit" variant="primary" block busy={save.isPending}>Добавить сотрудника</Button>
      </form>
    </>
  );
}
```

`web/src/screens/MoreScreen.tsx`:

```tsx
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthProvider';
import { ROLE_LABELS } from '../lib/labels';
import { Button } from '../ui/Button';
import { ScreenHeader } from '../ui/ScreenHeader';

export function MoreScreen() {
  const { user, signOut } = useAuth();
  const navigate = useNavigate();
  return (
    <>
      <ScreenHeader title="Ещё" />
      <div className="stack">
        <div className="card">
          <b>{user!.full_name}</b>
          <span className="hint">{ROLE_LABELS[user!.role]}</span>
        </div>
        <Link className="btn btn-block" to="/clients/new">Новый клиент</Link>
        <Link className="btn btn-block" to="/consent/paper">Бумажное согласие</Link>
        {user!.role === 'admin' && <Link className="btn btn-block" to="/staff/new">Добавить сотрудника</Link>}
        <Button
          variant="ghost"
          block
          onClick={() => {
            signOut();
            navigate('/login', { replace: true });
          }}
        >
          Выйти
        </Button>
      </div>
    </>
  );
}
```

`web/src/routes.tsx` — import `NewClientRoute`, `NewVehicleRoute`, `PaperConsentForm`, `StaffForm`, `MoreScreen`; replace elements: `/clients/new` → `<RoleGate roles={STAFF}><NewClientRoute /></RoleGate>`, `/vehicles/new` → `<RoleGate roles={STAFF}><NewVehicleRoute /></RoleGate>`, `/consent/paper` → `<RoleGate roles={STAFF}><PaperConsentForm /></RoleGate>`, `/staff/new` → `<RoleGate roles={['admin']}><StaffForm /></RoleGate>`, `/more` → `<RoleGate roles={STAFF}><MoreScreen /></RoleGate>`.

- [ ] **Step 4: Run tests**

Run: `cd web && npm test && npm run typecheck`
Expected: all pass. (Task 9's `RoleGate shows no access for mechanic on a master route` still targets `/more` and still passes.)

- [ ] **Step 5: Commit**

```bash
git add web/src
git commit -m "feat(web): client, vehicle, paper consent and staff forms; More screen"
```

---

### Task 17: New visit wizard

**Files:**
- Create: `web/src/forms/NewVisitWizard.tsx`, `web/src/forms/NewVisitWizard.test.tsx`
- Modify: `web/src/routes.tsx` (route `/visits/new`)

**Interfaces:**
- Consumes: `searchApi.search`, `ClientHit` (Task 14), `clientsApi.vehicles`, `vehiclesApi.get/owner`, `usersApi.masters`, `visitsApi.create`, `ClientForm`, `VehicleForm` (Task 16), `ScreenHeader({ onBack })`, `telegram.showBack`, `useGoBack`.
- Produces: route `/visits/new` (`?vehicle_id=` skips client and vehicle steps when the vehicle has an owner).

- [ ] **Step 1: Write failing tests**

`web/src/forms/NewVisitWizard.test.tsx`:

```tsx
import { screen, waitFor } from '@testing-library/react';
import { delay, http, HttpResponse } from 'msw';
import { CLIENT, VEHICLE, makeVisit, mockVisitPage } from '../test/fixtures';
import { USERS, renderApp } from '../test/render';
import { server } from '../test/server';

function mockClientSearch(hits = [{ entity: 'client', id: 'c1', matched_field: 'full_name' }]) {
  server.use(
    http.get('/api/search', () => HttpResponse.json(hits)),
    http.get('/api/clients/c1', () => HttpResponse.json(CLIENT)),
    http.get('/api/clients/c1/vehicles', () => HttpResponse.json([VEHICLE])),
  );
}

function captureCreate(bodies: unknown[], responses: Response[] = []) {
  server.use(http.post('/api/visits', async ({ request }) => {
    bodies.push(await request.json());
    return responses.shift() ?? HttpResponse.json(makeVisit(), { status: 201 });
  }));
}

test('master: client → vehicle → mileage → visit card', async () => {
  mockClientSearch();
  mockVisitPage();
  const bodies: unknown[] = [];
  captureCreate(bodies);
  const { user } = renderApp('/visits/new', { as: 'master' });
  await user.type(await screen.findByLabelText('Телефон или ФИО клиента'), 'Петров');
  await user.click(await screen.findByRole('button', { name: /Петров Иван/ }));
  await user.click(await screen.findByRole('button', { name: /Toyota Camry/ }));
  await user.type(await screen.findByLabelText('Пробег на приёмке, км'), '130000');
  await user.click(screen.getByRole('button', { name: 'Создать заезд' }));
  await waitFor(() =>
    expect(bodies).toEqual([{ client_id: 'c1', vehicle_id: 'veh1', assigned_master_id: 'u-master', mileage_at_intake: 130000, mileage_manually_confirmed: false }]),
  );
  await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/visits/v1'));
});

test('admin picks the master', async () => {
  mockClientSearch();
  mockVisitPage();
  server.use(http.get('/api/users/masters', () => HttpResponse.json([USERS.master])));
  const bodies: unknown[] = [];
  captureCreate(bodies);
  const { user } = renderApp('/visits/new', { as: 'admin' });
  await user.type(await screen.findByLabelText('Телефон или ФИО клиента'), 'Петров');
  await user.click(await screen.findByRole('button', { name: /Петров Иван/ }));
  await user.click(await screen.findByRole('button', { name: /Toyota Camry/ }));
  await user.type(await screen.findByLabelText('Пробег на приёмке, км'), '130000');
  await user.click(screen.getByRole('button', { name: 'Далее' }));
  await user.click(await screen.findByRole('button', { name: 'Орлов Пётр' }));
  await waitFor(() => expect(bodies[0]).toMatchObject({ assigned_master_id: 'u-master' }));
});

test('client not found → create client → create vehicle → mileage', async () => {
  server.use(
    http.get('/api/search', () => HttpResponse.json([])),
    http.post('/api/clients', () => HttpResponse.json(CLIENT, { status: 201 })),
    http.get('/api/clients/c1/vehicles', () => HttpResponse.json([])),
    http.post('/api/vehicles', () => HttpResponse.json(VEHICLE, { status: 201 })),
    http.post('/api/vehicles/veh1/owners', () => HttpResponse.json({ id: 'o1' }, { status: 201 })),
  );
  const { user } = renderApp('/visits/new', { as: 'master' });
  await user.type(await screen.findByLabelText('Телефон или ФИО клиента'), '+7 900 123-45-67');
  expect(await screen.findByText('Клиент не найден')).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: '+ Новый клиент' }));
  expect(screen.getByLabelText('Телефон')).toHaveValue('+7 900 123-45-67');
  await user.type(screen.getByLabelText('ФИО'), 'Петров Иван');
  await user.click(screen.getByRole('button', { name: 'Создать и продолжить' }));
  await user.click(await screen.findByRole('button', { name: '+ Новый автомобиль' }));
  await user.type(screen.getByLabelText('VIN или номер кузова'), 'JTDBR32E720012345');
  await user.type(screen.getByLabelText('Госномер'), 'А123ВС77');
  await user.type(screen.getByLabelText('Марка'), 'Toyota');
  await user.type(screen.getByLabelText('Модель'), 'Camry');
  await user.click(screen.getByRole('button', { name: 'Создать и продолжить' }));
  expect(await screen.findByLabelText('Пробег на приёмке, км')).toBeInTheDocument();
});

test('mileage rollback asks to confirm and resends with the flag', async () => {
  mockClientSearch();
  mockVisitPage();
  const bodies: unknown[] = [];
  captureCreate(bodies, [
    HttpResponse.json({ detail: 'Пробег меньше последнего зафиксированного, требуется mileage_manually_confirmed=true' }, { status: 409 }),
  ]);
  const { user } = renderApp('/visits/new', { as: 'master' });
  await user.type(await screen.findByLabelText('Телефон или ФИО клиента'), 'Петров');
  await user.click(await screen.findByRole('button', { name: /Петров Иван/ }));
  await user.click(await screen.findByRole('button', { name: /Toyota Camry/ }));
  await user.type(await screen.findByLabelText('Пробег на приёмке, км'), '1000');
  await user.click(screen.getByRole('button', { name: 'Создать заезд' }));
  await user.click(await screen.findByRole('button', { name: 'Подтвердить пробег' }));
  await waitFor(() => expect(bodies).toHaveLength(2));
  expect(bodies[1]).toMatchObject({ mileage_at_intake: 1000, mileage_manually_confirmed: true });
});

test('back keeps typed values', async () => {
  mockClientSearch();
  const { user } = renderApp('/visits/new', { as: 'master' });
  await user.type(await screen.findByLabelText('Телефон или ФИО клиента'), 'Петров');
  await user.click(await screen.findByRole('button', { name: /Петров Иван/ }));
  await user.click(await screen.findByRole('button', { name: /Toyota Camry/ }));
  await user.type(await screen.findByLabelText('Пробег на приёмке, км'), '5');
  await user.click(screen.getByRole('button', { name: 'Назад' }));
  await user.click(await screen.findByRole('button', { name: /Toyota Camry/ }));
  expect(await screen.findByLabelText('Пробег на приёмке, км')).toHaveValue('5');
  await user.click(screen.getByRole('button', { name: 'Назад' }));
  await user.click(screen.getByRole('button', { name: 'Назад' }));
  expect(screen.getByLabelText('Телефон или ФИО клиента')).toHaveValue('Петров');
});

test('vehicle_id preset starts at mileage', async () => {
  server.use(
    http.get('/api/vehicles/veh1', () => HttpResponse.json(VEHICLE)),
    http.get('/api/vehicles/veh1/owner', () => HttpResponse.json(CLIENT)),
  );
  renderApp('/visits/new?vehicle_id=veh1', { as: 'master' });
  expect(await screen.findByLabelText('Пробег на приёмке, км')).toBeInTheDocument();
  expect(screen.getByText(/Петров Иван/)).toBeInTheDocument();
  expect(screen.getByText('Последний пробег: 120 500 км')).toBeInTheDocument();
});

test('create visit submits once on double tap', async () => {
  mockClientSearch();
  mockVisitPage();
  const bodies: unknown[] = [];
  server.use(http.post('/api/visits', async ({ request }) => {
    bodies.push(await request.json());
    await delay(50);
    return HttpResponse.json(makeVisit(), { status: 201 });
  }));
  const { user } = renderApp('/visits/new', { as: 'master' });
  await user.type(await screen.findByLabelText('Телефон или ФИО клиента'), 'Петров');
  await user.click(await screen.findByRole('button', { name: /Петров Иван/ }));
  await user.click(await screen.findByRole('button', { name: /Toyota Camry/ }));
  await user.type(await screen.findByLabelText('Пробег на приёмке, км'), '130000');
  await user.dblClick(screen.getByRole('button', { name: 'Создать заезд' }));
  await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/visits/v1'));
  expect(bodies).toHaveLength(1);
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd web && npx vitest run src/forms/NewVisitWizard.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Implement**

`web/src/forms/NewVisitWizard.tsx`:

```tsx
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { ApiError } from '../api/client';
import { clientsApi, searchApi, usersApi, vehiclesApi, visitsApi } from '../api/endpoints';
import type { Client, Vehicle } from '../api/types';
import { useAuth } from '../auth/AuthProvider';
import { formatKm } from '../lib/format';
import { useDebounced } from '../lib/useDebounced';
import { useGoBack } from '../lib/useGoBack';
import { ClientHit } from '../screens/hits';
import { telegram } from '../telegram/webapp';
import { Button } from '../ui/Button';
import { EmptyState } from '../ui/EmptyState';
import { Field } from '../ui/Field';
import { Loadable } from '../ui/Loadable';
import { Plate } from '../ui/Plate';
import { ScreenHeader } from '../ui/ScreenHeader';
import { useToast } from '../ui/Toast';
import { ClientForm } from './ClientForm';
import { VehicleForm } from './VehicleForm';

type Step = 'client' | 'client_new' | 'vehicle' | 'vehicle_new' | 'mileage' | 'master';

const STEP_TITLES: Record<Step, string> = {
  client: 'Шаг 1 · Клиент',
  client_new: 'Шаг 1 · Новый клиент',
  vehicle: 'Шаг 2 · Автомобиль',
  vehicle_new: 'Шаг 2 · Новый автомобиль',
  mileage: 'Шаг 3 · Пробег',
  master: 'Шаг 4 · Мастер',
};

const ROLLBACK_TEXT = 'Пробег меньше последнего зафиксированного. Подтвердите, если он верный, или исправьте.';

export function NewVisitWizard() {
  const { user } = useAuth();
  const isAdmin = user!.role === 'admin';
  const navigate = useNavigate();
  const goBack = useGoBack();
  const toast = useToast();
  const queryClient = useQueryClient();
  const [params] = useSearchParams();
  const presetVehicleId = params.get('vehicle_id');

  const [step, setStep] = useState<Step>('client');
  const [history, setHistory] = useState<Step[]>([]);
  const [clientQuery, setClientQuery] = useState('');
  const [client, setClient] = useState<Client | null>(null);
  const [vehicle, setVehicle] = useState<Vehicle | null>(null);
  const [mileage, setMileage] = useState('');
  const [mileageError, setMileageError] = useState('');
  const [rollback, setRollback] = useState(false);
  const [masterId, setMasterId] = useState<string | null>(null);
  const [ready, setReady] = useState(!presetVehicleId);

  useEffect(() => {
    if (!presetVehicleId) return;
    let cancelled = false;
    Promise.all([vehiclesApi.get(presetVehicleId), vehiclesApi.owner(presetVehicleId)])
      .then(([v, owner]) => {
        if (cancelled) return;
        if (owner) {
          setClient(owner);
          setVehicle(v);
          setStep('mileage');
        }
        setReady(true);
      })
      .catch(() => !cancelled && setReady(true));
    return () => {
      cancelled = true;
    };
  }, [presetVehicleId]);

  function go(next: Step, opts: { resetHistory?: boolean } = {}) {
    setHistory((h) => (opts.resetHistory ? [] : [...h, step]));
    setStep(next);
  }

  function back() {
    if (history.length === 0) {
      const dirty = client !== null || clientQuery.trim() !== '' || mileage !== '';
      if (dirty && !window.confirm('Прервать новый заезд?')) return;
      goBack();
      return;
    }
    setStep(history[history.length - 1]);
    setHistory((h) => h.slice(0, -1));
    setRollback(false);
  }

  const creating = useRef(false);
  const backRef = useRef(back);
  backRef.current = back;
  useEffect(() => telegram.showBack(() => backRef.current()), []);

  const debouncedQuery = useDebounced(clientQuery.trim(), 300);
  const clientSearch = useQuery({
    queryKey: ['search', debouncedQuery],
    queryFn: () => searchApi.search(debouncedQuery),
    enabled: step === 'client' && debouncedQuery.length >= 2,
  });
  const clientVehicles = useQuery({
    queryKey: ['clientVehicles', client?.id],
    queryFn: () => clientsApi.vehicles(client!.id),
    enabled: step === 'vehicle' && client !== null,
  });
  const masters = useQuery({ queryKey: ['masters'], queryFn: usersApi.masters, enabled: step === 'master' });

  const create = useMutation({
    mutationFn: (vars: { confirmed: boolean; masterId: string }) =>
      visitsApi.create({
        client_id: client!.id,
        vehicle_id: vehicle!.id,
        assigned_master_id: vars.masterId,
        mileage_at_intake: Number(mileage.trim()),
        mileage_manually_confirmed: vars.confirmed,
      }),
    onSettled: () => {
      creating.current = false;
    },
    onSuccess: async (visit) => {
      telegram.haptic('success');
      await queryClient.invalidateQueries({ queryKey: ['visits'] });
      navigate(`/visits/${visit.id}`, { replace: true });
    },
    onError: (e) => {
      telegram.haptic('error');
      if (e instanceof ApiError && e.status === 409) {
        setRollback(true);
        if (step === 'master') {
          setHistory((h) => h.slice(0, -1));
          setStep('mileage');
        }
        return;
      }
      toast.show(e.message);
    },
  });

  // Ref lock: a double tap submits twice before React re-renders the button as disabled.
  function startCreate(vars: { confirmed: boolean; masterId: string }) {
    if (creating.current) return;
    creating.current = true;
    create.mutate(vars);
  }

  function submitMileage(e: FormEvent) {
    e.preventDefault();
    if (!/^\d+$/.test(mileage.trim())) {
      setMileageError('Введите число (пробег в км)');
      return;
    }
    setMileageError('');
    setRollback(false);
    if (isAdmin) {
      go('master');
      return;
    }
    startCreate({ confirmed: false, masterId: user!.id });
  }

  function pickMaster(id: string) {
    setMasterId(id);
    startCreate({ confirmed: false, masterId: id });
  }

  function confirmMileage() {
    startCreate({ confirmed: true, masterId: masterId ?? user!.id });
  }

  const clientHits = (clientSearch.data ?? []).filter((h) => h.entity === 'client');

  return (
    <>
      <ScreenHeader title="Новый заезд" back onBack={back} />
      <p className="wizard-step">
        {STEP_TITLES[step]}
        {client && step !== 'client' && step !== 'client_new' ? ` · ${client.full_name}` : ''}
      </p>
      {!ready && <div className="loading">Загрузка…</div>}

      {ready && step === 'client' && (
        <div className="stack">
          <Field label="Телефон или ФИО клиента" value={clientQuery} onChange={(e) => setClientQuery(e.target.value)} autoComplete="off" autoFocus />
          {debouncedQuery.length >= 2 && clientSearch.isSuccess && clientHits.length === 0 && <EmptyState text="Клиент не найден" />}
          {clientHits.map((h) => (
            <ClientHit key={h.id} id={h.id} onPick={(c) => { setClient(c); go('vehicle'); }} />
          ))}
          <Button block onClick={() => go('client_new')}>+ Новый клиент</Button>
        </div>
      )}

      {step === 'client_new' && (
        <ClientForm
          initialQuery={clientQuery.trim()}
          submitLabel="Создать и продолжить"
          onCreated={(c) => {
            setClient(c);
            go('vehicle', { resetHistory: true });
          }}
        />
      )}

      {step === 'vehicle' && (
        <div className="stack">
          <Loadable query={clientVehicles}>
            {(list) =>
              list.length === 0 ? (
                <EmptyState text="У клиента нет машин" />
              ) : (
                <>
                  {list.map((v) => (
                    <button key={v.id} type="button" className="card card-link hit" onClick={() => { setVehicle(v); go('mileage'); }}>
                      <div className="row">
                        <Plate value={v.plate_number} />
                        <span>{v.make} {v.model}</span>
                      </div>
                    </button>
                  ))}
                </>
              )
            }
          </Loadable>
          <Button block onClick={() => go('vehicle_new')}>+ Новый автомобиль</Button>
        </div>
      )}

      {step === 'vehicle_new' && client && (
        <VehicleForm
          clientId={client.id}
          submitLabel="Создать и продолжить"
          onCreated={(v) => {
            setVehicle(v);
            go('mileage', { resetHistory: true });
          }}
        />
      )}

      {ready && step === 'mileage' && vehicle && (
        <form className="form" noValidate onSubmit={submitMileage}>
          <div className="row">
            <Plate value={vehicle.plate_number} />
            <span>{vehicle.make} {vehicle.model}</span>
          </div>
          <p className="hint">Последний пробег: {formatKm(vehicle.mileage_current)}</p>
          <Field label="Пробег на приёмке, км" inputMode="numeric" value={mileage} onChange={(e) => setMileage(e.target.value)} error={mileageError} autoFocus />
          {rollback && (
            <>
              <p className="form-error" role="alert">{ROLLBACK_TEXT}</p>
              <Button variant="secondary" block busy={create.isPending} onClick={confirmMileage}>Подтвердить пробег</Button>
            </>
          )}
          <Button type="submit" variant="primary" block busy={create.isPending}>{isAdmin ? 'Далее' : 'Создать заезд'}</Button>
        </form>
      )}

      {step === 'master' && (
        <div className="stack">
          <Loadable query={masters}>
            {(list) =>
              list.length === 0 ? (
                <EmptyState text="Сначала добавьте мастера в «Ещё → Добавить сотрудника»" />
              ) : (
                <>
                  {list.map((m) => (
                    <Button key={m.id} block busy={create.isPending && create.variables?.masterId === m.id} disabled={create.isPending} onClick={() => pickMaster(m.id)}>
                      {m.full_name}
                    </Button>
                  ))}
                </>
              )
            }
          </Loadable>
        </div>
      )}
    </>
  );
}
```

Extend `ScreenHeader` (`web/src/ui/ScreenHeader.tsx`) with an optional `onBack` used instead of `useGoBack` when given:

```tsx
export function ScreenHeader({ title, back = false, onBack, right }: { title: string; back?: boolean; onBack?: () => void; right?: ReactNode }) {
  const goBack = useGoBack();
  return (
    <header className="screen-header">
      {back && !telegram.isMiniApp() && (
        <button type="button" className="back" aria-label="Назад" onClick={onBack ?? goBack}>‹</button>
      )}
      <h1>{title}</h1>
      {right}
    </header>
  );
}
```

`web/src/lib/roles.ts` — the wizard owns the Telegram BackButton on its route, so the layout must not register a second handler. Change:

```ts
export const ROOT_PATHS = ['/visits', '/visits/new', '/my', '/search', '/more'];
```

`web/src/routes.tsx` — import; replace `/visits/new` element with `<RoleGate roles={STAFF}><NewVisitWizard /></RoleGate>`.

- [ ] **Step 4: Run tests**

Run: `cd web && npm test && npm run typecheck`
Expected: all pass. If `back keeps typed values` fails because the first `Назад` at the vehicle step re-renders the client results before the hit loads, keep the assertion order but add `await screen.findByRole('button', { name: /Toyota Camry/ })` between clicks — the data is cached, so it resolves immediately.

- [ ] **Step 5: Commit**

```bash
git add web/src
git commit -m "feat(web): new visit wizard with create-on-the-fly, mileage confirm and step back"
```

---

### Task 18: Final wiring, docs, live check

**Files:**
- Delete: `web/src/screens/Placeholder.tsx`
- Modify: `web/src/routes.tsx` (remove `Placeholder` import), `README.md` (section «Веб / Mini App»)

**Interfaces:**
- Consumes: everything above.

- [ ] **Step 1: Remove the placeholder**

Run: `grep -n "Placeholder" web/src/routes.tsx`
Expected: only the import line remains. Delete that import and `web/src/screens/Placeholder.tsx`.

Run: `cd web && npm test && npm run typecheck && npm run build`
Expected: all green; `dist/` builds.

- [ ] **Step 2: README section**

Append to `README.md`:

```markdown
## Веб / Telegram Mini App

Фронтенд — `web/` (React + Vite). Тонкий клиент к тому же API, что и бот.

Локальный запуск:

1. В `.env`: `SESSION_SECRET=<случайная строка>`, `DEV_LOGIN=true`.
2. `docker compose up -d --build api` — API на `http://localhost:8000`.
3. `cd web && npm install && npm run dev` — открыть `http://localhost:5173`,
   в DevTools включить режим устройства (ширина 390px). Вход — выбор сотрудника
   (работает только при `DEV_LOGIN=true`).

Тесты: `cd web && npm test`.

Сервисный ключ бота: задать `INTERNAL_API_KEY` в `.env` и пересобрать
`docker compose up -d --build api bot` — после этого API принимает `X-User-Id`
только от бота.

Mini App без домена: `cloudflared tunnel --url http://localhost:5173` даёт
HTTPS-адрес; его ставят кнопке меню бота в BotFather. В Mini App вход
автоматический (Telegram `initData`), `DEV_LOGIN` не нужен.
```

- [ ] **Step 3: Full test run**

Run: `docker compose up -d postgres && uv run pytest -q && (cd web && npm test)`
Expected: backend all pass; frontend all pass.

- [ ] **Step 4: Live check in a phone-size headless browser**

1. Ensure `.env` has `SESSION_SECRET` (any random string) and `DEV_LOGIN=true`; `docker compose up -d --build api`.
2. `curl -s localhost:8000/auth/dev-users | head -c 300` — expect a JSON list of staff (if empty, create an admin via the bot or SQL first).
3. `cd web && npm run dev` (background).
4. In the scratchpad (not the repo): `npm init -y && npm i playwright-core@1.49.1`, then a script that launches `~/.cache/ms-playwright/chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell` with `viewport: { width: 390, height: 844 }`, opens `http://localhost:5173/login`, clicks each role's button in turn, and screenshots `/visits`, a visit card, a work screen, `/search?q=<plate>`, `/my` (mechanic), `/visits/new`.
5. Read the screenshots; check: no horizontal scroll, tab bar visible, plate rendering, amber primary buttons, Russian copy, no clipped text. Fix anything off and re-run.

- [ ] **Step 5: Commit**

```bash
git add -A web/src README.md
git commit -m "docs: web/Mini App run instructions; remove placeholder screen"
```

---

## Self-Review notes (done while writing)

- Spec §2 auth → Tasks 1–2; §2 bot key → Task 4; §3 statuses → Task 3; §4 screens → Tasks 10–14, 16; forms → 15–17; Telegram → Task 9 (`telegram`, BackButton, haptic) and 17 (wizard back); §5 errors → `client.ts`, `Loadable`, `useAction`, `formErrors`; §6 tests → per task; §7 rollout → Task 4 (`.env.example`) and Task 18 (README).
- Deviations from spec are listed at the top (SDK, per-work sums/parts list, PDF in Mini App, computed field scope).
- Leaving the wizard: confirm only on Back at the first step (no router blocker — `BrowserRouter` has no `useBlocker`); switching tabs drops the draft silently. Acceptable for this cycle.
