# syntax=docker/dockerfile:1
# One image for both the API and the Telegram bot; docker-compose.yml picks the command.

ARG PYTHON_VERSION=3.14

FROM python:${PYTHON_VERSION}-slim-trixie AS builder

COPY --from=ghcr.io/astral-sh/uv:0.12.22 /uv /usr/local/bin/uv

ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    uv sync --locked --no-dev --no-install-project


FROM python:${PYTHON_VERSION}-slim-trixie

# WeasyPrint needs Pango; DejaVu covers Cyrillic in generated PDFs.
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    rm -f /etc/apt/apt.conf.d/docker-clean \
    && apt-get update \
    && apt-get install -y --no-install-recommends libpango-1.0-0 libpangoft2-1.0-0 fonts-dejavu-core

RUN groupadd --system app && useradd --system --gid app --no-create-home app \
    && mkdir -p /data/storage && chown app:app /data/storage

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    FILE_STORAGE_ROOT=/data/storage

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app
COPY bot ./bot

USER app

EXPOSE 8000
HEALTHCHECK --interval=5s --timeout=3s --start-period=10s --retries=10 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
