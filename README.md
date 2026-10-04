# GarageAborigineApp — CRM автосервиса

Backend API (FastAPI + PostgreSQL) и Telegram-бот (aiogram 3) для персонала автосервиса:
клиенты, автомобили, визиты и их статусы, работы и запчасти, согласование доп. работ,
согласие клиента на обработку ПДн (QR), поиск, PDF заказ-наряды, уведомления в Telegram.

Бот — тонкий клиент: вся бизнес-логика живёт в API, бот только ходит в него по HTTP.

| Компонент | Технологии |
|---|---|
| API | Python 3.14, FastAPI, SQLAlchemy 2 (async), asyncpg, Alembic, WeasyPrint |
| Бот | aiogram 3, httpx |
| БД | PostgreSQL 15 (расширение `pg_trgm` для нечёткого поиска) |
| Запуск | Docker Engine + Compose v2 + Buildx; зависимости — `uv` |

---

## Содержание

- [Быстрый старт (Docker)](#быстрый-старт-docker)
- [Первый администратор](#первый-администратор)
- [Что умеет бот](#что-умеет-бот)
- [Повседневные команды](#повседневные-команды)
- [Обновление и пересборка](#обновление-и-пересборка)
- [Настройки (.env)](#настройки-env)
- [Локальная разработка без Docker](#локальная-разработка-без-docker)
- [Тесты](#тесты)
- [Миграции БД](#миграции-бд)
- [Резервные копии](#резервные-копии)
- [Устройство Docker-стека](#устройство-docker-стека)
- [Структура проекта](#структура-проекта)
- [Решение проблем](#решение-проблем)

---

## Быстрый старт (Docker)

Нужно: Docker Engine с плагинами **Compose v2** и **Buildx** (`docker compose version`,
`docker buildx version`). Старый `docker-compose` 1.x (через дефис) не подходит —
Dockerfile использует возможности BuildKit.

```bash
git clone git@github.com:aaaaaaaantonio/GarageAborigineApp.git
cd GarageAborigineApp

cp .env.example .env
# впишите токен бота от @BotFather в BOT_TOKEN (и обычно его же в TELEGRAM_BOT_TOKEN)

docker compose up -d --build
```

Что произойдёт:
1. Соберётся образ `garage-crm` (первый раз ~30 с, дальше — секунды благодаря кэшу).
2. Поднимется PostgreSQL и дождётся готовности.
3. Контейнер `api` применит миграции (`alembic upgrade head`) и запустит API на порту **8000**.
4. Когда API станет `healthy`, запустится `bot`.

Проверка:

```bash
docker compose ps                      # postgres и api — (healthy), bot — Up
curl http://localhost:8000/health      # {"status":"ok"}
```

Документация API (Swagger): <http://localhost:8000/docs>.
Запросы к API требуют заголовок `X-User-Id: <uuid пользователя>`.

## Первый администратор

Пользователей создаёт только администратор, поэтому самого первого нужно добавить
напрямую в базу. Свой Telegram ID можно узнать у бота [@userinfobot](https://t.me/userinfobot).

```bash
docker compose exec postgres psql -U crm crm -c "
INSERT INTO users (id, role, full_name, telegram_id, branch_id)
VALUES (gen_random_uuid(), 'ADMIN', 'Иван Иванов', 123456789,
        '00000000-0000-0000-0000-000000000001');"
```

- `role` — `ADMIN`, `MASTER` или `MECHANIC` (заглавными).
- `branch_id` должен совпадать с `DEFAULT_BRANCH_ID` из `.env`.

Дальше напишите боту `/start`. Остальных сотрудников администратор добавляет
прямо в боте: кнопка **«Добавить сотрудника»** (или `POST /users` в API).

## Что умеет бот

| Роль | Меню | Что внутри |
|---|---|---|
| Администратор | Новый заезд, Заезды в работе, Поиск, Регистрация клиента (бумага), Добавить сотрудника | всё, что у мастера; в «Новом заезде» выбирает ответственного мастера |
| Мастер | Новый заезд, Заезды в работе, Поиск, Регистрация клиента (бумага) | карточка заезда: статусы, работы, запчасти, согласование, PDF; поиск → карточки клиента и машины → их заезды, «Новый заезд» прямо из карточки машины |
| Механик | Мои работы, Поиск | свои работы и их статусы; поиск машины по VIN/госномеру → карточка машины и история работ (без данных клиента и цен) |

Команды (кнопка «Меню» в Telegram): `/start`, `/cancel`, `/new_client`, `/new_vehicle`.

## Повседневные команды

| Задача | Команда |
|---|---|
| Запустить всё | `docker compose up -d` |
| Остановить (данные сохраняются) | `docker compose down` |
| Статус контейнеров | `docker compose ps` |
| Логи всех сервисов | `docker compose logs -f` |
| Логи одного сервиса | `docker compose logs -f bot` (или `api`, `postgres`) |
| Перезапустить сервис | `docker compose restart bot` |
| Запустить без бота (нет токена) | `docker compose up -d api` |
| Консоль PostgreSQL | `docker compose exec postgres psql -U crm crm` |
| Shell внутри API | `docker compose exec api sh` |

Если изменили только `.env`, достаточно пересоздать контейнеры (без пересборки):
`docker compose up -d`.

## Обновление и пересборка

**Обновить код и перезапустить** (основной сценарий):

```bash
git pull
docker compose up -d --build
```

Пересоберётся образ, контейнеры пересоздадутся, новые миграции применятся
автоматически при старте `api`. Данные БД и файлы лежат в volume и не теряются.

**Пересобрать только образ** (например, после правки кода):

```bash
docker compose build              # с кэшем — быстро
docker compose build --no-cache   # с нуля — если кэш «залип»
```

**Обновить базовые образы** (свежий Python / PostgreSQL с патчами безопасности):

```bash
docker compose pull postgres
docker compose build --pull
docker compose up -d
```

**Обновить Python-зависимости**:

```bash
uv lock --upgrade                 # или точечно: uv lock --upgrade-package fastapi
uv sync --extra dev
.venv/bin/pytest                  # убедиться, что всё зелёное
docker compose up -d --build
```

Закоммитьте изменённый `uv.lock` — образ ставит зависимости строго по нему (`--locked`).

**Поменять версию Python или uv** — правьте `ARG PYTHON_VERSION` и тег образа
`ghcr.io/astral-sh/uv:...` в `Dockerfile`.

**Почистить место**, занятое старыми образами и кэшем сборки:

```bash
docker image prune -f
docker builder prune -f
```

## Настройки (.env)

Все параметры с описанием и значениями по умолчанию — в [`.env.example`](.env.example).
Кратко:

| Параметр | Обязателен | Назначение |
|---|---|---|
| `BOT_TOKEN` | **да**, для бота | Токен бота от @BotFather |
| `TELEGRAM_BOT_TOKEN` | нет | Токен для уведомлений из API; пусто — уведомления только в лог |
| `DATABASE_URL` | нет | Подключение к PostgreSQL (asyncpg) |
| `TEST_DATABASE_URL` | для тестов | Отдельная база для pytest — таблицы в ней пересоздаются |
| `API_BASE_URL` | нет | Куда бот ходит за API |
| `FILE_STORAGE_ROOT` | нет | Папка для PDF-документов |
| `CONSENT_TOKEN_TTL_MINUTES` | нет | Срок жизни QR-ссылки на согласие |
| `SEARCH_FUZZY_THRESHOLD`, `CATALOG_FUZZY_THRESHOLD` | нет | Пороги нечёткого поиска (0..1) |
| `RECENT_VIEWS_LIMIT` | нет | Сколько недавних просмотров показывать |
| `DEFAULT_BRANCH_ID` | нет | Филиал по умолчанию для новых записей |
| `SQL_ECHO` | нет | Печатать SQL в лог (отладка) |

В Docker `DATABASE_URL`, `API_BASE_URL` и `FILE_STORAGE_ROOT` переопределяются
в `docker-compose.yml` (адреса внутри сети контейнеров) — в `.env` оставляйте
значения для локального запуска.

`.env` не хранится в git. Не коммитьте токены.

## Локальная разработка без Docker

Нужно: Python 3.14, [uv](https://docs.astral.sh/uv/), системные библиотеки для
WeasyPrint (`sudo apt install libpango-1.0-0 libpangoft2-1.0-0`). PostgreSQL удобно
взять из compose.

```bash
uv sync --extra dev                      # создаст .venv с зависимостями и dev-инструментами
docker compose up -d postgres            # только база, порт 5432 открыт наружу
.venv/bin/alembic upgrade head           # миграции

.venv/bin/uvicorn app.main:app --reload  # API на http://localhost:8000
.venv/bin/python -m bot.main             # бот (во втором терминале)
```

Не запускайте одновременно локального бота и бота в Docker с одним токеном —
Telegram отдаёт обновления только одному получателю (`TelegramConflictError`).

## Тесты

```bash
docker compose up -d postgres
docker compose exec postgres createdb -U crm crm_test   # один раз
.venv/bin/pytest
```

Тесты используют базу из `TEST_DATABASE_URL` и пересоздают в ней все таблицы.
Telegram в тестах не нужен — API бота замокан.

## Миграции БД

Схема хранится в `alembic/versions/`. В Docker миграции применяются автоматически
при старте `api`; вручную:

```bash
# создать миграцию после изменения моделей в app/modules/*/models.py
.venv/bin/alembic revision --autogenerate -m "short description"
# проверьте сгенерированный файл глазами — autogenerate не всё видит

.venv/bin/alembic upgrade head        # применить локально
.venv/bin/alembic downgrade -1        # откатить последнюю
.venv/bin/alembic current             # текущая версия

docker compose exec api alembic current   # то же внутри контейнера
```

## Резервные копии

```bash
# бэкап
docker compose exec -T postgres pg_dump -U crm -Fc crm > backup_$(date +%F).dump

# восстановление (остановите api и bot, чтобы никто не писал в базу)
docker compose stop api bot
docker compose exec -T postgres pg_restore -U crm -d crm --clean --if-exists < backup_2026-10-02.dump
docker compose start api bot
```

PDF-документы лежат в volume `storage`:

```bash
docker run --rm -v garageaborigineapp_storage:/data -v "$PWD":/backup alpine \
    tar czf /backup/storage_$(date +%F).tgz -C /data .
```

**Полный сброс данных** (удалит базу и файлы безвозвратно):

```bash
docker compose down -v
```

## Устройство Docker-стека

Один `Dockerfile` собирает образ `garage-crm`, который используют и API, и бот:

- **builder-стадия**: `uv sync --locked` ставит зависимости в `/opt/venv`
  (кэш uv переживает пересборки);
- **итоговая стадия**: `python:3.14-slim-trixie` + Pango и шрифты DejaVu (кириллица в PDF),
  только venv и код, запуск от непривилегированного пользователя `app`;
- `HEALTHCHECK` опрашивает `/health`; команда по умолчанию —
  `alembic upgrade head && uvicorn ...`.

`docker-compose.yml`:

| Сервис | Что делает | Ждёт |
|---|---|---|
| `postgres` | PostgreSQL 15, порт 5432, volume `pgdata` | — |
| `api` | миграции + API, порт 8000, volume `storage` | `postgres` healthy |
| `bot` | `python -m bot.main` (healthcheck отключён — HTTP нет) | `api` healthy |

`api` и `bot` перезапускаются автоматически (`restart: unless-stopped`).

## Структура проекта

```
app/
  main.py            FastAPI-приложение, подключение роутеров, /health
  core/              настройки, подключение к БД, базовые модели, enum'ы, утилиты
  modules/           доменные модули: users, clients, vehicles, catalog, visits,
                     consent, search, documents, notifications
                     (в каждом: models, schemas, repository, service, router)
bot/
  main.py            точка входа бота, порядок роутеров
  api_client.py      HTTP-клиент к API
  handlers/          сценарии: клиенты, авто, визиты, работы, запчасти, статусы,
                     документы, согласие, сотрудники, поиск
  middlewares/       авторизация по Telegram ID, обработка ошибок
alembic/versions/    миграции
tests/               pytest: API, сервисы, бот, end-to-end сценарий
docs/superpowers/    дизайн-спецификации и планы реализации
```

## Решение проблем

**Бот отвечает «Обратитесь к администратору, ваш Telegram не привязан…»**
Вашего Telegram ID нет в таблице `users` (или запись удалена). Проверьте:
`docker compose exec postgres psql -U crm crm -c "SELECT full_name, role, telegram_id FROM users;"`

**Контейнер `bot` постоянно перезапускается**
Смотрите `docker compose logs bot`. Чаще всего пустой или неверный `BOT_TOKEN`.
После правки `.env`: `docker compose up -d`.

**`api` не становится healthy**
`docker compose logs api` — обычно ошибка миграции или недоступна база.

**Порт 5432 или 8000 занят**
Остановите локальный PostgreSQL/uvicorn или поменяйте левую часть `ports:` в `docker-compose.yml`.

**`unknown command: docker compose` / ошибки про BuildKit**
Установлен устаревший Docker из пакетов дистрибутива. Поставьте Docker Engine из
официального репозитория: <https://docs.docker.com/engine/install/ubuntu/>.

**После обновления Docker сервис не стартует: `no sockets found via socket activation`**
Перезапустите сокет-юнит:

```bash
sudo systemctl daemon-reload
sudo systemctl stop docker.service docker.socket
sudo rm -f /run/docker.sock
sudo systemctl reset-failed docker.service docker.socket
sudo systemctl start docker.socket docker.service
```
