# CLAUDE.md

Guía para Claude Code y agentes que asisten en este repositorio. **Léelo antes de proponer cambios.**

## Project Overview

PitWall es un motor en tiempo real que detecta oportunidades de *undercut* en carreras de F1 usando datos históricos de FastF1 reproducidos como si fueran live. Calcula la ventana de undercut para cada par de pilotos consecutivos, emite alertas vía WebSocket, y muestra todo en un dashboard React.

Detalle completo: [`docs/architecture.md`](docs/architecture.md)
Plan maestro: [`.claude/plans/00-master-plan.md`](.claude/plans/00-master-plan.md)

## Stack

- **Lenguaje backend**: Python 3.12
- **Lenguaje frontend**: TypeScript 5.x
- **Backend**: FastAPI + uvicorn + WebSockets nativos + asyncio
- **Datos**: Polars (no pandas), scipy, xgboost
- **DB**: PostgreSQL 15 + TimescaleDB
- **ORM/migrations**: SQLModel + Alembic
- **Frontend**: React + Vite + TanStack Query + Tailwind + Recharts
- **Tests**: pytest + hypothesis + vitest + Playwright (1 e2e)
- **Lint/format**: ruff (Python), prettier + eslint (TS)
- **Infra local**: docker-compose
- **CI**: GitHub Actions

## Repo Layout

```
f1_strategy_engine/
├── CLAUDE.md, AGENTS.md, README.md
├── docker-compose.yaml, Makefile
├── .claude/plans/                 # plan maestro y planes por stream
├── .github/workflows/             # CI: lint, test, build
├── docker/                        # Dockerfiles + postgres init
├── docs/                          # arquitectura, walkthrough, ADRs, quanta, interfaces
├── backend/src/pitwall/           # código backend (api, engine, ml, ingest, db, feeds)
├── frontend/                      # React app
├── notebooks/                     # exploración + backtest + train XGBoost
├── scripts/                       # CLI: ingest_season, fit_degradation, train_xgb, seed_demo
├── infra/                         # documentación de infra (no IaC en V1)
└── data/                          # cache FastF1 y dumps de seed (gitignored)
```

## Common Commands

```bash
make up          # docker compose up -d (db + backend + frontend + migrate)
make down        # docker compose down
make seed        # cargar 1 carrera de demo (Mónaco 2024)
make migrate     # alembic upgrade head
make replay      # arrancar replay de la sesión default
make train-xgb   # reentrenar XGBoost y persistir modelo
make test        # backend pytest + frontend vitest
make lint        # ruff + eslint + prettier check
make demo        # up + seed + abrir browser (target principal)
```

## Key Architecture Concepts

1. **Replay-first.** En V1 no consumimos OpenF1 en vivo. Un `ReplayFeed` lee del histórico y emite eventos al motor con el mismo formato que tendría OpenF1. Esto se decide así para tener desarrollo reproducible y libre del calendario F1. La interfaz `RaceFeed` deja la puerta abierta para `OpenF1Feed` en V2.

2. **`PacePredictor` interface.** El motor de undercut consume una abstracción `PacePredictor` con dos implementaciones:
   - `ScipyPredictor`: cuadrática ajustada por (circuito × compuesto) — baseline.
   - `XGBoostPredictor`: modelo XGBoost serializado, con features numéricas + categóricas — entregable de ML del MVP.
   - Switch en runtime con env var `PACE_PREDICTOR=scipy|xgb`.

3. **In-process pub-sub.** No hay Kafka, Redis Streams, ni Celery. Replay → Motor → WebSocket pasa por `asyncio.Queue`. Si el cuello de botella aparece, ya pensaremos en V2.

4. **Heurística antes que ML.** Primero construimos el motor con el predictor scipy. XGBoost se entrena en la última etapa del sprint (E10) y se enchufa detrás de la misma interfaz. La heurística no es un draft — es un baseline honesto.

5. **TimescaleDB para `laps`, `alerts`, `live_lap_events`** — el resto son tablas Postgres normales. La razón es higiene de queries (`time_bucket`), no escala.

## Coding Conventions

- **Type hints obligatorios** en todo Python público. Verificado por mypy en CI.
- **Funciones con matemática llevan docstring corto** explicando inputs, output y unidad (ms/s).
- **Polars sobre pandas** — usamos LazyFrame para pipelines de ingesta.
- **Async por defecto** en backend, salvo en scripts CLI.
- **Sin "utils.py"**. Todo módulo tiene un nombre que dice qué hace.
- **Imports absolutos** (`from pitwall.engine.undercut import ...`).
- **No comentamos lo obvio**. Un comentario solo aparece si explica un POR QUÉ no derivable del código.
- **Tests viven al lado del código** que prueban: `backend/tests/unit/engine/test_undercut.py` para `backend/src/pitwall/engine/undercut.py`.

## Testing

- `make test` corre backend + frontend.
- Backend: pytest + hypothesis. Tests de integración usan `testcontainers` para Postgres.
- Frontend: vitest + React Testing Library + 1 happy-path Playwright.
- **Replay-as-test**: el CI corre el `ReplayFeed` sobre Mónaco 2024 a 1000× y verifica métricas mínimas (precision/recall) en backtest.

## What NOT to do

- **No introducir** Kafka, Redis, Celery, ni cualquier broker de mensajes en V1.
- **No implementar** LSTM ni redes neuronales en V1. Si hay duda, ver ADR 0004 y 0009.
- **No commitear** `data/cache/`, modelos `.json`/`.bin` grandes, ni `.env`.
- **No hacer** polling agresivo a OpenF1 en V1 (no estamos consumiendo live).
- **No mezclar** vueltas de la misma carrera entre train y test del XGBoost — split por `session_id`.
- **No tocar** `docs/interfaces/*` sin avisar al equipo (ver `AGENTS.md`).

## Where to find

- **Plan maestro**: [`.claude/plans/00-master-plan.md`](.claude/plans/00-master-plan.md)
- **Planes por stream**: [`.claude/plans/stream-{a,b,c,d}.md`](.claude/plans/)
- **ADRs**: [`docs/adr/`](docs/adr/)
- **Quanta** (explicaciones cortas para profesor): [`docs/quanta/`](docs/quanta/)
- **Interfaces compartidas**: [`docs/interfaces/`](docs/interfaces/)
- **Walkthrough end-to-end**: [`docs/walkthrough.md`](docs/walkthrough.md)
- **Progreso**: [`docs/progress.md`](docs/progress.md)

## Honest reminders

- El cuello de botella real no es el código del motor: es la **calidad de los datos** y la **curaduría de undercuts conocidos** para backtest. Cualquier cambio que no mejore una de las dos tiene baja prioridad.
- Si XGBoost no mejora claramente al baseline scipy, **no es fracaso**: es información. Lo documentamos honestamente en ADR 0009 y entregamos ambos modelos.
- 2 semanas, 4 personas. Cada PR que tarde más de 1 día sin merge es deuda.
