FROM python:3.12-slim

# Keep Python from writing .pyc files and force stdout/stderr to be unbuffered
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Copy only what pip needs to resolve and install deps.
# Separate COPY so Docker can cache the layer until pyproject.toml changes.
COPY backend/pyproject.toml backend/alembic.ini ./backend/
COPY backend/src/ ./backend/src/

RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir ./backend

# Alembic reads alembic.ini from its working directory.
# Both the migrate and backend services use this image;
# the migrate service runs `alembic upgrade head` here,
# and the backend service runs uvicorn (package is installed, so CWD is irrelevant).
WORKDIR /app/backend

CMD ["uvicorn", "pitwall.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
