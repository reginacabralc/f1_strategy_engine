# Infra

Documentación operativa del sistema. **No** es Infrastructure as Code en V1 — solo documentación.

## Contenido

| Archivo | Propósito |
|---------|-----------|
| [`docker-compose-architecture.md`](docker-compose-architecture.md) | Diagrama y descripción de los servicios en docker-compose, dependencias, healthchecks. |
| [`runbook.md`](runbook.md) | Cómo diagnosticar y resolver problemas comunes en operación. |

## Por qué no IaC en V1

El profesor solo exige `docker-compose` local. Terraform / Pulumi / Ansible / Kubernetes serían overkill para 2 semanas. En V2, si llegamos a deploy en cloud, agregamos `infra/terraform/`.

## Servicios

Estado actual de `docker-compose.yaml`:

```text
docker-compose
├── db          (timescale/timescaledb:2.17.2-pg15)   :5432
├── migrate     (one-shot, alembic upgrade head)
├── backend     (Python + FastAPI)                     :8000
└── frontend    (React + Vite dev server)              :5173
```

## Variables de entorno

Ver `.env.example` en raíz. Las críticas:

| Var | Default | Quién la usa |
|-----|---------|--------------|
| `DATABASE_URL` | `postgresql+psycopg://pitwall:pitwall@localhost:5432/pitwall` local / `postgresql+psycopg://pitwall:pitwall@db:5432/pitwall` compose | backend, migrate, scripts |
| `LOG_LEVEL` | `INFO` | backend |
| `PACE_PREDICTOR` | `scipy` | backend |
| `REPLAY_DEFAULT_SESSION` | `monaco_2024_R` | backend |
| `REPLAY_DEFAULT_SPEED` | `30` | backend |
| `FASTF1_CACHE_DIR` | `data/cache` | scripts ingesta |
| `VITE_API_URL` | `http://localhost:8000` | frontend |
| `VITE_WS_URL` | `ws://localhost:8000/ws/v1/live` | frontend |

## Persistencia

- Volumen `pgdata` (Docker) → datos de Postgres.
- Bind mount `./data/cache` → cache de FastF1 (varios GB; gitignored).
- Bind mount `./models` → modelos serializados (XGBoost JSON; gitignored).

Para resetear todo:

```bash
docker compose down -v   # -v borra volúmenes
rm -rf data/cache models/*.json
```

## Health checks

- `db`: `pg_isready -U pitwall`
- `backend`: `GET /health` (200 = vivo)
- `backend ready`: `GET /ready` (200 = DB conectada y modelo cargado)

## Logs

- Logs JSON en stdout de cada contenedor.
- `docker compose logs -f backend` para seguir.
- `docker compose logs --since=10m | jq 'select(.level=="ERROR")'` para filtrar.
