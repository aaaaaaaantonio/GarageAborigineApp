# CRM Telegram-бот — устранение пробелов исходного плана: спецификация

Дата: 2026-09-23
Статус: утверждено к реализации
Дополняет: `docs/superpowers/specs/2026-09-19-crm-bot-design.md`, `docs/superpowers/plans/2026-09-19-crm-bot-plan.md`

## Контекст

При реализации плана `2026-09-19-crm-bot-plan.md` (Задачи 1–10 завершены,
82/82 теста зелёные) обнаружены три места, где буквальные Steps задач
реализовали меньше, чем обещали их же Interfaces-абзацы и исходная
спецификация `2026-09-19-crm-bot-design.md`:

1. **Задача 10** (визард заезда): кнопка "Новый заезд" и состояния
   `NewVisitStates.choosing_client/choosing_vehicle/choosing_master`
   объявлены с Задачи 4, но ни одна задача плана не реализует обработчик
   для них — визард недостижим (уже задокументировано в
   `.superpowers/sdd/2026-09-19-crm-bot-plan/progress.md`, преамбула к
   Задаче 10).
2. **Задача 11** (работы): `WorkItemCreate.category` — обязательное
   поле бэкенда, но ни одна задача не собирает его от пользователя бота;
   собственный Step 4 задачи реализует только `receive_work_name`,
   оставляя состояния `choosing_suggestion`/`waiting_for_hours_and_rate`
   без обработчиков.
3. **Задача 17** (механик): "Мои работы" обещает "inline-кнопку смены
   статуса на каждую позицию", но Step 4 рисует голый текстовый список
   без кнопок; карточка заезда (Задача 10) не показывает кнопку
   "Согласовать работу", хотя она есть в исходной спеке.

Расследование показало: это **пробелы монтажа**, а не отсутствие
дизайна — почти все нужные строительные блоки уже существуют:

- Исходная спека прямо говорит: мастер заезда — "себя по умолчанию"
  (`2026-09-19-crm-bot-design.md:125`) → отдельный эндпоинт/UI выбора
  мастера не нужен, берётся `user["id"]` из `AuthMiddleware`.
- `GET /catalog/suggest` уже возвращает `category` и
  `default_norm_hours` в каждой подсказке (`WorkCatalogOut`) — при
  выборе из справочника категория не спрашивается повторно.
- `GET /clients/{id}` и `GET /vehicles/{id}` уже существуют.
- `ApiClient.search()` добавлен в Задаче 8, но нигде не используется.

Единственный настоящий недостающий кусок backend — списочный эндпоинт
работ по заезду (см. ниже), без которого карточку заезда нечем
наполнять для кнопки "Согласовать работу".

## Доработка backend

### `GET /visits/{visit_id}/work-items` — список работ заезда

Добавить в `app/modules/visits/work_items_router.py`:

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

`WorkItemService.list_for_visit(visit_id)`: проверить, что заезд
существует (иначе `VisitNotFound`), затем
`select(VisitWorkItem).where(VisitWorkItem.visit_id == visit_id)`.

`WorkItemOut` (в `work_items_schemas.py`) расширить полями, нужными для
отображения карточки — `free_text_name: str | None`,
`catalog_item_id: uuid.UUID | None` (аддитивное изменение, ничего не
ломает у существующих потребителей — Задачи 11/17 уже читают только
`id`/`status`/`approved_by_client`).

## Доработка bot

### A. Визард "Новый заезд" (`bot/handlers/visits.py`)

Новые состояния в `NewVisitStates` (заменяют неиспользуемое
`choosing_master`, которое убирается — мастер больше не выбирается
отдельным шагом):

```python
class NewVisitStates(StatesGroup):
    waiting_for_client_query = State()
    choosing_client = State()
    waiting_for_vehicle_query = State()
    choosing_vehicle = State()
    waiting_for_mileage = State()  # уже существует
```

Поток:

1. `F.text == "Новый заезд"` → `state.set_state(waiting_for_client_query)`,
   `"Введите телефон или ФИО клиента:"`.
2. `waiting_for_client_query` → `api.search(text)`, отфильтровать
   `entity == "client"`. Для каждого совпадения — `api.get_client(id)`
   (новый метод `ApiClient`) за именем.
   - 0 совпадений: сразу переключиться в существующий визард создания
     клиента — `state.set_state(NewClientStates.waiting_for_phone)`,
     `state.update_data(return_flow="new_visit")`, тот же промпт, что и
     у `Command("new_client")`.
   - 1–5 совпадений: inline-кнопки `client_pick:{id}` с именем,
     `state.set_state(choosing_client)`.
   - Кнопки не более 5 — если найдено больше, показываются первые 5
     (тот же порядок, что вернул `/search`).
3. `choosing_client` callback → `state.update_data(client_id=id)`,
   переход к шагу 4 (авто), как и в ветке создания ниже.
4. Аналогично для авто: `waiting_for_vehicle_query` →
   `"Введите VIN или гос. номер авто:"` → `api.search(text)`,
   `entity == "vehicle"`, `api.get_vehicle(id)` (новый метод), 0 →
   `NewVehicleStates.waiting_for_vin` с `return_flow="new_visit"`,
   1–5 → кнопки `vehicle_pick:{id}`.
5. `choosing_vehicle` callback → `state.update_data(vehicle_id=id)`,
   `state.set_state(waiting_for_mileage)`, `"Введите пробег на приёмке:"`.
6. `receive_mileage` (существует с Задачи 10) — убрать чтение
   `data["master_id"]`, использовать инжектируемый `user: dict`
   (уже кладётся `AuthMiddleware` в `data["user"]`) как
   `assigned_master_id=user["id"]`.

**Композиция с визардами создания (Задачи 8/9):** `clients.py` и
`vehicles.py` дописываются так, чтобы в конце своего последнего шага
(`receive_full_name`, `receive_make_model`) проверять
`data.get("return_flow")`:
- отсутствует → старое поведение (создать, очистить состояние,
  сообщить об успехе) — обратная совместимость со standalone
  `/new_client`/`/new_vehicle` не нарушается.
- `"new_visit"` → после создания сущности не очищать всё состояние
  сообщением "клиент создан", а сохранить `client_id`/`vehicle_id` в
  данных и продолжить: после клиента — перейти к шагу авто (см. пункт
  4 выше); после авто — перейти к `waiting_for_mileage`.

### B. Завершение визарда работ (`bot/handlers/work_items.py`)

Новое состояние в `AddWorkItemStates`:

```python
class AddWorkItemStates(StatesGroup):
    waiting_for_name = State()          # уже есть
    choosing_suggestion = State()       # уже есть
    choosing_category = State()         # новое — только для "своя формулировка"
    waiting_for_hours_and_rate = State()  # уже есть
```

1. `receive_work_name` (существует) — дополнительно сохранить
   подсказки в данные: `state.update_data(..., suggestions={item["id"]: item for item in suggestions})`.
2. `catalog_pick:{id}` callback, `id != "none"` →
   `state.update_data(catalog_item_id=id, category=sugg["category"], norm_hours=sugg["default_norm_hours"])`,
   `state.set_state(waiting_for_hours_and_rate)`,
   `"Введите часовую ставку:"`.
3. `catalog_pick:none` callback → показать 6 inline-кнопок категорий
   (рус. названия → значения `WorkCategory`: Диагностика/ТО/Кузовные/
   Электрика/Ходовая/Прочее → diagnostics/maintenance/body/electrical/
   chassis/other), `state.set_state(choosing_category)`.
4. `category_pick:{value}` callback (состояние `choosing_category`) →
   `state.update_data(category=value)`, `state.set_state(waiting_for_hours_and_rate)`,
   `"Введите нормо-часы и ставку через пробел (например: 1.5 800):"`.
5. `waiting_for_hours_and_rate` message handler — ветвление по
   наличию `data.get("norm_hours")`:
   - есть (путь из справочника) → `message.text` целиком — ставка
     (`float`).
   - нет (свободный путь) → `message.text.split()` → `norm_hours`,
     `hourly_rate` (оба `float`).
   Затем `api.add_work_item(visit_id=data["visit_id"], catalog_item_id=data.get("catalog_item_id"), free_text_name=data.get("free_text_name") if not data.get("catalog_item_id") else None, category=data["category"], norm_hours=..., hourly_rate=...)`,
   `state.clear()`, `send_visit_card(message, visit)` — визит
   перечитывается через `api.get_visit(visit_id)` (новый метод
   `ApiClient`, `GET /visits/{id}`, эндпоинт уже существует в
   backend).

`is_extra_work` не выставляется из этого визарда (остаётся `False` по
умолчанию схемы) — решение, требуется ли отдельный UI-переключатель
"дополнительная работа", вне охвата этой доработки; текущий approve-flow
(пункт C) не привязан к этому флагу, а к `approved_by_client`.

### C. Кнопки "Согласовать" и смены статуса

**Карточка заезда (`send_visit_card`)** — расширяется: помимо
кнопок смены статуса заезда, подгружает
`api.list_work_items(visit_id)` (новый метод, `GET
/visits/{id}/work-items`) и добавляет по одной кнопке
`"✅ {название}"` / `callback_data=f"approve_work:{item_id}"` на каждую
позицию с `approved_by_client is False`. Обработчик `approve_work:`
→ `api.approve_work_item(visit_id, item_id)`, затем
`send_visit_card` заново.

**"Мои работы" (`bot/handlers/mechanic.py`, Задача 17)** — на каждую
строку добавляется одна inline-кнопка "Следующий статус" (текст —
следующее значение `WorkItemStatus` по порядку
`not_ready → in_progress → waiting_parts/ready`, без ветвления —
для MVP кнопка всегда предлагает один "следующий" статус, как
записано в перечислении `WorkItemStatus`, а не полный граф переходов,
т.к. у работ, в отличие от заезда, нет ветвящейся FSM-таблицы в
backend), `callback_data=f"work_status:{item_id}:{next_status}"`. Один
обработчик на роутер, использует уже существующий
`api.update_work_item_status`.

## Границы (что НЕ входит)

- Переназначение мастера заезда на кого-то, кроме себя — не входит
  (спека называет это дефолтом, альтернативный UI не описан нигде).
- `is_extra_work` как явный переключатель в UI — не входит, требует
  отдельного продуктового решения.
- Полный граф переходов статуса работы (`WorkItemStatus`) со
  множественными вариантами, аналогично `_NEXT_STATUS_BY_CURRENT` у
  заезда — не входит, backend не публикует такой граф; один
  "следующий" статус по порядку enum — временное упрощение для MVP.

## Тестирование

Для каждого нового/изменённого обработчика — TDD как в остальном
плане: юнит-тест на `AsyncMock`-е `api`/`message`/`callback`, без
реальной БД (кроме нового backend-эндпоинта `list_for_visit`, который
тестируется как остальные `work_items` эндпоинты — через
`tests/modules/visits/test_work_items_*`, с реальным `AsyncSession`).
