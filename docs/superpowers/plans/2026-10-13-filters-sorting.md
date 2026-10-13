# Фильтры и сортировки списков — план

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** серверные фильтры/сортировки для всех списков работ и заездов + экраны «Доска работ» и «Архив заездов», в вебе и в боте.

**Architecture:** вся логика отбора и порядка — в сервисах FastAPI (параметры запроса); веб (React Query, ключ = параметры) и бот (args экрана + общий механизм `opt:` кнопок) только передают выбор и рисуют.

**Tech Stack:** FastAPI + SQLAlchemy async, pytest; React 18 + TanStack Query + MSW/vitest; aiogram 3.

**Spec:** `docs/superpowers/specs/2026-10-13-filters-sorting-design.md`

## Global Constraints

- `STALE_DAYS = 3`; лимиты: заезды 30/страница, done 100, board 200, история 30.
- Срочность: in_progress → not_ready → waiting_parts → ready.
- Воронка: received → diagnostics → approval → in_progress → waiting_parts → ready → issued → cancelled.
- Механик не получает денежных полей.
- callback_data бота ≤ 64 байт; активная кнопка-фильтр начинается с «✓ ».
- Тексты UI — по-русски, как в спецификации.

## Review Focus

- Фильтр без совпадений → пустое состояние «… с этим фильтром», а не «нет данных вообще» (веб, бот).
- `status_changed_at` у заезда без записей в логе = `created_at` (тест на сервере).
- Повторный клик по уже выбранной кнопке бота — не ломает экран («message is not modified» уже глушится в `nav.present`) (тест: args не меняются).
- Устаревшая кнопка `opt:` со старого сообщения → «кнопка устарела», а не смена фильтра чужого экрана (тест).
- Админ-фильтр по мастеру не показывается мастеру (тест веб + бот).

---

### Task 1: API заездов — фильтры, сортировки, итоги
**Files:** `app/modules/visits/repository.py`, `service.py`, `router.py`, `schemas.py`; tests `tests/modules/visits/test_visit_filters.py`
**Produces:** `GET /visits` params `status[] closed master_id unassigned_work stale since sort offset`; `VisitOut.status_changed_at`; `VisitListOut.total_count, issued_amount`.
- [ ] Тесты: каждый фильтр, 4 сортировки, offset, total_count/issued_amount без лимита, status_changed_at по логу и без лога.
- [ ] Реализация: `status_changed_at_expr()` (коррелированный подзапрос `coalesce(max(changed_at), created_at)`), `VisitFilters` dataclass, count/sum отдельным запросом с теми же условиями.
- [ ] Полный pytest, коммит.

### Task 2: API работ механика — мои/выполненные, история по категориям
**Files:** `app/modules/visits/work_items_service.py`, `work_items_schemas.py`, `work_items_mine_router.py`, `vehicle_history_router.py`; tests в `test_work_items.py`, `test_work_items_routes.py`, `test_vehicle_history_routes.py`
**Produces:** `GET /work-items/mine?status[]&sort=urgency|car`; `GET /work-items/mine/done?since&outcome` → `{items[{…, norm_hours, closed_at}], count, total_norm_hours, has_more}`; `GET /vehicles/{id}/work-history?category[]`, элемент += `category`.
- [ ] Тесты → реализация (`URGENCY_ORDER` CASE-выражение общее для всех) → pytest → коммит.

### Task 3: API «Доска работ»
**Files:** новый `app/modules/visits/board_router.py` (+ подключение в `app/main.py`), сервис `list_board` в `work_items_service.py`, схема `WorkItemBoardOut`, `WorkItemBoardListOut`; tests `tests/modules/visits/test_work_board.py`
**Produces:** `GET /work-items/board?mechanic_id|unassigned&status[]&category[]&unapproved&group=mechanic|status|car` → `{items, has_more}`.
- [ ] Тесты (фильтры, 3 группировки, закрытые заезды исключены, механику 403) → реализация → коммит.

### Task 4: Веб — API-слой и общие контролы
**Files:** `web/src/api/types.ts`, `endpoints.ts`, новый `web/src/ui/Chips.tsx` (`<Chips options value onChange label>`), `web/src/ui/SelectField.tsx` при необходимости, `web/src/lib/periods.ts` (`sinceFor(period)`), `labels.ts` (категории уже есть); tests `ui.test.tsx`, `lib.test.ts`.
- [ ] Типы и методы: `visitsApi.list(params)`, `workItemsApi.mine(params)`, `.done(params)`, `.board(params)`, `vehiclesApi.workHistory(id, categories)`; построитель query string с повторяемыми ключами.

### Task 5: Веб — «Заезды в работе»
**Files:** `web/src/screens/VisitsScreen.tsx` (+ test). Чипы фильтров, select сортировки, select мастера (админ), «N дн. в статусе», кнопки «Доска работ» и «Архив».

### Task 6: Веб — «Архив заездов» и «Доска работ»
**Files:** новые `web/src/screens/ArchiveScreen.tsx`, `BoardScreen.tsx` (+ tests), `routes.tsx`, `MoreScreen.tsx`.

### Task 7: Веб — экраны механика, история авто, карточка заезда
**Files:** `MyWorksScreen.tsx`, `DoneWorksScreen.tsx`, `VehicleScreen.tsx`, `VisitScreen.tsx` (+ tests).

### Task 8: Бот — механизм опций и API-клиент
**Files:** `bot/nav.py` (`OPT = "opt"`, `option_button(text, key, value, current)`, `cycle_button(label, key, values, current)`, обработчик `opt:` с проверкой живого сообщения и `replace_top`), `bot/api_client.py` (новые параметры, `list_work_board`), tests `test_nav.py`, `test_api_client.py`.

### Task 9: Бот — заезды, архив, доска
**Files:** `bot/handlers/navigation.py` (active_visits с фильтрами), новый `bot/handlers/staff_lists.py` (`archive`, `board`), `menu.py` (пункты «🗄 Архив заездов», «📋 Доска работ»), tests `test_visit_screens.py`/новый `test_staff_lists.py`, `test_callback_sizes.py`.

### Task 10: Бот — механик, история, карточка заезда
**Files:** `bot/handlers/mechanic.py`, `navigation.py` (work_history), `visits.py` (`visit_card` сортировка по срочности), tests.

### Task 11: Проверка
- [ ] pytest, vitest, tsc; пересборка api+bot; скриншоты веба (390px) под механиком/мастером/админом; рендер экранов бота в контейнере; обновить память; слияние в main по запросу.
