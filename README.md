# PitWall — F1 Undercut Strategy Engine

> Real-time detection of undercut opportunities during an F1 race, comparing three independent decision paths: a **scipy baseline**, an **XGBoost ML model**, and a **causal structural-equation model**. Backend in FastAPI, frontend in React, data from FastF1 open history.

[![Lint](https://github.com/reginacabralc/f1_strategy_engine/actions/workflows/lint.yml/badge.svg)](.github/workflows/lint.yml)
[![Tests](https://github.com/reginacabralc/f1_strategy_engine/actions/workflows/test.yml/badge.svg)](.github/workflows/test.yml)
[![Build](https://github.com/reginacabralc/f1_strategy_engine/actions/workflows/build.yml/badge.svg)](.github/workflows/build.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

---

## What It Does

When a driver pits during an F1 race, they lose roughly 21 seconds on track. An **undercut** works when the fresh-tyre pace advantage over the next several laps more than recovers that loss — arriving ahead of the rival after the rival also pits. PitWall calculates this window in real time for every consecutive driver pair, and broadcasts alerts via WebSocket to a live React dashboard.

```text
┌──────────────────────┐     ┌───────────────────────────────┐     ┌────────────────┐
│  FastF1 History      │────▶│  Undercut Engine               │────▶│  WebSocket /ws │
│  (replay as live)    │     │  ┌─ ScipyPredictor (default)  │     │  + REST API    │
└──────────────────────┘     │  ├─ XGBoostPredictor          │     └───────┬────────┘
                             │  └─ CausalPredictor (advisory)│             │
                             └───────────────────────────────┘     ┌───────▼────────┐
                                                                    │  React UI      │
                                                                    │  :5173         │
                                                                    └────────────────┘
```

**Three decision paths compared side by side:**

| Path | Method | When it fires | Status |
|------|--------|--------------|--------|
| `scipy` (default) | Quadratic tyre degradation fit + break-even formula | score > 0.4 AND model confidence > 0.5 | ✅ Live |
| `xgboost` | XGBoost regressor on tyre age, circuit, compound, driver offset | Same gate as scipy | ✅ Trained (switch at runtime) |
| `causal` | Structural equation: projected gain vs required gain, traffic-penalised | projected_gain ≥ required_gain | ✅ Advisory endpoint |

---

## Quickstart

**Prerequisites:** Docker Desktop ≥ 4.x, GNU Make, Python 3.12+, ~10 GB free, internet for FastF1 on first run.

```bash
git clone https://github.com/reginacabralc/f1_strategy_engine.git
cd f1_strategy_engine
cp .env.example .env
make demo
```

`make demo` does everything:
1. Starts TimescaleDB in Docker.
2. Creates `.venv` and installs the Python backend.
3. Runs database migrations (`alembic upgrade head`).
4. Ingests the three demo races (Bahrain, Monaco, Hungary 2024).
5. Fits tyre degradation coefficients.
6. Starts the backend (port 8000) and frontend (port 5173) in Docker.
7. Opens the React dashboard in your browser.

> **Note:** PostgreSQL is published on `localhost:5433` (not 5432) to avoid conflicts with a local Postgres. Inside Docker, services use `db:5432`. First run downloads FastF1 data — allow 8–15 minutes.

After demo is running:

```bash
curl http://localhost:8000/health          # {"status":"ok","version":"..."}
curl http://localhost:8000/api/v1/sessions # list of available sessions
```

Full Swagger: <http://localhost:8000/docs>

---

## Architecture

### Data Flow

```text
FastF1 cache (data/cache/)
    │
    │  scripts/ingest_season.py
    ▼
PostgreSQL + TimescaleDB
    │  laps, stints, pit_stops, weather, degradation_coefficients,
    │  pit_loss_estimates, driver_skill_offsets, known_undercuts
    ▼
ReplayFeed  ──asyncio.Queue──▶  UndercutEngine
    │                                │
    │  emits lap_complete events      │  for each consecutive pair:
    │  at replay speed factor         │  evaluate_undercut(attacker, defender, predictor)
    ▼                                ▼
                              alert → WebSocket → React UI
                              alert → alerts table (TimescaleDB)
```

### Module Boundaries

```text
backend/src/pitwall/
  api/         ← FastAPI routes, WebSocket, dependency injection
  engine/      ← RaceState, undercut scoring, backtest, replay manager
  feeds/       ← RaceFeed interface, ReplayFeed, OpenF1Feed stub
  ingest/      ← FastF1 ingestion pipeline
  degradation/ ← Scipy quadratic fit (ScipyPredictor)
  ml/          ← XGBoost training, feature engineering, XGBoostPredictor
  causal/      ← Structural-equation model, DoWhy offline analysis
  pit_loss/    ← Historical pit-loss estimation
  pace_offsets/← Driver skill offset estimation
  db/          ← SQLAlchemy engine, Alembic migrations
  core/        ← Config (env vars), logging, pub-sub topics
```

**Rules:** `engine/` never imports from `api/`. `feeds/` never imports from `engine/`. Communication is one-directional via `asyncio.Queue` and typed topics.

### Component Ownership (Stream Map)

| Stream | Owns |
|--------|------|
| **A — Data & ML** | Ingestion, FastF1 client, scipy fit, XGBoost training/dataset/tuning, pit-loss, driver offsets |
| **B — Engine & API** | Replay engine, undercut scoring, FastAPI + WebSocket, causal graph module |
| **C — Frontend** | React dashboard, all UI components, Vite, TypeScript types |
| **D — Platform** | Docker, CI (GitHub Actions), Makefile, demo orchestration, migrations |

---

## The Three Models

### 1. Scipy Baseline (`ScipyPredictor`)

Fits a quadratic curve per `(circuit_id, compound)` from clean-air historical laps:

```text
lap_time_ms(tyre_age) = a + b·tyre_age + c·tyre_age²
```

The undercut engine projects defender pace (on worn tyres) and attacker fresh pace over 5 laps, computes the cumulative advantage, and scores it:

```text
score = clamp((gain - pit_loss - gap - 500ms) / pit_loss, 0, 1)
alert if score > 0.4 AND min(R²_defender, R²_attacker) > 0.5
```

**Default predictor.** XGBoost improves MAE@k=3 by ~8.5% but doesn't reach the 10% ADR 0009 threshold for promoting it to default.

### 2. XGBoost (`XGBoostPredictor`)

Trained on lap-time delta against a live-safe session reference using features: `tyre_age`, `lap_in_stint_ratio`, `compound`, `circuit_id`, `driver_code`, `team_code`, `track_temp_c`. Target: `lap_time_delta_ms`.

Model artifact: `models/xgb_pace_v1.json`  
Metadata sidecar: `models/xgb_pace_v1.meta.json`  
Switch at runtime (no restart): `POST /api/v1/config/predictor {"predictor": "xgboost"}`

See ADRs [0009](docs/adr/0009-xgboost-vs-scipy-resultados.md) and [0011](docs/adr/0011-temporal-expanding-xgboost-validation.md).

### 3. Causal Structural-Equation Model

Independent of XGBoost and scipy. Uses domain-derived structural equations:

```text
projected_gain  = Σ(k=1..5)[defender_pace(age+k) − attacker_fresh_pace(k)]
                − traffic_penalty  (3000ms if high, 1500ms if medium)
                − cold_tyre_penalty (3000ms lap1, 1000ms lap2)

required_gain   = gap_to_rival + pit_loss + 500ms margin
undercut_viable = projected_gain ≥ required_gain
```

**Performance on 77 observed outcomes (full 2024 season):**

| Metric | Value |
|--------|-------|
| Precision | 74.1% |
| Recall | 100.0% |
| Accuracy | 90.9% |
| TP / FP / FN / TN | 20 / 7 / 0 / 50 |

DoWhy offline analysis confirms correct causal directions. Advisory endpoint: `GET /api/v1/causal/prediction`.

See [`docs/causal_model_performance.md`](docs/causal_model_performance.md) for the full analysis.

---

## Repository Structure

```text
f1_strategy_engine/
├── backend/
│   ├── src/pitwall/         # All Python source (see module map above)
│   └── tests/               # pytest: unit/, integration/, contract/
├── frontend/
│   └── src/
│       ├── api/             # client.ts, types.ts, openapi.ts (generated)
│       ├── components/      # React components (RaceTable, AlertPanel, etc.)
│       └── hooks/           # TanStack Query hooks
├── scripts/                 # CLI tools: ingest, fit, train, compare, causal
├── docs/
│   ├── adr/                 # Architecture Decision Records (0001–0011)
│   ├── interfaces/          # openapi_v1.yaml (source of truth for types)
│   ├── quanta/              # Concept explanations
│   ├── architecture.md      # Full system architecture
│   ├── walkthrough.md       # Step-by-step tutorial
│   ├── causal_model_performance.md  # Causal model evaluation
│   └── causal_dag.dot       # Causal graph in DOT format
├── data/
│   ├── cache/               # FastF1 HTTP cache (gitignored, ~2–5 GB)
│   ├── causal/              # Causal dataset parquet (gitignored, regenerable)
│   └── reference/           # ml_race_manifest.yaml
├── models/                  # XGBoost artifacts (gitignored, regenerable)
├── reports/                 # Backtest reports (gitignored, regenerable)
├── docker/                  # Dockerfiles (backend, frontend)
├── docker-compose.yaml      # db, migrate, backend, frontend
├── Makefile                 # All dev commands
└── .env.example             # Environment variable template
```

---

## Installation & Setup

### Environment Variables

```bash
cp .env.example .env
```

Key variables (all have working defaults):

| Variable | Default | Purpose |
|----------|---------|---------|
| `DATABASE_URL` | `postgresql+psycopg://pitwall:pitwall@localhost:5433/pitwall` | Host-side DB URL for scripts |
| `PACE_PREDICTOR` | `scipy` | Active predictor: `scipy` or `xgboost` |
| `XGB_MODEL_PATH` | `models/xgb_pace_v1.json` | XGBoost artifact path |
| `POSTGRES_HOST_PORT` | `5433` | Avoid conflict with local Postgres on 5432 |
| `FASTF1_CACHE_DIR` | `data/cache` | FastF1 download cache |

### Local Development (without Docker for backend)

```bash
# Install Python backend
make install

# Start only the database
make db-up

# Run migrations
make migrate

# Start backend with hot-reload
make serve-api

# Frontend (in a separate terminal, requires Node + pnpm)
cd frontend && pnpm install && pnpm dev
```

### Full Docker Stack

```bash
make up       # start all services (db + backend + frontend)
make down     # stop all services
make down-v   # stop and delete database volume
make logs     # follow all service logs
make ps       # show container status
```

### Rebuilding after code changes

When you edit code under `backend/src/` or `frontend/src/`, the running container
holds the old code (Docker images are immutable). Use these targets to refresh:

```bash
make rebuild-backend    # rebuild + restart backend container, waits for /health
make rebuild-frontend   # rebuild + restart frontend container
make rebuild            # both at once
```

### Without Node.js installed locally

The frontend stack (Vitest, ESLint, Playwright, openapi-typescript) needs Node 22 + pnpm.
**You do not need to install them on your host machine.** As long as the frontend container
is running (`make up`), the following targets transparently execute inside it:

```bash
make test-frontend       # Vitest — runs in container if no local Node
make lint-frontend       # ESLint — runs in container if no local Node
make test-e2e            # Playwright — runs in container if no local Node
make generate-api-types  # openapi-typescript — runs in container if no local Node
```

The Makefile picks the best available runner in this order:

1. `frontend/node_modules/.bin/<tool>` if installed locally
2. `pnpm` / `corepack pnpm` / `npx pnpm` on host PATH
3. `docker compose exec frontend pnpm <command>` if the container is running
4. Otherwise: clear error message instructing you to run `make up` first

---

## Running the Project

### Demo (recommended first run)

```bash
make demo
```

Opens React dashboard at <http://localhost:5173>. Swagger at <http://localhost:8000/docs>.

### Start a Replay

```bash
# Via API
curl -X POST http://localhost:8000/api/v1/replay/start \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"monaco_2024_R","speed_factor":30}'

# Via WebSocket client (watch live events)
.venv/bin/python scripts/ws_demo_client.py ws://localhost:8000/ws/v1/live

# Stop
curl -X POST http://localhost:8000/api/v1/replay/stop
```

Demo race IDs: `bahrain_2024_R`, `monaco_2024_R`, `hungary_2024_R`.

### Load Another Race

```bash
make ingest YEAR=2024 ROUND=13   # Hungarian GP
```

### Switch Predictor at Runtime

```bash
# Switch to XGBoost (requires trained model at models/xgb_pace_v1.json)
curl -X POST http://localhost:8000/api/v1/config/predictor \
  -H 'Content-Type: application/json' \
  -d '{"predictor": "xgboost"}'

# Switch back to scipy
curl -X POST http://localhost:8000/api/v1/config/predictor \
  -H 'Content-Type: application/json' \
  -d '{"predictor": "scipy"}'
```

Or use the **Pace Predictor** toggle in the React dashboard sidebar.

### Query the Causal Model

```bash
# Advisory prediction (does not affect live alerts)
curl "http://localhost:8000/api/v1/causal/prediction?session_id=bahrain_2024_R&circuit_id=bahrain&lap_number=30&attacker=NOR&attacker_compound=MEDIUM&attacker_tyre_age=15&defender=VER&defender_compound=HARD&defender_tyre_age=25&gap_ms=5000&pit_loss_ms=21000"

# CLI smoke test
PYTHONPATH=backend/src .venv/bin/python scripts/predict_causal_undercut.py
```

---

## ML Pipeline

### Reproduce the Scipy Baseline

```bash
make ingest-demo           # load Bahrain, Monaco, Hungary 2024
make fit-degradation       # fit quadratic curves
make fit-pit-loss          # pit-loss estimates by (circuit, team)
make fit-driver-offsets    # driver skill offsets
```

### Train XGBoost

```bash
make build-xgb-dataset SPLIT_STRATEGY=temporal_expanding
make validate-xgb-dataset
make tune-xgb              # Optuna hyperparameter search
make train-xgb
make validate-xgb-model
make plot-xgb-diagnostics  # saves to reports/figures/
```

### Compare Scipy vs XGBoost

```bash
make compare-predictors    # saves to reports/ml/scipy_xgboost_backtest_report.json
```

Results documented in [`docs/adr/0009-xgboost-vs-scipy-resultados.md`](docs/adr/0009-xgboost-vs-scipy-resultados.md).

### Causal Model

```bash
# Rebuild causal dataset from DB (after ingesting sessions)
make reconstruct-race-gaps
make build-causal-dataset

# Run DoWhy offline analysis (pooled + stratified by circuit)
make run-causal-dowhy

# Compare causal vs scipy engine decisions
make compare-causal-engines
```

---

## Tests

```bash
make test              # backend unit tests + frontend Vitest
make test-backend      # pytest backend/tests/unit only  (no Node needed)
make test-frontend     # Vitest — uses Docker container if no local Node
make test-e2e-install  # install Playwright Firefox browser (once)
make test-e2e          # Playwright happy-path e2e test
make lint              # ruff + mypy + eslint
```

Current state: **383 backend unit tests pass, 58 frontend Vitest tests pass**.
The frontend tests run inside the running `frontend` container automatically
when host Node is not available — no extra setup needed.

---

## Regenerating Frontend Types

When `docs/interfaces/openapi_v1.yaml` changes (new endpoint or schema):

```bash
make generate-api-types   # requires Node + pnpm in PATH
```

This runs `openapi-typescript` and regenerates `frontend/src/api/openapi.ts`. Then add named re-exports to `frontend/src/api/types.ts` and typed client functions to `frontend/src/api/client.ts`.

The contract test `backend/tests/contract/test_openapi_export.py` checks that the live FastAPI spec matches the YAML spec. Run it with `make test-backend`.

---

## Expected Outputs

| Command | Output |
|---------|--------|
| `make demo` | React dashboard at :5173, Swagger at :8000/docs |
| `GET /api/v1/sessions` | JSON list of available sessions |
| WebSocket `/ws/v1/live` | `snapshot` and `alert` messages every lap |
| `make compare-predictors` | `reports/ml/scipy_xgboost_backtest_report.json` |
| `make run-causal-dowhy` | Pooled + stratified DoWhy effects printed to stdout |
| `make compare-causal-engines` | `data/causal/engine_disagreements.csv` |
| `GET /api/v1/causal/prediction` | `CausalPredictionOut` with counterfactuals |

---

## Troubleshooting

See [`infra/runbook.md`](infra/runbook.md) for a full diagnosis guide. Quick fixes:

| Problem | Fix |
|---------|-----|
| `Cannot connect to db` | `make db-up && make db-wait` |
| `FastF1 cache permission denied` | `chmod -R 777 data/cache` |
| `XGBoost model not found` | Use `PACE_PREDICTOR=scipy` or run `make train-xgb` |
| `WebSocket disconnects immediately` | Check backend logs: `make logs` |
| `Playwright browser missing` | `make test-e2e-install` |
| `Backtest precision = 0` | Both predictors may have F1=0 on 3-session demo; see ADR 0009 |
| `data/causal/*.parquet not found` | `make build-causal-dataset` (requires DB with sessions) |
| Port 5432 conflict | Set `POSTGRES_HOST_PORT=5433` in `.env` (already the default) |
| `/api/v1/causal/prediction returns 404` | Backend image is stale. Run `make rebuild-backend` |
| `make test-frontend: command not found: npx` | Run `make up` first; the target then uses the container automatically |
| `make lint-frontend: command not found: npx` | Same as above — `make up` first |
| `make generate-api-types` fails | Same as above — `make up` first |
| Backend code changed but API behaviour didn't | Container holds old code. Run `make rebuild-backend` |
| Frontend code changed but UI didn't update | The dev container has hot-reload; if the file changed but UI didn't update, check `make logs` for build errors. For a full refresh: `make rebuild-frontend` |

---

## Known Limitations

- **Replay-first, not live:** V1 uses historical FastF1 data replayed at configurable speed. Real-time OpenF1 ingestion is stubbed (`feeds/openf1.py`) and deferred to V2.
- **XGBoost trained on 3 demo sessions:** The model generalises poorly — MAE@k=3 improves only ~8.5% over scipy on 3 sessions. Performance improves significantly with a full season (use `make ingest-ml-races`).
- **Causal model uses proxy labels:** 99.6% of `undercut_viable` labels in the causal dataset are derived from structural equations, not observed pit outcomes. DoWhy is explaining the equation's own outputs.
- **No auth/users:** Single-user, local deployment only in V1.
- **No dirty-air/DRS modelling:** Clean-air lap times only. Traffic penalty is a domain constant (3 s / 1.5 s), not learned.
- **No rain transitions:** Rain track status suppresses alerts with `UNDERCUT_DISABLED_RAIN`; wet-dry transitions are not modelled.

---

## What Was Integrated (2026-05-16)

This repo was built by four streams working in parallel. The integration pass connected:

1. **Frontend ↔ causal endpoint:** `openapi.ts` updated with `CausalPredictionOut` and `CausalCounterfactualOut`. Typed `getCausalPrediction()` client function added to `client.ts` and `types.ts`. The frontend can now call the causal advisory endpoint without raw `fetch`.

2. **`reports/` directory created:** `compare_predictors.py` writes to `reports/ml/scipy_xgboost_backtest_report.json`. The directory now exists with `.gitkeep` so `make compare-predictors` doesn't fail on a fresh clone.

3. **`make generate-api-types` added:** Single command to regenerate `openapi.ts` from `docs/interfaces/openapi_v1.yaml` after schema changes. Closes the loop between backend API changes and frontend types.

4. **`.gitignore` documented:** `data/causal/` gitignore entry now explains the force-commit situation and how to regenerate the files after a fresh clone.

No model logic, algorithm, or frontend design was changed.

---

## Documentation Index

| Document | Contents |
|----------|----------|
| [`docs/architecture.md`](docs/architecture.md) | Full system architecture, component map, sequence diagrams |
| [`docs/walkthrough.md`](docs/walkthrough.md) | Step-by-step tutorial from clone to running replay |
| [`docs/causal_model_performance.md`](docs/causal_model_performance.md) | Causal model math, metrics, comparison |
| [`docs/adr/`](docs/adr/) | 11 Architecture Decision Records |
| [`docs/interfaces/openapi_v1.yaml`](docs/interfaces/openapi_v1.yaml) | API contract (source of truth for frontend types) |
| [`docs/causal_dag.dot`](docs/causal_dag.dot) | Causal graph in DOT format (render with Graphviz) |
| [`docs/quanta/`](docs/quanta/) | Short explanations of key concepts |
| [`infra/runbook.md`](infra/runbook.md) | Troubleshooting and ops runbook |

---

## Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12, FastAPI, uvicorn, asyncio |
| Data processing | Polars (pipelines), scipy (curve fit), XGBoost, DoWhy |
| Database | PostgreSQL 15 + TimescaleDB |
| Frontend | React 18, Vite, TypeScript, TanStack Query, Tailwind CSS, Recharts |
| Infra | docker-compose, GitHub Actions CI |
| Data source | [FastF1](https://docs.fastf1.dev/), [OpenF1](https://openf1.org) (future live) |

## License

MIT — see [`LICENSE`](LICENSE).
