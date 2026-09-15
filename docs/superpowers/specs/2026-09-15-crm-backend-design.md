# CRM автосервиса — Backend (Этап 1): спецификация

Дата: 2026-09-15
Статус: утверждено к реализации

## Контекст и решённые открытые вопросы

Проект — CRM для автосервиса, поэтапно: Telegram-бот (MVP) → веб/Mini App →
клиентский контур. Этот документ описывает **только backend** (данные, API,
сервисный слой): схему БД, статусную модель, consent-сервис, поиск, генерацию
PDF, уведомления, роли. Бот проектируется отдельным циклом поверх готового API
после утверждения и реализации этого спека.

Решения по открытым вопросам из исходного ТЗ:

- **Согласование доп.работ** — обязательный шаг всегда, без исключений для
  постоянных клиентов.
- **Подпись заказ-наряда на MVP** — без юридической силы: флаг
  `approved_by_client` со статусом "согласовано", проставляется мастером
  после устного согласия клиента. Бумажной/электронной подписи нет.
- **Мультифилиальность** — не реализуется в MVP, но `branch_id` закладывается
  сразу во все ключевые таблицы (дешёвое поле сейчас, дорогая миграция
  потом). UI для филиалов не делаем.
- **1С/бухгалтерия** — вне горизонта Этапов 1–2, интеграционных точек не
  закладываем.
- **Стек** — Python 3.12, FastAPI, PostgreSQL (+ `pg_trgm`), SQLAlchemy,
  WeasyPrint, aiogram 3 (бот — отдельный цикл). Хранение файлов — локальная
  ФС на MVP с интерфейсом, допускающим замену на S3-совместимое хранилище
  без изменения вызывающего кода.

## Архитектура

Модульный монолит. Один FastAPI-процесс, модули изолированы по домену,
взаимодействуют только через сервисный слой друг друга (не через репозитории
напрямую). Деление на отдельные процессы/сервисы — по мере роста, не сейчас.

```
app/
  modules/
    clients/       # CRUD клиента, история владения (VehicleOwnership)
    vehicles/       # CRUD авто, привязка пробега
    visits/         # заезд, work items, статусная FSM
    catalog/        # справочник работ, fuzzy-подбор
    consent/        # consent service: draft/token/confirm, независим от канала
    search/         # конфигурируемый мультиполевой поиск + recent_views
    documents/       # генерация PDF заказ-наряда
    notifications/  # абстракция отправки (Telegram-реализация на MVP)
    users/          # роли, аутентификация, audit_log
  core/
    db.py           # сессия SQLAlchemy, engine
    config.py       # настройки (env)
    models.py       # базовые миксины: SoftDeleteMixin, TimestampMixin
```

Каждый модуль: `router.py` (FastAPI-эндпоинты), `service.py` (бизнес-логика,
единственная точка входа для других модулей и для бота/сайта), `repository.py`
(SQLAlchemy-запросы), `schemas.py` (Pydantic). Прямого доступа к БД в обход
`service.py` нет ни у одного канала (бот, будущий сайт, Mini App) — только
HTTP к router.

## Модель данных

Все таблицы: soft delete через `deleted_at` (nullable timestamp, `NULL` =
активна). Физическое удаление запрещено — нужно для будущей отчётности и
152-ФЗ ("удаление" по запросу клиента = анонимизация ПДн-полей + простановка
`deleted_at`, а не `DELETE FROM`).

```sql
clients (
  id, full_name, phone_normalized, phone_display,
  telegram_id NULL, telegram_username NULL,
  client_type ENUM('individual','legal'),
  legal_details JSONB NULL,           -- реквизиты юрлица
  branch_id,
  registered_at,
  deleted_at NULL
)

vehicles (
  id, vin, plate_number, make, model, modification, year, color,
  mileage_current,                    -- обновляется из последнего visit
  registered_at, deleted_at NULL
)

vehicle_ownership (
  id, vehicle_id FK, client_id FK,
  date_from, date_to NULL,
  show_history_before_ownership BOOLEAN DEFAULT false
)

visits (
  id, branch_id, client_id FK, vehicle_id FK,
  created_at, planned_ready_at,
  mileage_at_intake, mileage_manually_confirmed BOOLEAN,
  status ENUM(...),                   -- см. Статусная модель
  assigned_master_id FK users,
  complaint_text,
  intake_photos JSONB,                -- массив URL
  total_amount NUMERIC,
  discount NUMERIC,
  cancelled_reason NULL,
  deleted_at NULL
)

visit_status_log (                    -- append-only, не редактируется и не чистится
  id, visit_id FK, from_status, to_status,
  changed_by_user_id FK, changed_at, reason NULL
)

work_catalog (
  id, name, category ENUM,
  default_norm_hours,
  created_at, created_by_user_id FK,
  deleted_at NULL
)

visit_work_items (
  id, visit_id FK,
  catalog_item_id FK NULL, free_text_name NULL,   -- одно из двух
  category, norm_hours, hourly_rate,
  status ENUM('not_ready','in_progress','waiting_parts','ready'),
  assigned_mechanic_id FK users,
  comment,
  is_extra_work BOOLEAN,
  approved_by_client BOOLEAN, approved_at NULL,
  approved_via ENUM('crm_status', 'bot', ...),   -- расширяемо под этап 2+
  progress_photos JSONB
)

visit_part_items (
  id, visit_id FK, work_item_id FK,
  name, article_number NULL,
  quantity, unit_price,
  availability_status ENUM('in_stock','ordered','pending')
)

users (
  id, role ENUM('admin','master','mechanic'),
  full_name, telegram_id, phone, branch_id,
  deleted_at NULL
)

consents (
  id, client_id FK NULL, draft_id NULL,   -- одно из двух: до конверсии есть только draft_id
  consent_date, consent_text_version,
  consent_method ENUM('qr_onsite','paper','telegram_bot_start',
                       'email_confirmation','sms_otp'),
  ip_address NULL, telegram_id NULL, verification_ref NULL
)

audit_log (                              -- общий аудит поверх visit_status_log
  id, user_id FK, entity_type, entity_id,
  action, old_value JSONB, new_value JSONB, at
)

recent_views (
  id, user_id FK, entity_type, entity_id, viewed_at
)
```

`branch_id` на MVP всегда = единственному засеянному филиалу; поле есть, UI
управления филиалами нет.

## Статусная модель заезда

```
Принят → Диагностика → Согласование → В работе
  → Ожидание запчастей ⇄ В работе → Готов → Выдан
Отменён — доступен с любого нетерминального статуса, reason обязателен
```

Реализация: словарь `ALLOWED_TRANSITIONS: dict[Status, set[Status]]` внутри
`visits/service.py` — единственное место, где разрешённые переходы
перечислены. Любой переход статуса идёт только через
`VisitService.change_status(visit_id, new_status, user, reason=None)`,
который:
1. проверяет переход по словарю,
2. для перехода в `Готов` — проверяет, что все `visit_work_items.status ==
   'ready'` (иначе `409`),
3. для перехода в `Отменён` — требует непустой `reason`,
4. пишет строку в `visit_status_log`,
5. вызывает `NotificationSender` для статусов `Готов` и
   `Ожидание запчастей`.

Статус отдельной работы (`visit_work_items.status`) меняется независимо,
своим эндпоинтом, доступным механику только для его собственных назначенных
работ.

## Consent service

Единая точка для согласия на ПДн, метод хранится в `consent_method`, схема
таблицы не меняется между этапами — меняется только то, кто и как её
заполняет.

**Этап 1 (`qr_onsite` + `paper`):**
- `POST /consent/draft` — мастер создаёт черновик клиента (ФИО/телефон/авто
  ещё не обязательны), получает `draft_id` + одноразовый `token` (TTL 15
  минут, поле `expires_at`). Возвращает короткую ссылку для QR.
- Отдельная статическая веб-страница (не часть бота, не требует
  аутентификации, живёт за тем же API) по токену читает draft
  (`GET /consent/draft/{token}`), клиент сам на своём устройстве вводит
  ФИО/телефон/авто, ставит галочку согласия.
- `POST /consent/confirm` (по токену) — конвертирует draft → `clients`-запись
  + строку в `consents` с `consent_method='qr_onsite'`, `ip_address` из
  запроса.
- Истёкший токен → `410 Gone`, мастер создаёт новый draft.
- Фоллбэк `paper`: мастер сам создаёт клиента и запись `consents` с
  `consent_method='paper'`, без токена, `verification_ref` — опционально
  номер бумажного бланка.

Этапы 2–4 (`telegram_bot_start`, `email_confirmation`, `sms_otp`) добавляют
новые значения `consent_method` и новые способы создания той же записи —
схема `consents` не меняется, `sms_otp` закладывается только как значение
enum, интеграция с SMS-шлюзом — в бэклог.

## Поиск

Конфигурируемый список полей, добавление критерия = новая запись в списке,
без изменения ядра поискового модуля:

```python
SEARCH_FIELDS = [
    SearchField(entity="client", field="phone_normalized", match_type="normalized"),
    SearchField(entity="client", field="full_name", match_type="fuzzy"),
    SearchField(entity="vehicle", field="vin", match_type="exact_or_suffix"),
    SearchField(entity="vehicle", field="plate_number", match_type="normalized"),
    SearchField(entity="vehicle", field="make", match_type="fuzzy"),
    SearchField(entity="vehicle", field="model", match_type="fuzzy"),
]
```

Типы сравнения:
- `exact` — прямое совпадение.
- `exact_or_suffix` — точное совпадение ИЛИ (если введено ≤4 символов) `LIKE
  '%<suffix>'` по VIN.
- `normalized` — сравнение после нормализации (для телефона: только цифры,
  `8`/`+7` приводятся к единому префиксу; для гос.номера: верхний регистр,
  без пробелов/дефисов).
- `fuzzy` — `pg_trgm` `similarity()`, порог по умолчанию 0.3, сортировка по
  убыванию похожести.

Ядро (`search/service.py`) итерирует `SEARCH_FIELDS`, для каждого поля
применяет соответствующую стратегию сравнения (класс-стратегия на
`match_type`), объединяет результаты по `entity`, возвращает список карточек
клиент+авто с указанием, по какому полю сработало совпадение.

`recent_views` — при открытии карточки клиента/авто пишется строка; при
входе в поиск без запроса отдаются последние N (по умолчанию 10) записей
текущего `user_id`.

## Справочник работ (fuzzy-дедупликация)

При вводе свободного текста работы:
`GET /catalog/suggest?text=...` возвращает top-3 совпадения по
`similarity(name, :text) > 0.3` из `work_catalog`, отсортированные по
убыванию похожести. Мастер выбирает существующую позицию или создаёт новую
(`POST /catalog`) — тогда `visit_work_items.catalog_item_id` заполняется,
`free_text_name` остаётся `NULL`. Если позиция не создаётся —
`free_text_name` хранит введённый текст, `catalog_item_id = NULL`.

## Генерация PDF

`documents/service.py`: `generate_visit_document(visit_id) -> url`.
Рендерит HTML-шаблон (Jinja2) с данными визита/клиента/авто/работ/запчастей
через WeasyPrint, сохраняет файл через абстракцию `FileStorage`
(`save(bytes, path) -> url`), на MVP — реализация поверх локальной ФС;
замена на S3-совместимое хранилище — только замена реализации `FileStorage`,
без изменения вызывающего кода. URL кладётся в `visits.document_url`.
Отправка документа в Telegram — через `notifications`-модуль, не
реализуется на MVP, но интерфейс `NotificationSender.send_document(...)`
существует.

## Уведомления

`notifications/service.py`: интерфейс `NotificationSender` с методами
`send_status_changed(visit, old_status, new_status)`,
`send_extra_work_approval_request(work_item)`, `send_document(visit, url)`.
На MVP единственная реализация — отправка ботом внутренним пользователям
(мастеру/админу) при смене статуса на `Готов` / `Ожидание запчастей`.
Клиентские уведомления — заглушка (клиентского контура ещё нет), но вызовы
из `visits/service.py` уже происходят в нужных точках — на Этапе 3
реализация подменяется без изменения вызывающего кода.

## Роли и права

| Действие | admin | master | mechanic |
|---|---|---|---|
| CRUD клиентов/авто | ✅ | ✅ | ❌ |
| Создание/ведение заезда | ✅ | ✅ | ❌ |
| Смена статуса заезда | ✅ | ✅ | ❌ |
| Смена статуса своей work_item | ✅ | ✅ | ✅ (только назначенные) |
| Просмотр финансов (суммы, цены) | ✅ | ✅ | ❌ |
| Редактирование справочника работ | ✅ | ✅ | ❌ |
| Управление пользователями | ✅ | ❌ | ❌ |

Проверка прав — декоратор/зависимость FastAPI на уровне router, бизнес-логика
в service.py не знает о ролях напрямую (принимает уже авторизованного
`user`).

## Аудит

`audit_log` — общий журнал (кто/когда/что изменил) для всех сущностей кроме
статусов заезда, которые логируются отдельно в `visit_status_log` (более
специфичная структура: конкретно from/to статус). Оба журнала append-only,
не редактируются, не чистятся — основа для будущей отчётности без миграций
задним числом (загрузка мастеров, средний чек, повторные обращения, конверсия
согласований и т.д. считаются агрегацией по этим двум таблицам плюс
`visits`/`visit_work_items`).

## Нефункциональные требования

- 152-ФЗ: `consents` — обязательная запись перед созданием полноценной
  карточки клиента (кроме внутреннего draft-состояния). Запрос на удаление
  данных — анонимизация ПДн-полей (ФИО→"Удалено", телефон→NULL и т.д.) +
  `deleted_at`, без физического `DELETE`.
- Soft delete везде, без исключений.
- Один и тот же API обслуживает бота (Этап 1), сайт/Mini App (Этап 2+),
  клиентский контур (Этап 3) — бизнес-логика только в `service.py`, роутеры
  и будущие клиенты — тонкие.

## Вне рамок этого документа (следующий цикл)

- Telegram-бот (aiogram 3) — тонкий клиент поверх этого API, отдельный
  спек+план после реализации backend.
- Веб/Mini App, клиентский контур — Этапы 2–3.
- Отчётность/графики — не реализуется, но данные уже пригодны (см. Аудит).
- SMS OTP — бэклог, конфигурируемый метод, интеграция с SMS-шлюзом вне
  этого документа.
