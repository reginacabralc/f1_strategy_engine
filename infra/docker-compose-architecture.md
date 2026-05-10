# docker-compose Architecture

> Diagrama y descripción de los servicios. Si tocas `docker-compose.yaml`, actualiza este doc.

## Diagrama

```text
        host (laptop / VM)
        │
        │   :5173                  :8000                  :5432 (interno)
        ▼   ▼                      ▼                      ▼
   ┌────────────────┐    ┌───────────────────┐    ┌──────────────────┐
   │   frontend     │    │     backend       │    │       db         │
   │ React + Vite   │───▶│ FastAPI + uvicorn │───▶│ TimescaleDB pg15 │
   │ (dev) o nginx  │ HTTP│ asyncio engine    │ TCP│  + ext timescale │
   │ (prod)         │ WS │ replay + motor    │    │  pgdata volume   │
   └────────────────┘    └─────────┬─────────┘    └────────┬─────────┘
                                   │                        │
                                   │ depends_on             │
                                   ▼                        │
                          ┌──────────────────┐              │
                          │     migrate      │              │
                          │ alembic one-shot │──────────────┘
                          └──────────────────┘
```

## Servicios

### `db`

- **Imagen**: `timescale/timescaledb:latest-pg15`
- **Puerto**: 5432 (interno solo, no expuesto al host por defecto)
- **Volumen**: `pgdata:/var/lib/postgresql/data`
- **Init**: `docker/postgres-init.sql` con `CREATE EXTENSION timescaledb`
- **Healthcheck**: `pg_isready -U pitwall` cada 5s
- **Recursos**: ~200 MB RAM en steady state, ~500 MB con 1 temporada cargada

### `migrate`

- **Imagen**: misma que `backend` (target `dev`)
- **Comando**: `alembic upgrade head`
- **Tipo**: one-shot (corre, termina)
- **`depends_on`**: `db` healthy
- **Razón de existir como servicio separado**: idempotencia, no quieres que el backend levante con DB no migrada

### `backend`

- **Imagen**: build local de `docker/backend.Dockerfile`
- **Puerto**: 8000 (expuesto)
- **Comando dev**: `uvicorn pitwall.api.main:app --reload --host 0.0.0.0 --port 8000`
- **Comando prod**: `uvicorn pitwall.api.main:app --host 0.0.0.0 --port 8000 --workers 1` (1 worker porque hay estado in-memory)
- **`depends_on`**: `migrate` `service_completed_successfully`
- **Volúmenes** (dev): bind mount de `backend/src` para hot reload
- **Volúmenes** (prod): solo `./data/cache` y `./models`
- **Healthcheck**: `curl -f http://localhost:8000/health`
- **Recursos**: ~400-500 MB RAM en steady state

### `frontend`

- **Imagen**: build local de `docker/frontend.Dockerfile`
- **Puerto**: 5173 (expuesto)
- **Dev**: `vite dev` con HMR
- **Prod**: `nginx` sirviendo `dist/` estático
- **`depends_on`**: `backend` healthy (no estricto, frontend puede mostrar estado degradado)
- **Volúmenes** (dev): bind mount de `frontend/src`

## Dependencias

```text
db (healthy)
  → migrate (run-to-completion)
    → backend (healthy)
      → frontend (healthy, opcional)
```

## Networks

Una sola red por defecto (`default`). Servicios se ven entre sí por nombre (`backend`, `db`, etc.).

## Volúmenes

| Volumen | Tipo | Propósito |
|---------|------|-----------|
| `pgdata` | Docker volume | Datos persistentes de Postgres |
| `./data/cache` | Bind mount | Cache de FastF1 (varios GB) |
| `./models` | Bind mount | Modelos XGBoost serializados |
| `./backend/src` | Bind mount (dev) | Hot reload del backend |
| `./frontend/src` | Bind mount (dev) | HMR del frontend |

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
make restart-backend
make demo        # up + seed + open browser
```

## CI

GitHub Actions (`.github/workflows/build.yml`) construye las imágenes en cada PR para validar que el `docker-compose.yaml` es coherente. No publicamos imágenes en V1.

## Cambios futuros

- V1.5: publicar imágenes a GHCR para que el evaluador no tenga que buildear.
- V2: separar backend en N workers stateless + Redis para estado compartido.
- V2: agregar `prometheus` y `grafana` opcionales como sidecar.
