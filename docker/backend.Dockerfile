FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PATH="/opt/venv/bin:${PATH}"

WORKDIR /app

RUN python -m venv /opt/venv \
 && pip install --upgrade pip


FROM base AS builder

RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential \
 && rm -rf /var/lib/apt/lists/*

COPY backend/pyproject.toml backend/alembic.ini ./backend/
COPY backend/src/ ./backend/src/

RUN pip install ./backend


FROM base AS dev

RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential \
 && rm -rf /var/lib/apt/lists/*

COPY backend/pyproject.toml backend/alembic.ini ./backend/
COPY backend/src/ ./backend/src/
COPY backend/tests/ ./backend/tests/

RUN pip install -e "./backend[dev]"

WORKDIR /app/backend
CMD ["uvicorn", "pitwall.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]


FROM base AS prod

COPY --from=builder /opt/venv /opt/venv
COPY backend/alembic.ini ./backend/alembic.ini
COPY backend/src/ ./backend/src/

WORKDIR /app/backend
CMD ["uvicorn", "pitwall.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
