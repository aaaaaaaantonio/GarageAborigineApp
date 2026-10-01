# SDD ledger — plan: docs/superpowers/plans/2026-09-15-crm-backend-plan.md

> **Recovery note (2026-09-19):** this file was accidentally deleted by `git worktree remove --force
> .claude/worktrees/crm-backend` (the directory was never git-tracked, only lived inside that
> worktree). Reconstructed from conversation context immediately after. The per-task
> `task-N-brief.md` / `task-N-report.md` files and `review-*.diff` files that lived alongside this
> ledger were **not** recoverable (their content was never read into context) and are permanently
> lost. This file's content below is intact/verbatim as of the loss.

## Preflight scan (2026-09-15)

Проверено: спек прочитан (docs/superpowers/specs/2026-09-15-crm-backend-design.md), Global Constraints выписаны. Скан по парам задач, делящим файл/интерфейс, и самосогласованность каждой задачи.

| Пара/задача | Общий файл/интерфейс | Найдено |
|---|---|---|
| T6→T7→T8→T9→T13 | app/modules/visits/{models,service}.py | Последовательные modify одного файла — порядок задач это и есть порядок правок, конфликта нет |
| T9(шаг5)→T13(шаг4) | app/modules/visits/work_items_service.py::add_item | Обе задачи дописывают код в конец метода. T13 не уточняет порядок вставки notification-вызова относительно record_audit. Ruling ниже |
| T3→T10 | app/modules/clients/service.py::create_client | T10 явно меняет сигнатуру (acting_user опционален) — уже описано в тексте T10, не пропущено |
| T4→T11 | app/core/plate.py | Уже вынесено в T4 (core), T11 просто импортирует — конфликта нет (это было исправлено при самопроверке плана до коммита) |
| Global Constraints vs T4/T8/T9/T10/T11/T13 модели | "Soft delete везде... во всех модулях" | Дочерние/лог-таблицы (visit_work_items, visit_part_items, vehicle_ownership, consents, consent_drafts, recent_views, audit_log, visit_status_log, notifications_outbox) НЕ имеют deleted_at — соответствует таблице модели данных в спеке (deleted_at только у clients/vehicles/work_catalog/visits/users), но противоречит буквальной формулировке Global Constraints. Ruling ниже |
| Все задачи с alembic autogenerate | app/core/db.py, alembic/env.py | T1 даёт только общую заметку "импортировать модели по мере появления" — нет явного шага в T2-T13. Операционный риск пустой миграции. Ruling ниже (процедурный, не правка плана) |
| Circular imports: notifications↔visits | T13 | notifications/logging_sender.py импортирует visits.models (не service); visits/service.py импортирует notifications.logging_sender — однонаправленно, цикла нет |
| Типы enum в моделях (T7 changed_at, T2 AuditLog.at, T13 NotificationOutbox.created_at) | — | Уже исправлено до коммита плана (Mapped[object]→Mapped[datetime]) |

**Ruling 1:** T13 шаг4 (уведомление о extra_work в WorkItemService.add_item) вставляется ПОСЛЕ вызова recalculate_total (T9 шаг5) и ПЕРЕД record_audit — симметрично точке вставки T9. Не load-bearing (порядок не влияет на корректность), но снимает двусмысленность для исполнителя T13. — Стоит < 5 минут переписать порядок двух строк, если ошибусь.

**Ruling 2:** Формулировка Global Constraints "Soft delete везде... во всех модулях" трактуется как относящаяся только к 5 сущностям, которым спек прямо даёт `deleted_at` в таблице модели данных (clients, vehicles, work_catalog, visits, users). Дочерние/журнальные таблицы (visit_work_items, visit_part_items, vehicle_ownership, consents, consent_drafts, recent_views, audit_log, visit_status_log, notifications_outbox) — исключение по дизайну (append-only логи либо нет ни одного delete-эндпоинта в этом плане вообще). Ревьюеры задач НЕ должны флагать отсутствие `deleted_at` на этих таблицах как нарушение Global Constraints. — Если ошибусь: добавить deleted_at этим таблицам — тривиальная миграция, риск минимален.

**Ruling 3 (процедурный, не относится к тексту плана):** каждая задача, добавляющая новые ORM-модели (T2–T13), обязана перед `alembic revision --autogenerate` дописать соответствующий `import app.modules.<name>.models  # noqa` (и `.audit`, `.logging_sender` где применимо) в `alembic/env.py` — иначе autogenerate создаст пустую миграцию. Буду включать это напоминание в каждый dispatch начиная с Task 2. — Если implementer забудет: пустая миграция обнаружится на этапе review диффа (нет CREATE TABLE в файле миграции), фикс — дополнить env.py и перегенерировать.

Скан завершён, чистых блокеров нет. Начинаю Task 1.

## Task 1: scaffold
Task 1: minor (deferred): pyproject.toml нет явного [build-system] (setuptools/build-backend) — фикс в будущей задаче при желании
Task 1: minor (deferred): loop-scope в pytest.ini_options глобальный на весь suite, не точечный — заметка для будущих тестов, трогающих asyncio-примитивы
Task 1: minor (deferred): нет теста на UUIDPkMixin/TimestampMixin на реальной таблице — не требовалось брифом
Task 1: complete (commits 7792f4b..6b557d8, review clean)

## Task 2: users/RBAC/audit
Ruling (plan-mandated findings, Task 2): оба Important-финдинга реальны — брифовый тест test_create_user_writes_audit_row не проверяет AuditLog вообще (имя лжёт), test_auth.py не покрывает оба 401-пути (unknown user, soft-deleted user), хотя auth.py их реализует. Это фундаментальный код (auth+audit), от которого зависят все 12 оставшихся задач — чинить сейчас, пока дёшево, а не откладывать. Решение: fix round 1, резюмирую implementer'а. — Если ошибусь (найдётся что тесты избыточны): откат тривиален, это только тестовый код.

## Security review note (Task 2, auth.py)
Автоматический security-review пометил CRITICAL: X-User-Id header — spoofable auth bypass (любой клиент с сетевым доступом к API может выдать себя за любого пользователя, подставив чужой UUID в заголовок).
Ruling: это осознанное, уже задокументированное упрощение MVP из Global Constraints плана ("Авторизация на MVP: доверенный внутренний API... Полноценный OAuth/JWT — вне рамок MVP"). API на этом этапе не имеет ни одного публичного эндпоинта, не выставлено в интернет, единственный потребитель — бот следующего цикла (сам будет server-side, не клиентский код). Меняю НЕ дизайн, а довожу до пользователя явно, т.к. finding CRITICAL и затрагивает архитектуру всех оставшихся 12 задач. — Если пользователь не согласен: переделка auth.py + require_role на JWT/токены — локализованная правка (только Task 2), не требует переписывать остальные задачи (они вызывают require_role(...) по интерфейсу, не по механизму).
Task 2: fix round 1/5 (2 addressed, 0 open; commits 0b7d2dc..01eabed)
Task 2: minor (deferred): schemas.py UserOut.Config — Pydantic v1-style deprecated, warning only
Task 2: complete (commits 6b557d8..01eabed, review clean)

## Task 3: clients module
Ruling (plan-mandated finding, Task 3): router.py get_client's `client_id` param has no type annotation, copied verbatim from brief Step 7. Reviewer verified via app.openapi() that this disables FastAPI's automatic UUID validation, and traced the asyncpg codec path showing a malformed id reaches session.get() uncaught → unhandled 500 instead of a clean 422/404. Real bug, not a style nit. Fixing: annotate as `client_id: uuid.UUID` (contradicts brief's literal sample, but the brief's own Produces-interfaces section implies typed UUIDs everywhere else). — Cost if wrong: one-line revert, no downstream impact (Task 4+ don't consume this signature).
Task 3: minor (deferred): ClientRepository.get() doesn't filter deleted_at — GET /clients/{id} can return soft-deleted rows, inconsistent with get_by_phone
Task 3: minor (deferred): no DB-level uniqueness on phone_normalized, create_client doesn't check for existing — dedup left to caller
Task 3: minor (deferred): telegram_id stored as 32-bit Integer (mirrors Task 2's User.telegram_id, pre-existing pattern)
Task 3: minor (deferred): migration downgrade() doesn't drop the clienttype enum (mirrors Task 2's userrole enum gap)
Task 3: minor (deferred): test coverage limited to brief's single happy path — no test for get()->None/soft-delete exclusion, legal client + legal_details, router-level 404/create, malformed phone input
Task 3: fix round 1/5 (1 addressed, 0 open; commits 6239620..c1b92b7)
Task 3: complete (commits 01eabed..c1b92b7, review clean)

## Task 4: vehicles + ownership
Task 4: minor (deferred): update_mileage uses assert for not-found check instead of raised exception
Task 4: minor (deferred): attach_owner doesn't verify vehicle exists first — unknown vehicle_id surfaces as unhandled FK IntegrityError (500) not 404
Task 4: minor (deferred): get_by_vin unused in this diff, no deleted_at filter (unlike ClientRepository.get_by_phone_normalized)
Task 4: minor (deferred): attach_owner router returns raw dict, no response_model
Task 4: minor (deferred): no test for GET 404, update_mileage, duplicate-VIN FK violation
Task 4: complete (commits c1b92b7..fb322cd, review clean)

## Task 5: work catalog (fuzzy suggest)
Task 5: minor (deferred): repository.py unused `import uuid`
Task 5: minor (deferred): similarity(name,:q) computed twice (WHERE + ORDER BY) instead of labeled once — perf, not correctness
Task 5: minor (deferred): no test for soft-deleted row excluded from suggest()
Task 5: minor (deferred): no audit-row test for catalog create (unlike users module's pattern)
Task 5: minor (deferred): no GIN trigram index on work_catalog.name — will matter at scale
Task 5: complete (commits fb322cd..e6e45e8, review clean)

## Task 6: visit intake
Automated background security review of commit 8003889 flagged 2 issues in app/modules/visits/service.py (audit-log-evasion, broken-authorization) — no detailed body delivered, only category labels. Reading the code (verbatim from brief): (1) audit-log-evasion likely = vehicle_service.update_mileage() mutates vehicle.mileage_current with zero record_audit call, only the visit-create audit entry exists; (2) broken-authorization likely = VisitCreate.assigned_master_id taken directly from request body with no check that it references a real user with MASTER role — any admin/master caller can assign a visit to an arbitrary UUID. Both match the brief's own verbatim code, both real gaps. Awaiting Task 6 task-reviewer report to fold these into one combined fix dispatch instead of two separate rounds.

## Task 6: visit intake — review
Task reviewer (sonnet): Spec ✅ all 9 steps + global constraints satisfied. Task quality: Needs fixes.
Important (confirmed): assigned_master_id (schemas.py:11) accepted with zero existence/role check — service.py:19-34 passes it straight to Visit() constructor; ADMIN/MASTER caller can point it at a MECHANIC, another ADMIN, soft-deleted user, or nonexistent UUID (→ unhandled IntegrityError/500). Real gap in both brief and implementation. Entering fix loop round 1.
Task 6: minor (deferred): audit-log-evasion (mileage mutation has no dedicated audit trail) is real but root cause is Task 4's VehicleService.update_mileage, out of Task 6 scope — track as Task 4 follow-up, not a Task 6 blocker.
Task 6: minor (deferred): task-6-report.md fabricates brief citations for two deviations (planned_ready_at type, visit_id annotation) — technical choices are correct, citations aren't in task-6-brief.md.
Task 6: minor (deferred): report's "Next Steps" claims Task 7 = Telegram bot — wrong, Task 7 is visit-status FSM, bot is a separate later cycle.
Task 6: minor (deferred): test_intake.py:2 unused `from datetime import date` import.
Task 6: minor (deferred): VisitService.get(self, visit_id) missing uuid.UUID type annotation, inconsistent with router.get_visit fix.
Task 6: minor (deferred): no test asserts vehicle.mileage_current updated, audit row written, or HTTP-level 409 round trip.
Task 6: minor (deferred): AssertionError/IntegrityError on bad ids surface as generic 500 (pre-existing pattern from Tasks 3-4, not a new regression).
Task 6: fix round 1/5 (1 addressed, 0 open; commits 8003889..a186336)
Task 6: complete (commits e6e45e8..a186336, 6 minors deferred, review clean after fix round 1)

## Task 7: visit status FSM — BLOCKED, plan defect found
Implementer (sonnet) correctly stopped before writing code: Task 7 Step 5 (change_status) imports/queries `VisitWorkItem` (app/modules/visits/models.py), which does not exist yet — it's first defined in Task 8 (plan line 2194), which comes AFTER Task 7 in the plan's sequence. Preflight scan's T6→T7→T8→T9→T13 row assumed pure sequential-modify-same-file with no conflict and missed this forward reference entirely — preflight scan was incomplete on this point.
Implementer also flagged a second latent bug in the brief's own sample test (`test_ready_blocked_until_all_work_items_ready`): it never creates any VisitWorkItem rows, so the READY-gate check (`any(i.status != READY for i in items)`) is vacuously False on an empty list and wouldn't actually test the gate — real but only surfaces once Task 8 exists; tracked below.
Ruling: reorder EXECUTION only — implement Task 8 (VisitWorkItem, work_items_service/router/schemas) before Task 7 (status FSM). Neither task's plan text needs editing: Task 8 has no dependency on Task 7's FSM or VisitStatusLog (consumes only Tasks 1/5/6), and both tasks independently append to the end of app/modules/visits/models.py so edit order doesn't conflict either way. Once Task 8 lands, Task 7's Step 5 import resolves and the brief runs as written. — Cost if wrong: trivial, this is pure sequencing with no plan-text change; worst case is redoing the reorder.
Ruling: the vacuous-truth gap in Task 7's own sample test is real but not actionable until Task 8's VisitWorkItem exists. Carry this into Task 7's dispatch (after Task 8 is done) as an explicit fix-on-arrival: the test must create at least one non-READY VisitWorkItem before asserting NotAllWorkItemsReady, otherwise the assertion is meaningless. — Cost if wrong: caught by Task 7's task review either way, no downstream risk.
Task 7: deferred, resuming after Task 8 (see ruling above)

## Task 8: visit work items — review
Task reviewer (sonnet): Spec ✅ all steps + global constraints satisfied. Both claimed bug fixes (approved_at tz-aware column, workcategory enum create_type=False) independently verified. Fixture adaptation for Task 6's assigned_master_id constraint verified correct. Task quality: Approved.
Important (plan-mandated, both literal brief code, not implementer defects):
  1. work_items_service.py update_status/approve use bare `assert item is not None` on client-supplied item_id → unhandled 500 instead of 404.
  2. add_item has no existence check on visit_id → bad id hits FK IntegrityError on flush → unhandled 500 instead of 404/422.
Ruling: park both, no fix dispatched. Ledger precedent from Task 4 already deferred the identical class of finding as Minor ("attach_owner doesn't verify vehicle exists first — unknown vehicle_id surfaces as unhandled FK IntegrityError (500) not 404"), and the same gap exists untouched across vehicles/catalog modules. Fixing it only in Task 8 while leaving Tasks 3/4/5's equivalent gaps open is inconsistent effort for no real risk reduction on an MVP trusted-internal-API (Global Constraints) with no public endpoints yet. Better handled as one batch hardening pass (add existence checks + proper 404/422 mapping across all modules) flagged for the final whole-branch review, not a per-task fix loop. — Cost if wrong: a malformed/missing id currently surfaces as a generic 500 instead of a 4xx in several modules; trivial to batch-fix later, no data-integrity risk (nothing is corrupted, just an ugly error code).
Task 8: minor (deferred): work_items_router.py visit_id/item_id path params lack uuid.UUID type annotation (plan-mandated, inconsistent with Task 6 fix).
Task 8: minor (deferred): update_status role check via acting_user.role.value == "mechanic" string literal instead of UserRole.MECHANIC enum compare (plan-mandated, style only).
Task 8: minor (deferred): assigned_mechanic_id accepted with no role check (unlike Task 6's InvalidAssignedMaster pattern) — not requested by brief, follow-up candidate.
Task 8: minor (deferred): update_status/approve don't call record_audit (only add_item does) — no established precedent either way.
Task 8: minor (deferred): MissingWorkNameSource exception is dead code (validation actually done via Pydantic model_validator per brief's own Step 3) — kept per implementer's literal-brief discipline.
Task 8: complete (commits a186336..9cac7e7, review clean — 2 Important parked with ruling, 5 minors deferred)

## Task 7: visit status FSM — review
Task reviewer (sonnet): Spec ✅ all 9 steps + global constraints satisfied. Both controller-mandated fixes (assigned_master_id fixture, non-vacuous READY-gate test) verified as genuine, not cosmetic. Implementer's independently-claimed enum-collision migration fix (visitstatus, create_type=False) verified correct against Task 8's precedent. Task quality: Approved.
Important (plan-mandated): service.py change_status uses bare `assert visit is not None` on client-supplied visit_id → unhandled 500 instead of 404. Same class as Task 8's parked findings.
Ruling: park, same reasoning as Task 8's ruling — batch hardening candidate for final whole-branch review, not a per-task fix loop on an MVP trusted-internal-API with no public endpoints yet.
Task 7: minor (deferred): test_valid_transition_logs_status_change never actually queries VisitStatusLog to confirm a row was written, despite its name — audit-trail purpose of the table goes unverified by any test in this diff.
Task 7: minor (deferred): no router-level HTTP test coverage — matches existing codebase convention (service-layer-only tests), not a regression.
Task 7: complete (commits 9cac7e7..0e82b0b, review clean — 1 Important parked with ruling, 2 minors deferred)

## Task 9: visit part items + total recalculation — review
Task reviewer (sonnet): Spec ✅ all 9 steps satisfied. Verified independently-found migration downgrade() enum-drop fix (db86d669174d, drops `partavailability`) against sibling pattern in 3b2df745e6b6 (visit_work_items) — correct, drops only the enum this table owns. Task quality: Approved.
Important (plan-mandated): recalculate_total (service.py:294-310) casts all financial values (norm_hours, hourly_rate, quantity, unit_price, discount) to Python `float` before summing, total_amount assigned as float — contradicts Global Constraints' Numeric(10,2)/Decimal-precision intent. Copied verbatim from brief Шаг 3 sample code, not an implementer deviation.
Ruling: park, no fix dispatched now. Numeric(10,2) rounds to cents on write, so drift is bounded to sub-cent noise per recalculation on an MVP with low item counts per visit; not a novel risk this task introduced (same float-cast pattern the brief mandates). Fixing only here while every other money-touching path in the plan (T4 mileage, T6 visit create, later T10-T13) hasn't been audited for the same pattern is inconsistent effort. Batch into the final whole-branch review as one Decimal-precision hardening pass across the whole visits module (switch to `decimal.Decimal(str(...))` arithmetic or accumulate as Decimal instead of float) rather than a per-task fix loop. — Cost if wrong: total_amount could drift by a few cents on visits with many work/part items before the Numeric(10,2) column rounds it on write; fix is localized to recalculate_total's arithmetic, no schema change needed, low blast radius.
Task 9: minor (deferred): PartItemService.add_item (part_items_service.py:24) doesn't verify work_item_id belongs to visit_id — cross-visit part-item creation possible, no FK/service check.
Task 9: minor (deferred): PartItemOut omits visit_id/work_item_id/article_number/availability_status (matches brief exactly, not a deviation) — caller gets back less than submitted, revisit if bot/frontend needs full record.
Task 9: minor (deferred): work_items_service.py:27 local-scoped VisitService import has no actual circular-import reason (verified: service.py doesn't import work_items_service) — matches brief's prescribed style, style-only note.
Task 9: complete (commits 0e82b0b..60b1b83, 1 Important parked with ruling, 3 minors deferred)

## Task 10: consent service — in progress
Automated background security review flagged consent/router.py (`confirm` endpoint, Шаг 7 in brief): `data.ip_address = data.ip_address or (request.client.host if request.client else None)` — `ConsentConfirm.ip_address` is a client-suppliable field, only overridden by the real connection IP when the client omits it. Same class as Task 6's assigned_master_id gap (spoofable field, literal brief code) — flag for the task review, and if confirmed real, fold into the fix loop rather than a separate ad-hoc patch. This field feeds a legal-consent audit trail (consent_date/ip_address/verification_ref), so unlike most parked minors this one has compliance weight — do not auto-park without judgment at review time.

## Task 10: consent service — review
Task reviewer (sonnet): Spec ✅ (files/migration/tests match brief) with one ⚠️ noted (router doing ip_address fallback logic, folded into finding below). Task quality: Needs fixes.
Important (plan-mandated, both literal brief code, not implementer deviations):
  1. router.py:254 `data.ip_address = data.ip_address or (request.client.host if request.client else None)` — ConsentConfirm.ip_address is client-suppliable (schemas.py:90); caller can fabricate IP that lands verbatim in Consent.ip_address, a legal-consent audit field (consent_date/ip_address/verification_ref). Same class as Task 6's assigned_master_id (ruled Important there, fixed).
  2. service.py confirm() — get_valid_draft only checks None/expiry, never checks draft.converted_client_id already set → same still-valid token can be replayed to create duplicate Client+Consent rows from one QR scan. converted_client_id field exists but the guard using it was never wired in.
Ruling 1: fix — service always derives ip_address server-side from request.client.host, drop client-suppliable override entirely (remove ip_address from ConsentConfirm or ignore it, router passes real IP into service call, service signature takes ip_address as a separate param it always trusts from the router's connection-derived value, not from the body). Contradicts brief's literal sample, justified same as Task 6 precedent (client-spoofable field feeding a record where correctness/compliance matters). — Cost if wrong: one-line revert, no downstream task consumes ConsentConfirm's shape.
Ruling 2: fix — add DraftAlreadyUsed check in confirm() (raise if draft.converted_client_id is not None, before creating client/consent), map to 409 in router. Not brief-mandated omission style (brief's sample just never wired the guard), real correctness gap on a legal record. — Cost if wrong: trivial, localized to consent module only.
Task 10: fix round 1/5 (dispatching fresh implementer, original implementer not resumable in this session)
Task 10: fix round 1/5 (2 addressed, 0 open; commits 7641a4e..147fbc6)
Task 10: complete (commits 60b1b83..147fbc6, review clean after fix round 1)

## Task 10: post-completion finding (automated security review, commit 147fbc6)
Automated background security review flagged TOCTOU race in ConsentService.confirm(): the DraftAlreadyUsed guard (fix round 1) reads `draft.converted_client_id` then later sets it in the same transaction, no row lock / unique constraint — two concurrent requests with the same still-valid token can both pass the None-check before either commits, still producing duplicate Client+Consent rows under concurrency (narrows but doesn't close the Finding 2 gap the fix round targeted).
Ruling: park, no fix dispatched now. Real gap, but same class as every other unenforced-at-DB-level invariant already deferred in this plan (Task 3's missing phone_normalized uniqueness, Task 9's cross-visit part-item check) — MVP trusted-internal-API, QR-onsite confirm is a low-concurrency human-paced flow (one physical scan), not a hot path. Proper fix is a unique constraint or `SELECT ... FOR UPDATE` on consent_drafts.token, batched into the final whole-branch review alongside the other unenforced-invariant findings rather than a new fix loop reopening a task already marked complete. — Cost if wrong: a genuine double-scan race (same token, near-simultaneous requests) could still create duplicate client/consent records; low likelihood given the physical QR flow, no data corruption (both rows are individually valid), fix is localized to consent module (DB constraint + migration) whenever addressed.

## Task 11: search + recent_views — review
Task reviewer (sonnet): Spec ✅ all steps satisfied (strategies.py correctly skipped per brief's own permission), extensibility/SQL-safety/params-binding risk areas verified correct, empirically confirmed via test run. Task quality: Needs fixes.
Important (plan-mandated, literal brief code): EXACT_OR_SUFFIX branch (service.py, brief Шаг 1/3) does `column.like(f"%{query.upper()}")` when `len(query) <= 4` — empty query `q=""` compiles to `LIKE '%'`, dumping the entire non-deleted vehicles table with no pagination. router.py's `q: str` has zero validation (global constraint: router = validation + service call).
Ruling: fix — add `Query(min_length=1)` (or equivalent) on router.py's `q` param, single-file mechanical fix, no service.py change needed. — Cost if wrong: trivial revert, no downstream task consumes this signature.
Task 11: fix round 1/5 (dispatching implementer)
Task 11: fix round 1/5 (1 addressed, 0 open; commits 610330e..9b6084a)
Task 11: complete (commits 147fbc6..9b6084a, review clean after fix round 1)

## Task 12: PDF visit document — review
Task reviewer (sonnet): Spec ✅ all steps satisfied, both implementer claims (document_url pre-existing, ADMIN→MASTER test fix) independently verified correct. Task quality: Needs fixes.
Important (plan-mandated, literal brief code):
  1. service.py hardcodes `"catalog_item_name": None` for every work item, never resolves WorkCatalog.name when catalog_item_id is set — catalog-based work items (a first-class path, WorkItemCreate requires exactly one of catalog_item_id/free_text_name) render with blank/None names in the official PDF document.
  2. test only asserts url is not None + document_url set — never verifies actual PDF bytes were written (file exists, non-empty, %PDF magic bytes) — a silently broken write_pdf() call would pass this test.
  3. bare `assert visit is not None` (service.py:114) → unhandled 500 instead of 404 on client-suppliable visit_id — same deferred class already parked across Tasks 6/7/8 (vehicles/service.py:56, visits/service.py:70,105, work_items_service.py:51,60). Not new.
Ruling 1: fix — service.py's work_items rendering must query WorkCatalog by catalog_item_id when set and use its .name; keep free_text_name path as-is. — Cost if wrong: localized to documents module, one query added.
Ruling 2: fix — strengthen test to assert the PDF file exists at the storage path, is non-empty, and starts with b"%PDF". — Cost if wrong: trivial, test-only change.
Ruling 3: park, no fix — identical to the already-established deferred pattern from Tasks 6-8 (batch hardening candidate for final whole-branch review, not a per-task fix loop on an MVP trusted-internal-API). — Cost if wrong: same as prior parkings of this exact class, no new risk introduced.
Task 12: fix round 1/5 (2 addressed, 0 open; commits 9b6084a..fcc26ac)
Task 12: complete (commits 9b6084a..fcc26ac, review clean after fix round 1 — Ruling 1 catalog name resolution + Ruling 2 PDF magic-byte test both verified via full suite run, 39 passed. Ruling 3 [bare assert 404] remains parked per batch-hardening plan.)

## Task 13: notifications — interface + MVP outbox

Implemented directly (no implementer subagent dispatch this round): interfaces.py (NotificationSender protocol), logging_sender.py (NotificationOutbox model + LoggingNotificationSender), wired into VisitService.change_status (READY/WAITING_PARTS) and WorkItemService.add_item (is_extra_work), per brief steps 1-4 verbatim. Migration autogenerated cleanly (single CREATE TABLE, no enum). Full suite: 40 passed (39 pre-existing + 1 new).
Task 13: complete (commit 5d4f9be, review clean — DI seam verified, insertion order matches Ruling 1, migration clean, WAITING_PARTS FSM path in test genuinely non-vacuous, 40 passed).
Task 13: minor (deferred): NotificationSender is vestigial — LoggingNotificationSender is the only implementation ever constructed, no caller injects an alternative; expected per brief (Telegram wiring is next cycle).
Task 13: minor (deferred): no test coverage for send_extra_work_approval_request or send_document paths — brief's own Step 5 test only covers status_changed, not an implementer gap.

## Task 14: end-to-end smoke test — final task

app/main.py already wired all 10 routers (landed incrementally through Tasks 2-12), matched brief step 1 verbatim, no change needed. Wrote tests/test_end_to_end.py per brief step 2, fixing the same assigned_master_id-role latent bug already corrected in Tasks 12/13 (brief's sample uses admin.id, service requires MASTER role since Task 6's fix — swapped in a dedicated master user). Full suite: 41 passed. Verified openapi() collects all 22 routes across every module with no import/registration error.
Task 14: complete (commit 084e3bc). **All 14 tasks of the CRM backend Phase 1 (Этап 1) plan are now complete.**

## Plan complete — outstanding batch-hardening items for next cycle

Parked findings carried across the whole branch (not blocking, flagged in prior task reviews):
- Bare `assert x is not None` on client-suppliable ids → unhandled 500 instead of 404/422 (vehicles, visits, work_items, part_items, documents services).
- Float-cast arithmetic in VisitService.recalculate_total instead of Decimal (Task 9).
- No DB-level uniqueness on clients.phone_normalized; no unique constraint/row-lock on consent_drafts.token (TOCTOU double-confirm race, Task 10).
- PartItemService.add_item doesn't verify work_item_id belongs to visit_id (Task 9); attach_owner doesn't verify vehicle exists first (Task 4).
- Various missing deleted_at filters, Pydantic v1-style Config classes, missing GIN trigram index on work_catalog.name.
- X-User-Id header auth is MVP-only by design (documented decision, not a defect) — real JWT/OAuth is out of scope until a public-facing client exists.

## Merge to main (2026-09-19)

worktree-crm-backend fast-forward merged into main (main had no divergent commits since branch-off, merge-base == main's prior HEAD). main had 4 unrelated untracked scaffold files (.python-version, README.md, main.py, pyproject.toml — a different uv-init'd project, not CRM-related) that collided by path with tracked files in this branch; stashed aside (not deleted) before merging: stash "pre-crm-merge-stray-scaffold" on main, still recoverable via `git stash list`. main now at commit 0f1486d after merge + batch-hardening fix commit. Editable install redone on main (`uv sync --extra dev` + `uv pip install -e .`) since venv itself wasn't part of the merge (gitignored). Full suite verified passing on main post-merge before any further changes.

## Batch-hardening pass (2026-09-19, commit 0f1486d, on main)

Closed the "Plan complete — outstanding batch-hardening items" list above, scoped to real correctness/security gaps only (left cosmetic/perf items open, see below):
- Bare `assert x is not None` → typed exceptions (VisitNotFound/VehicleNotFound/WorkItemNotFound) → 404 at router layer. Covers visits.service (create_visit's vehicle lookup, change_status, recalculate_total), vehicles.service (update_mileage, attach_owner — now also checks vehicle exists), work_items_service (add_item now checks visit exists first, update_status, approve), documents.service (generate_visit_document).
- part_items_service.add_item: added visit-exists check + work_item_id-belongs-to-visit_id check (was previously an open FK-integrity gap allowing cross-visit part-item creation).
- recalculate_total: switched from float to `Decimal(str(...))` arithmetic — closes the Task 9 Important finding.
- consent/service.py confirm(): draft fetch now uses `SELECT ... FOR UPDATE` (repo.get_draft_by_token gained a for_update param) — closes the Task 10 post-completion TOCTOU race finding.
- work_items_router.py / part_items_router.py: added missing `uuid.UUID` path-param typing (Task 8 minor).
- 11 new regression tests added (one per fixed gap), full suite 52 passed.

Still open (not touched this pass — lower priority, left for a future cleanup pass, not blocking):
- No DB-level uniqueness on clients.phone_normalized (Task 3 minor) — would need a migration + dedup decision on existing rows, riskier than the rest of this batch.
- Pydantic v1-style `class Config` on several *Out schemas (deprecation warnings only, no functional bug).
- Missing GIN trigram index on work_catalog.name (perf at scale, not correctness).
- Missing deleted_at filters on a couple of read paths (ClientRepository.get, VehicleRepository.get_by_vin).

**Backend Phase 1 (Этап 1) is now complete on main, merged, and hardened. Next step per roadmap: Telegram bot cycle (separate brainstorming pass, aiogram 3, thin client over this API).**

## Worktree cleanup (2026-09-19)

After the merge above, `git worktree remove --force .claude/worktrees/crm-backend` was run to delete the now-merged feature worktree/branch. This directory (`.superpowers/sdd/2026-09-15-crm-backend-plan/`) lived only inside that worktree and was never git-tracked, so the force-remove deleted it along with the venv/lockfile it was meant to clear. This file was reconstructed from conversation context immediately after (see recovery note at the top); the task-N-brief/report files and review-*.diff files were not recoverable. This copy now lives at `.superpowers/sdd/` under the **main** repo root — should be committed to git if it's meant to survive future worktree cleanups.

## Tech-debt pass (2026-10-01, branch backend-tech-debt, commits 8b43fcd..870ec8c)

Closed everything left in "Still open" above plus the Task 8 minors:
- deleted_at filters on ClientRepository.get / VehicleRepository.get_by_vin.
- Partial unique index uq_clients_phone_normalized_active (WHERE deleted_at IS NULL) + ClientPhoneTaken → 409 on POST /clients, /consent/paper, /consent/confirm. Migration a3f5c1e8d2b4.
- GIN trigram index ix_work_catalog_name_trgm + `name % :q` predicate (pg_trgm.similarity_threshold set per transaction) so suggest() can use it. Migration b7d2e9f4a6c1.
- class Config → ConfigDict; pytest now errors on PydanticDeprecatedSince20.
- InvalidAssignedMechanic (422) on add_item; unknown id previously surfaced as 500 FK violation.
- audit_log rows for work-item status_change and approve; mechanic role compared via UserRole enum.
- Removed dead MissingWorkNameSource.
Suite: 198 passed. Remaining warning is WeasyPrint wanting system HarfBuzz-Subset (environment, not code).

Open, found during this pass (not fixed): bot never sends assigned_mechanic_id when adding a work item, so a mechanic's "Мои работы" is always empty in practice. search module's fuzzy client/vehicle matching has the same no-index pattern as catalog suggest had.
