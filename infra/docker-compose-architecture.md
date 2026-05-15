# docker-compose Architecture

> Diagrama y descripción de los servicios. Si tocas `docker-compose.yaml`, actualiza este doc. Estado actual: `db`, `migrate`, `backend` y `frontend` levantan con `make demo`.

## Diagrama

```text
        host (laptop / VM)
        │
        │             :5173        :8000                  :5433
        ▼              ▼           ▼                      ▼
                 ┌──────────────┐  ┌───────────────────┐    ┌──────────────────┐
                 │   frontend   │  │     backend       │    │       db         │
                 │ React + Vite │─▶│ FastAPI + uvicorn │───▶│ TimescaleDB pg15 │
                 │ Vite proxy   │  │ asyncio engine    │ TCP│  + ext timescale │
                 └──────────────┘  │ replay + motor    │    │  pgdata volume   │
                                   └─────────┬─────────┘    └────────┬─────────┘
                                             │                        │
                                             │ depends_on             │
                                             ▼                        │
                                    ┌──────────────────┐              │
                                    │     migrate      │              │
                                    │ alembic one-shot │──────────────┘
                                    └──────────────────┘
```

Service dependency graph:

```text
db (healthy)
  → migrate (run-to-completion)
    → backend (healthy)
      → frontend (healthy)
```

## Servicios

### `db`

- **Imagen**: `timescale/timescaledb:2.17.2-pg15`
- **Puerto**: `127.0.0.1:${POSTGRES_HOST_PORT:-5433}:5432`
- **Volumen**: `pgdata:/var/lib/postgresql/data`
- **Init**: `docker/postgres-init.sql` — `timescaledb` + `pgcrypto` (belt-and-suspenders; migration 0001 también los crea)
- **Healthcheck**: `pg_isready -U pitwall -d pitwall` cada 5s

### `migrate`

- **Imagen**: `docker/backend.Dockerfile` (misma que `backend`)
- **Comando**: `python -m alembic -c alembic.ini upgrade head`
- **Tipo**: one-shot (`restart: "no"`)
- **`depends_on`**: `db` → `service_healthy`
- **Razón**: el backend nunca levanta sin esquema completo

### `backend`

- **Imagen**: build local de `docker/backend.Dockerfile` target `prod` (builder + prod sobre `python:3.12-slim`)
- **Puerto**: 8000
- **Comando**: `uvicorn pitwall.api.main:app --host 0.0.0.0 --port 8000 --workers 1`
- **`depends_on`**: `migrate` → `service_completed_successfully`
- **Healthcheck**: `python -c "urllib.request.urlopen('http://localhost:8000/health')"` cada 10s
- **Estado in-memory**: 1 worker obligatorio en V1 (RaceState no es serializable)

### `frontend`

- **Imagen dev**: build local de `docker/frontend.Dockerfile` target `dev`.
- **Puerto**: 5173.
- **Comando**: `pnpm dev` / Vite dev server.
- **Proxy**: `VITE_PROXY_TARGET=http://backend:8000` para `/api`, `/health`, `/ready` y `/ws`.
- **Healthcheck**: fetch a `http://localhost:5173`.
- **Prod image**: `docker/frontend.Dockerfile --target prod` sirve `dist/` con nginx y se valida en `.github/workflows/build.yml`.

## Networks

Una sola red por defecto (`default`). Servicios se ven entre sí por nombre (`backend`, `db`, etc.).

## Volúmenes

| Volumen | Tipo | Propósito |
|---------|------|-----------|
| `pgdata` | Docker volume | Datos persistentes de Postgres |
| `./data/cache` | Bind mount | Cache de FastF1 (varios GB) |
| `./models` | Bind mount | Modelos XGBoost serializados |
| `./backend/src` | Bind mount opcional | Hot reload del backend en flujos dev locales |
| `./frontend/src` | Bind mount opcional | HMR del frontend en flujos dev locales |

## Por qué un solo worker en backend

El motor mantiene `RaceState` en memoria. Si tuviéramos N workers, cada uno tendría su propio estado y verían vueltas distintas. Para V1, 1 worker.

V2 si necesita escalar: mover estado a Redis/Postgres, varios workers stateless, asyncio.Queue → Redis Streams.

## Make targets

```bash
make up          # docker compose up -d (con build si es necesario)
make down        # docker compose down (preserva volúmenes)
make down-v      # docker compose down -v (borra volúmenes)
make logs        # docker compose logs -f
make ps          # docker compose ps
make migrate     # alembic upgrade head desde .venv local
make ingest      # ingiere YEAR/ROUND/SESSION_CODE a DB
make demo-api    # db + migrate + seed + backend + Swagger
make demo        # db + migrate + seed + fit degradación + backend + frontend
```

## CI

GitHub Actions (`.github/workflows/build.yml`) construye las imágenes en cada PR para validar que el `docker-compose.yaml` es coherente. No publicamos imágenes en V1.

## Cambios futuros

- V1.5: publicar imágenes a GHCR para que el evaluador no tenga que buildear.
- V2: separar backend en N workers stateless + Redis para estado compartido.
- V2: agregar `prometheus` y `grafana` opcionales como sidecar.
