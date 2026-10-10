# CRM автосервиса — веб / Telegram Mini App (вариант B): спецификация

Дата: 2026-10-10
Статус: на ревью
Дополняет: `docs/superpowers/specs/2026-09-15-crm-backend-design.md` (Этап 2 «веб/Mini App»)
Ветка: `web-miniapp` (worktree), от `main` 7d3ecc5

## Контекст

Бэкенд (FastAPI) и Telegram-бот (тонкий клиент поверх HTTP API) готовы и в `main`.
Следующий этап по плану — веб/Mini App. Визуальный стиль выбран по макетам
(`https://claude.ai/artifact/2TTxP7DywERqyBJt5Fnktf`): **вариант B** — свой фирменный
стиль автосервиса, графит + сигнальный янтарь, госномер в виде таблички.

Сверено с кодом на `main` 7d3ecc5:

1. **Аутентификация небезопасна для внешнего канала.** `app/modules/users/auth.py:
   get_current_user` доверяет заголовку `X-User-Id` без проверки. Внутри Docker рядом
   с ботом это терпимо, в браузере — нет: любой подставит чужой uuid. Кроме того,
   `GET /users/by-telegram/{telegram_id}` открыт без авторизации и раскрывает uuid
   сотрудников.
2. **Графы переходов статусов продублированы в боте.** `bot/handlers/visits.py:
   _NEXT_STATUS_BY_CURRENT` копирует `app/modules/visits/fsm.py: ALLOWED_TRANSITIONS`;
   `bot/work_item_status.py: NEXT_WORK_ITEM_STATUSES` — UI-подсказка, на бэкенде
   графа для работ нет (PATCH принимает любой статус). Веб стал бы третьей копией.
3. **Домена нет.** Пользователь тестирует на компьютере; Mini App требует HTTPS-URL,
   поэтому в этом цикле основной режим — браузер в мобильной раскладке.

## Решения (согласованы)

- Один фронтенд на два канала: Telegram Mini App и сайт в браузере. В этом цикле —
  только мобильная раскладка (360–430px); на широком экране — колонка 430px по центру.
- Объём первой версии — паритет с ботом (все его экраны и действия). Отчёты — следующий цикл.
- Стек: React 18 + TypeScript + Vite, TanStack Query, React Router, `@telegram-apps/sdk-react`;
  CSS с переменными (без Tailwind); тесты Vitest + Testing Library + MSW.
- Фронтенд — тонкий клиент: только HTTP к API, бизнес-логики нет.
- Вход: Telegram `initData` → токен сессии; для разработки — выбор сотрудника под флагом
  `DEV_LOGIN`. `X-User-Id` остаётся только для бота и только с сервисным ключом.

## 1. Архитектура

```
web/                         новый фронтенд
  index.html
  vite.config.ts             proxy /api → http://localhost:8000 (rewrite: убрать /api)
  src/
    main.tsx, App.tsx        роутер, QueryClientProvider, AuthProvider
    api/
      client.ts              fetch-обёртка: базовый /api, Bearer-токен, разбор ошибок
      types.ts               типы ответов API (вручную по схемам Pydantic)
      *.ts                   функции по доменам: visits, workItems, clients, vehicles, search, users, catalog, consent, documents, auth
    auth/                    AuthProvider, хранение токена, экран входа
    telegram/                обёртка над SDK: isMiniApp, backButton, haptic, expand, initData
    screens/                 по файлу на экран (раздел 3)
    forms/                   формы и мастер нового заезда
    ui/                      Card, Plate, StatusTag, Button, Field, TabBar, Toast, EmptyState, Sheet
    lib/validators.ts        телефон / VIN / госномер — те же правила, что bot/validators.py
    lib/labels.ts            русские названия и иконки статусов
    theme.css                токены варианта B
  tests/ или src/**/*.test.tsx
app/modules/auth/            новый модуль бэкенда (раздел 2)
```

Запуск для проверки:
- `docker compose up -d` — API на `:8000`, как сейчас.
- `cd web && npm install && npm run dev` — `http://localhost:5173`, Vite проксирует
  `/api/*` на API (CORS не нужен).
- Проверка в браузере в режиме устройства (ширина 390px).

Отдача собранной статики в проде, nginx/compose-сервис для `web` — вне рамок (нет домена).

## 2. Бэкенд: аутентификация

Новый модуль `app/modules/auth/` (`router.py`, `service.py`, `schemas.py`, `telegram.py`).
Новая зависимость: `pyjwt`.

### Настройки (`app/core/config.py`)

| Поле | Env | По умолчанию | Назначение |
|---|---|---|---|
| `session_secret` | `SESSION_SECRET` | `None` | ключ подписи токена сессии (HS256). Без него `/auth/telegram` и `/auth/dev-login` отвечают 503 |
| `session_ttl_hours` | `SESSION_TTL_HOURS` | `12` | срок жизни токена |
| `internal_api_key` | `INTERNAL_API_KEY` | `None` | сервисный ключ бота |
| `dev_login` | `DEV_LOGIN` | `False` | включает dev-вход |
| `telegram_init_data_max_age_s` | — | `86400` | максимальный возраст `auth_date` |

### Эндпоинты

- `POST /auth/telegram` — тело `{"init_data": "<строка Telegram.WebApp.initData>"}`.
  Проверка по документации Telegram: `secret = HMAC_SHA256(key="WebAppData", msg=bot_token)`,
  `hash == hex(HMAC_SHA256(secret, data_check_string))`, где `data_check_string` — пары
  `key=value` без `hash`, отсортированные по ключу, через `\n`; сравнение
  `hmac.compare_digest`. `auth_date` не старше `telegram_init_data_max_age_s`.
  Из поля `user` (JSON) берётся `id` → `UserService.get_by_telegram_id`.
  Ответ `200 {"token": "...", "user": UserOut}`.
  Ошибки: подпись неверна / данные просрочены / нет `user` → 401;
  сотрудник не найден или удалён → 403 «Вы не сотрудник сервиса»;
  нет `TELEGRAM_BOT_TOKEN` или `SESSION_SECRET` → 503.
- `GET /auth/dev-users` — список активных сотрудников `[UserOut]`. Только при
  `DEV_LOGIN=true`, иначе 404.
- `POST /auth/dev-login` — тело `{"user_id": uuid}` → `{"token", "user"}`. Только при
  `DEV_LOGIN=true`, иначе 404; неизвестный/удалённый → 404.
- `GET /auth/me` — текущий сотрудник `UserOut` (фронтенд проверяет токен при старте).

Токен — JWT HS256: `{"sub": "<user uuid>", "exp": now + ttl, "iat": now}`.

### `get_current_user` (`app/modules/users/auth.py`)

Порядок:
1. `Authorization: Bearer <jwt>` → проверка подписи и `exp` → `User` по `sub`.
   Ошибка декодирования или просрочка → 401.
2. Иначе `X-User-Id`:
   - если `internal_api_key` задан — требуется `X-Service-Key`, равный ему
     (`hmac.compare_digest`), иначе 401;
   - если не задан — принимается как сейчас (тесты, локальная разработка); при старте
     приложения — `logger.warning` «INTERNAL_API_KEY не задан: X-User-Id принимается без ключа».
3. Иначе 401.
Удалённый/неизвестный пользователь → 401 (как сейчас). `require_role` не меняется.

`GET /users/by-telegram/{telegram_id}` — тем же правилом сервисного ключа: при заданном
`internal_api_key` требует `X-Service-Key`, иначе 401. Вынести в зависимость
`require_service_key` (`app/modules/users/auth.py`).

### Бот

`bot/config.py` — поле `internal_api_key` (`INTERNAL_API_KEY`, опционально).
`bot/api_client.py: _headers` и запрос `by-telegram` добавляют `X-Service-Key`, если ключ задан.
`docker-compose.yml` ничего не меняет (`env_file: .env` общий для api и bot).
`.env.example` — `SESSION_SECRET=`, `INTERNAL_API_KEY=`, `DEV_LOGIN=true` с комментариями.

## 3. Бэкенд: допустимые переходы статусов

- `VisitOut` (`GET /visits/{id}`, `PATCH /visits/{id}/status`) получает
  `allowed_next_statuses: list[VisitStatus]` — из `ALLOWED_TRANSITIONS[visit.status]`,
  в порядке объявления enum.
- Для работ на бэкенде появляется `app/modules/visits/work_item_flow.py:
  WORK_ITEM_NEXT_STATUSES` — перенос `bot/work_item_status.py: NEXT_WORK_ITEM_STATUSES`.
  Это **подсказка UI**, PATCH статуса работы по-прежнему принимает любой статус (поведение
  не меняется). `WorkItemOut` и `WorkItemMineOut` получают `allowed_next_statuses`.
- Бот не меняется (перевод на поле — отдельная задача, вне рамок).

### `GET /visits/{id}/lines` — цены для карточки заезда

`WorkItemOut` цен не содержит и отдаётся механикам; запросить список запчастей заезда
нельзя. Новый эндпоинт только для ADMIN/MASTER (механик → 403, неизвестный заезд → 404)
отдаёт работы с ценами и запчасти, сгруппированные по работе:
`{works: [{id, name, status, assigned_mechanic_name, approved_by_client, norm_hours,
hourly_rate, amount, parts: [{id, work_item_id, name, quantity, unit_price, amount}]}],
works_total, parts_total, discount, total}`. `total` считается по той же формуле, что
`VisitService.recalculate_total`, и совпадает с `Visit.total_amount`.

## 4. Фронтенд: экраны и навигация

### Навигация

React Router, у каждого экрана свой URL. Снизу — таб-бар по роли:
- MASTER/ADMIN: `Заезды` (`/visits`), `Поиск` (`/search`), `+ Заезд` (`/visits/new`), `Ещё` (`/more`);
- MECHANIC: `Мои работы` (`/my`), `Поиск` (`/search`).

Стартовый экран после входа: `/visits` (мастер/админ), `/my` (механик).
Неизвестный URL → стартовый экран. Маршрут, недоступный роли → экран «Нет доступа».

### Экраны

| Экран | URL | Роли | API | Содержимое и действия |
|---|---|---|---|---|
| Вход | `/login` | все | `/auth/*` | Mini App: автоматически `POST /auth/telegram`, при 403 — «Вы не сотрудник сервиса». Браузер: при `DEV_LOGIN` — список сотрудников (ФИО, роль), иначе «Откройте приложение из Telegram» |
| Заезды в работе | `/visits` | M, A | `GET /visits?active=true` | карточки: табличка госномера, марка/модель, клиент, статус-тег, мастер. Фильтры-чипы на клиенте: Все · Мои (master = я) · Ждут запчасти · Готовы. Пусто → «Нет заездов в работе» + `+ Новый заезд` |
| Карточка заезда | `/visits/:id` | M, A | `GET /visits/{id}`, `GET /visits/{id}/lines` | шапка (госномер, авто, клиент → `/clients/:id`, пробег, мастер), итого, работы (иконка статуса, название, исполнитель, сумма → экран работы), под каждой работой её запчасти с суммой; строка «Работы … · запчасти …». Действия: `+ Работа` (форма), `Статус` (лист с `allowed_next_statuses`; «Отменён» → диалог причины), `PDF` |
| Работа | `/visits/:id/works/:itemId` | M, A, MECH | мастер/админ: из `GET /visits/{id}/work-items`; механик: из `GET /work-items/mine` | название, статус, исполнитель, согласовано/нет, запчасти работы. Мастер/админ: `Согласовано клиентом` (если нет), кнопки `allowed_next_statuses`, `+ Запчасть`, `Сменить исполнителя` (лист: механики + «Без исполнителя»). Механик: только кнопки статуса |
| Мои работы | `/my` | MECH | `GET /work-items/mine` | карточки: иконка статуса, название, госномер, марка → экран работы. Пусто → «Нет назначенных работ» |
| Поиск | `/search?q=` | все | `GET /search`, `GET /search/recent` | поле сверху, запрос с задержкой 300 мс от 2 символов; пусто — недавние. Результаты: клиенты и машины → карточки. Подсказка по роли как в боте |
| Клиент | `/clients/:id` | M, A | `GET /clients/{id}`, `/clients/{id}/vehicles`, `GET /visits?client_id=` | ФИО, телефон (ссылка `tel:`), машины → `/vehicles/:id`, история заездов → `/visits/:id`. `+ Автомобиль` (форма) |
| Машина | `/vehicles/:id` | все (механик — как в боте) | `GET /vehicles/{id}`, `/owner`, `/work-history`, `GET /visits?vehicle_id=` | авто, VIN, госномер, пробег, владелец → клиент, история работ. Мастер/админ: ещё заезды (`GET /visits` механику закрыт) и `+ Новый заезд` (мастер с подставленной машиной) |
| Ещё | `/more` | M, A | — | `Бумажное согласие` (форма), `Добавить сотрудника` (только A, форма), имя и роль, `Выйти` |

`GET /visits` принимает `active`, `client_id`, `vehicle_id`; формат ответов — схемы
Pydantic текущих роутеров, типы в `web/src/api/types.ts` пишутся по ним.

### Формы

Одна форма вместо пошагового ввода бота; валидация на клиенте (`lib/validators.ts`,
правила `bot/validators.py`), окончательная — API.

| Форма | Поля | API | После успеха |
|---|---|---|---|
| Добавить работу | название (подсказки `GET /catalog/suggest` по вводу, выбор подставляет нормо-часы и ставку), категория (если своё название), нормо-часы, ставка, исполнитель (механики + «Без исполнителя») | `POST /visits/{id}/work-items` | назад в карточку заезда |
| Добавить запчасть | название, количество, цена | `POST /visits/{id}/part-items` | назад в экран работы / заезда |
| Новый клиент | телефон, ФИО | `POST /clients` | в карточку клиента или следующий шаг мастера |
| Новая машина | VIN/номер кузова, госномер, марка и модель | `POST /vehicles` (+ `POST /vehicles/{id}/owners` если открыта из клиента) | в карточку машины или следующий шаг мастера |
| Бумажное согласие | телефон, ФИО | `POST /consent/paper` | в карточку клиента |
| Новый сотрудник | роль, ФИО, Telegram ID | `POST /users` | «Сотрудник добавлен», назад в `Ещё` |
| Отмена заезда | причина | `PATCH /visits/{id}/status` | карточка заезда |

### Мастер «Новый заезд» (`/visits/new`)

Шаги (ветвятся, как в боте): клиент (поиск по телефону/ФИО) → не найден: форма
«Новый клиент» с подставленным запросом → машина клиента (список его машин или поиск
по госномеру/VIN) → не найдена: форма «Новая машина» → пробег (число; если меньше
последнего известного — подтверждение) → мастер (только ADMIN, `GET /users/masters`) →
`POST /visits` → `replace` на `/visits/:id`.
Вход с карточки машины (`?vehicle_id=`) пропускает шаги клиента и машины.
Состояние мастера — в памяти компонента; `Назад` (в шапке и Telegram BackButton) ведёт
на предыдущий шаг без потери введённого; после создания сущности (клиент, машина) шаг
назад её не создаёт повторно. Уход с мастера — подтверждение «Прервать новый заезд?».

### Стиль (вариант B)

`theme.css`: фон `#1d2024`, карточка `#272b31`, текст `#f1efe9`, подсказка `#9aa0a8`,
янтарь `#f2b632` (текст на нём `#1d2024`), линия `#353a42`; статус-теги: ремонт — янтарь,
запчасти `#8fb6ff`, согласование `#ff8e84`, готов `#7fd99a`, прочие — нейтральный.
Шрифты: Golos Text (текст), JetBrains Mono (госномер, VIN, суммы). Госномер — компонент
`Plate` (белая табличка, регион отдельно). Тема одна, от темы Telegram не зависит;
в Mini App `setHeaderColor`/`setBackgroundColor` = `#1d2024`. Цель нажатия ≥ 44px.

### Telegram

`src/telegram/`: если открыто в Telegram (`initData` не пустой) — `ready()`, `expand()`,
BackButton показывается на всех экранах кроме стартового и ведёт `navigate(-1)`,
`HapticFeedback.notificationOccurred('success'|'error')` после отправки форм.
В браузере все вызовы — no-op.

### Данные

TanStack Query: ключи по ресурсам (`['visit', id]`, `['visits', filter]`, …); после мутации —
инвалидация затронутых ключей. `staleTime` 15 с; повтор при ошибке — 1 раз, кроме 4xx.

## 5. Ошибки

| Ситуация | Поведение |
|---|---|
| сеть / 5xx | тост «Нет связи с сервером» + `Повторить`; данные экрана остаются |
| 401 | токен удаляется, переход на `/login` (в Mini App вход повторяется автоматически) |
| 403 | экран «Нет доступа к этому разделу» |
| 404 на карточке | «Не найдено» + `К списку` |
| 409 / 422 в форме | текст у поля (по `loc` из 422 или известному коду 409: телефон / VIN заняты), ввод сохраняется |
| двойное нажатие | кнопка отправки `disabled` до завершения запроса |
| PDF | `POST /visits/{id}/document` → открыть `GET /documents/{doc}/file` (в Mini App — `openLink`) |

Токен хранится в `sessionStorage` (ключ `crm.token`); `fetch` к `localStorage`/`sessionStorage`
обёрнут в try/catch.

## 6. Тестирование

Бэкенд (pytest, существующая инфраструктура):
- `initData`: верная подпись → токен; изменённое поле → 401; просроченный `auth_date` → 401;
  неизвестный `telegram_id` → 403; нет секрета/токена бота → 503.
- JWT: верный → доступ; просроченный / испорченный / чужой ключ → 401.
- `dev-users`/`dev-login` при `DEV_LOGIN=false` → 404; при `true` → токен.
- `X-User-Id` при заданном `INTERNAL_API_KEY`: без ключа / с неверным → 401, с верным → 200;
  без заданного ключа → 200 (обратная совместимость).
- `/users/by-telegram` — то же правило ключа.
- `allowed_next_statuses` у заезда совпадает с `ALLOWED_TRANSITIONS`; у работы — с `WORK_ITEM_NEXT_STATUSES`.
- Бот: `api_client` шлёт `X-Service-Key`, если задан.
- Все существующие тесты (410) зелёные.

Фронтенд (Vitest + Testing Library + MSW):
- `api/client`: Bearer в заголовке; 401 → сброс токена и событие выхода; разбор 409/422.
- `lib/validators`: те же кейсы, что `tests/bot/test_validators*.py`.
- Вход: dev-список → токен → стартовый экран по роли; Mini App-ветка с замоканным `initData`.
- Экраны: рендер по ролям; механик не видит кнопок мастера; пустые состояния.
- Формы: ошибки 409/422 у поля; блокировка двойной отправки.
- Мастер нового заезда: ветки «найден» и «не найден → создан»; `Назад` сохраняет ввод;
  вход с `vehicle_id`.

Ручная проверка: стек в Docker + `npm run dev`; проход по ролям ADMIN/MASTER/MECHANIC в
headless-браузере на 390px со скриншотами; затем проверка пользователем.

## 7. Выкатка

1. Ветка `web-miniapp` в worktree, слияние в `main` после ревью.
2. `.env`: добавить `SESSION_SECRET` (случайная строка), `DEV_LOGIN=true`.
3. `INTERNAL_API_KEY` — включать так: задать в `.env` → `docker compose up -d --build api bot`
   (оба читают один `.env`, перезапускаются вместе). Без ключа всё работает как раньше.
4. Позже, без домена, подключение к Telegram: `cloudflared tunnel --url http://localhost:5173`
   → HTTPS-адрес → кнопка меню бота через BotFather. Не входит в этот цикл.

## Вне рамок

Отчёты и графики; широкая раскладка для ПК; отдача собранного фронтенда в проде и
compose-сервис `web`; перевод бота на `allowed_next_statuses`; клиентский контур
(онлайн-запись, статус машины для клиента); принудительный граф статусов работ на бэкенде.
