# One image for both the API and the Telegram bot; docker-compose.yml picks the command.
FROM python:3.12-slim

# WeasyPrint needs Pango; DejaVu covers Cyrillic in generated PDFs.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpango-1.0-0 libpangoft2-1.0-0 fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv

ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencies first so code edits don't invalidate this layer.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app
COPY bot ./bot

EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
