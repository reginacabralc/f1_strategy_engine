PYTHON ?= .venv/bin/python
PIP ?= $(PYTHON) -m pip
PYTHON_BOOTSTRAP ?= $(shell if command -v python3.12 >/dev/null 2>&1; then echo python3.12; else echo python3; fi)
PNPM ?= $(shell if command -v pnpm >/dev/null 2>&1; then echo pnpm; elif command -v corepack >/dev/null 2>&1; then echo "corepack pnpm"; elif command -v npx >/dev/null 2>&1; then echo "npx -y pnpm@9.15.9"; else echo ""; fi)
# Frontend container service name (must match docker-compose.yaml).
FRONTEND_SERVICE ?= frontend
# True if Node tooling is available on the host (pnpm, corepack, or npx).
HOST_HAS_NODE := $(shell if [ -n "$(PNPM)" ]; then echo 1; else echo 0; fi)
# True if the frontend container is currently running.
FRONTEND_CONTAINER_UP := $(shell docker compose ps --status running --services 2>/dev/null | grep -qx "$(FRONTEND_SERVICE)" && echo 1 || echo 0)

.PHONY: install db-up db-wait db-down up down down-v logs ps migrate \
        rebuild rebuild-backend rebuild-frontend \
        ingest ingest-monaco ingest-demo validate-demo seed \
        ingest-ml-races validate-ml-races \
        fit-degradation fit-degradation-demo validate-degradation report-degradation \
        fit-pit-loss validate-pit-loss generate-api-types \
        fit-driver-offsets validate-driver-offsets \
        build-xgb-dataset validate-xgb-dataset diagnose-xgb-shift \
        evaluate-xgb-baselines run-xgb-ablations \
        tune-xgb train-xgb validate-xgb-model \
        plot-xgb-diagnostics compare-predictors \
        audit-causal-inputs reconstruct-race-gaps derive-known-undercuts \
        import-curated-known-undercuts build-causal-dataset run-causal-dowhy \
        compare-causal-engines prepare-causal-extended-data \
        replay test test-backend test-frontend test-e2e test-e2e-install \
        lint lint-backend lint-frontend \
        pre-commit \
        demo demo-api serve-api api-wait

install: .venv/.installed

.venv/.installed: backend/pyproject.toml
	$(PYTHON_BOOTSTRAP) -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 'Python 3.12+ is required. Install python3.12 or run make with PYTHON_BOOTSTRAP=/path/to/python3.12')"
	$(PYTHON_BOOTSTRAP) -m venv .venv
	$(PIP) install -U pip
	$(PIP) install -e 'backend[dev]'
	touch .venv/.installed

db-up:
	docker compose up -d db

db-wait: db-up
	@echo "Waiting for Postgres to be ready..."
	@until docker compose exec -T db pg_isready -U pitwall -d pitwall >/dev/null 2>&1; do \
		sleep 1; \
	done
	@echo "Postgres is ready."

db-down:
	docker compose down

## Compose includes db, migrate, backend, and frontend.
up:
	docker compose up -d

down:
	docker compose down

down-v:
	docker compose down -v

logs:
	docker compose logs -f

ps:
	docker compose ps

## rebuild-backend: rebuild the backend image and restart the container.
## Use after editing files under backend/src/ so the live API reflects the change.
rebuild-backend:
	docker compose build backend
	docker compose up -d backend
	@echo "Waiting for API to be ready..."
	@until curl -fsS http://localhost:8000/health >/dev/null 2>&1; do sleep 1; done
	@echo "API is ready."
	@echo "Backend rebuilt and ready at http://localhost:8000"

## rebuild-frontend: rebuild the frontend image and restart the container.
## Use after editing files under frontend/src/ when running via Docker.
rebuild-frontend:
	docker compose build frontend
	docker compose up -d frontend
	@echo "Frontend rebuilt and ready at http://localhost:5173"

## rebuild: rebuild both backend and frontend images.
rebuild: rebuild-backend rebuild-frontend

migrate: install db-wait
	cd backend && PYTHONPATH=src ../$(PYTHON) -m alembic -c alembic.ini upgrade head

ingest-monaco: install db-wait
	PYTHONPATH=backend/src $(PYTHON) scripts/ingest_season.py --year 2024 --round 8 --session R --write-db

## YEAR ?= 2024  ROUND ?= 8  SESSION_CODE ?= R
ingest: install db-wait
	PYTHONPATH=backend/src $(PYTHON) scripts/ingest_season.py --year $(or $(YEAR),2024) --round $(or $(ROUND),8) --session $(or $(SESSION_CODE),R) --write-db

ingest-demo: install db-wait
	PYTHONPATH=backend/src $(PYTHON) scripts/ingest_season.py --year 2024 --round 1 --session R --write-db
	PYTHONPATH=backend/src $(PYTHON) scripts/ingest_season.py --year 2024 --round 8 --session R --write-db
	PYTHONPATH=backend/src $(PYTHON) scripts/ingest_season.py --year 2024 --round 13 --session R --write-db

validate-demo: install db-wait
	PYTHONPATH=backend/src $(PYTHON) scripts/validate_demo_ingest.py

seed: ingest-demo

validate-ml-races: install
	PYTHONPATH=backend/src $(PYTHON) scripts/validate_race_manifest.py

ingest-ml-races: install db-wait
	PYTHONPATH=backend/src $(PYTHON) scripts/ingest_race_manifest.py --continue-on-error

fit-degradation: install db-wait
	PYTHONPATH=backend/src $(PYTHON) scripts/fit_degradation.py --manifest data/reference/ml_race_manifest.yaml

fit-degradation-demo: install db-wait
	PYTHONPATH=backend/src $(PYTHON) scripts/fit_degradation.py --all-demo

validate-degradation: install db-wait
	PYTHONPATH=backend/src $(PYTHON) scripts/validate_degradation.py

report-degradation: validate-degradation

fit-pit-loss: install db-wait
	PYTHONPATH=backend/src $(PYTHON) scripts/fit_pit_loss.py

validate-pit-loss: install db-wait
	PYTHONPATH=backend/src $(PYTHON) scripts/validate_pit_loss.py

fit-driver-offsets: install db-wait
	PYTHONPATH=backend/src $(PYTHON) scripts/fit_driver_offsets.py

validate-driver-offsets: install db-wait
	PYTHONPATH=backend/src $(PYTHON) scripts/validate_driver_offsets.py

audit-causal-inputs: install
	PYTHONPATH=backend/src $(PYTHON) scripts/audit_causal_inputs.py

reconstruct-race-gaps: install
	PYTHONPATH=backend/src $(PYTHON) scripts/reconstruct_race_gaps.py

derive-known-undercuts: install
	PYTHONPATH=backend/src $(PYTHON) scripts/derive_known_undercuts.py

import-curated-known-undercuts: install
	PYTHONPATH=backend/src $(PYTHON) scripts/import_curated_known_undercuts.py

build-causal-dataset: install
	PYTHONPATH=backend/src $(PYTHON) scripts/build_causal_dataset.py

run-causal-dowhy: install
	MPLCONFIGDIR=/tmp/pitwall-matplotlib PYTHONPATH=backend/src $(PYTHON) scripts/run_causal_dowhy.py

compare-causal-engines: install
	PYTHONPATH=backend/src $(PYTHON) scripts/compare_causal_engines.py

prepare-causal-extended-data: install
	PYTHONPATH=backend/src $(PYTHON) scripts/prepare_causal_extended_data.py

build-xgb-dataset: install db-wait
	PYTHONPATH=backend/src $(PYTHON) scripts/build_xgb_dataset.py --split-strategy $(or $(SPLIT_STRATEGY),temporal_expanding) --target-strategy $(or $(TARGET_STRATEGY),lap_time_delta)

validate-xgb-dataset: install
	PYTHONPATH=backend/src $(PYTHON) scripts/validate_xgb_dataset.py

diagnose-xgb-shift: install db-wait
	PYTHONPATH=backend/src $(PYTHON) scripts/diagnose_xgb_dataset_shift.py

evaluate-xgb-baselines: install
	PYTHONPATH=backend/src $(PYTHON) scripts/evaluate_xgb_baselines.py

run-xgb-ablations: install
	PYTHONPATH=backend/src $(PYTHON) scripts/run_xgb_ablation.py

train-xgb: install
	PYTHONPATH=backend/src $(PYTHON) scripts/train_xgb.py --feature-set $(or $(FEATURE_SET),full)

validate-xgb-model: install
	PYTHONPATH=backend/src $(PYTHON) scripts/validate_xgb_model.py

tune-xgb: install
	PYTHONPATH=backend/src $(PYTHON) scripts/tune_xgb.py --feature-set $(or $(FEATURE_SET),full)

plot-xgb-diagnostics: install
	PYTHONPATH=backend/src $(PYTHON) scripts/plot_xgb_diagnostics.py

compare-predictors: install db-wait
	PYTHONPATH=backend/src $(PYTHON) scripts/compare_predictors.py

test: test-backend test-frontend

test-backend: install
	MPLCONFIGDIR=/tmp/pitwall-matplotlib PYTHONPATH=backend/src $(PYTHON) -m pytest backend/tests/unit -q

## test-frontend: runs Vitest. Uses host Node if pnpm is on PATH;
## otherwise runs inside the live `frontend` Docker container.
## If neither is available, prints how to start the frontend container.
test-frontend:
	@if [ -x frontend/node_modules/.bin/vitest ]; then \
		cd frontend && ./node_modules/.bin/vitest run; \
	elif [ "$(HOST_HAS_NODE)" = "1" ]; then \
		cd frontend && $(PNPM) install --frozen-lockfile && $(PNPM) test; \
	elif [ "$(FRONTEND_CONTAINER_UP)" = "1" ]; then \
		echo "Running Vitest inside frontend container..."; \
		docker compose exec -T $(FRONTEND_SERVICE) pnpm test; \
	else \
		echo "ERROR: no host Node and frontend container is not running."; \
		echo "Fix: run 'make up' (starts the frontend container) and try again,"; \
		echo "     or install Node 22 + pnpm and re-run 'make test-frontend'."; \
		exit 1; \
	fi

test-e2e-install:
	@if [ -x frontend/node_modules/.bin/playwright ]; then \
		cd frontend && ./node_modules/.bin/playwright install firefox; \
	elif [ "$(HOST_HAS_NODE)" = "1" ]; then \
		cd frontend && $(PNPM) install --frozen-lockfile && $(PNPM) exec playwright install firefox; \
	elif [ "$(FRONTEND_CONTAINER_UP)" = "1" ]; then \
		docker compose exec -T $(FRONTEND_SERVICE) pnpm exec playwright install firefox; \
	else \
		echo "ERROR: no host Node and frontend container is not running. Run 'make up' first."; \
		exit 1; \
	fi

test-e2e:
	@if [ -x frontend/node_modules/.bin/playwright ]; then \
		cd frontend && ./node_modules/.bin/playwright test; \
	elif [ "$(HOST_HAS_NODE)" = "1" ]; then \
		cd frontend && $(PNPM) install --frozen-lockfile && $(PNPM) exec playwright test; \
	elif [ "$(FRONTEND_CONTAINER_UP)" = "1" ]; then \
		docker compose exec -T $(FRONTEND_SERVICE) pnpm exec playwright test; \
	else \
		echo "ERROR: no host Node and frontend container is not running. Run 'make up' first."; \
		exit 1; \
	fi

lint: lint-backend lint-frontend

lint-backend: install
	PYTHONPATH=backend/src $(PYTHON) -m ruff check backend
	PYTHONPATH=backend/src $(PYTHON) -m mypy backend/src backend/tests

lint-frontend:
	@if [ -x frontend/node_modules/.bin/eslint ]; then \
		cd frontend && ./node_modules/.bin/eslint src --ext .ts,.tsx --report-unused-disable-directives --max-warnings 0; \
	elif [ "$(HOST_HAS_NODE)" = "1" ]; then \
		cd frontend && $(PNPM) install --frozen-lockfile && $(PNPM) lint; \
	elif [ "$(FRONTEND_CONTAINER_UP)" = "1" ]; then \
		echo "Running eslint inside frontend container..."; \
		docker compose exec -T $(FRONTEND_SERVICE) pnpm lint; \
	else \
		echo "ERROR: no host Node and frontend container is not running. Run 'make up' first."; \
		exit 1; \
	fi

pre-commit: install
	$(PYTHON) -m pre_commit run --all-files

## generate-api-types: Regenerate frontend/src/api/openapi.ts from docs/interfaces/openapi_v1.yaml.
## Run this whenever openapi_v1.yaml changes.
## Uses host Node if available, otherwise runs inside the live frontend container.
generate-api-types:
	@if [ "$(HOST_HAS_NODE)" = "1" ]; then \
		cd frontend && $(PNPM) install --frozen-lockfile && $(PNPM) generate:api; \
	elif [ "$(FRONTEND_CONTAINER_UP)" = "1" ]; then \
		echo "Generating openapi.ts inside frontend container..."; \
		docker compose exec -T $(FRONTEND_SERVICE) pnpm generate:api; \
	else \
		echo "ERROR: no host Node and frontend container is not running. Run 'make up' first."; \
		exit 1; \
	fi

serve-api: install
	PYTHONPATH=backend/src $(PYTHON) -m uvicorn pitwall.api.main:app --reload --port 8000

api-wait:
	@echo "Waiting for API to be ready..."
	@until curl -fsS http://localhost:8000/health >/dev/null 2>&1; do \
		sleep 1; \
	done
	@echo "API is ready."

## SPEED ?= 30  (replay speed multiplier)
## SESSION ?= monaco_2024_R
replay: install db-wait
	PYTHONPATH=backend/src $(PYTHON) scripts/ingest_season.py --year 2024 --round 8 --session R --write-db
	@echo "Replay via API: POST /api/v1/replay/start  (Stream B Day 3 target)"

## demo-api: DB up (Docker), migrations and seed via local venv, then API up.
## Opens Swagger automatically. Requires: cp .env.example .env first.
demo-api: db-up migrate seed fit-degradation-demo
	docker compose up -d backend
	@echo "Waiting for API to be ready..."
	@until curl -fsS http://localhost:8000/health >/dev/null 2>&1; do sleep 1; done
	@echo "API is ready."
	$(PYTHON) -m webbrowser -t http://localhost:8000/docs
	@echo "Demo API is running at: http://localhost:8000/docs"

## demo: full local demo stack (DB + migrate + seeded data + backend + frontend).
## Opens the React dashboard and leaves Swagger available at :8000/docs.
demo: db-up migrate seed fit-degradation-demo
	docker compose up -d backend frontend
	@echo "Waiting for API to be ready..."
	@until curl -fsS http://localhost:8000/health >/dev/null 2>&1; do sleep 1; done
	@echo "API is ready."
	$(PYTHON) -m webbrowser -t http://localhost:5173
	@echo "Demo frontend is running at: http://localhost:5173"
	@echo "Swagger is available at: http://localhost:8000/docs"
