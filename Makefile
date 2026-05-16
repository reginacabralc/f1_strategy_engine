PYTHON ?= .venv/bin/python
PIP ?= $(PYTHON) -m pip
PYTHON_BOOTSTRAP ?= $(shell if command -v python3.12 >/dev/null 2>&1; then echo python3.12; else echo python3; fi)
PNPM ?= $(shell if command -v pnpm >/dev/null 2>&1; then echo pnpm; elif command -v corepack >/dev/null 2>&1; then echo "corepack pnpm"; else echo "npx -y pnpm@9.15.9"; fi)

.PHONY: install db-up db-wait db-down up down down-v logs ps migrate \
        ingest ingest-monaco ingest-demo validate-demo seed \
        ingest-ml-races validate-ml-races \
        fit-degradation fit-degradation-demo validate-degradation report-degradation \
        fit-pit-loss validate-pit-loss \
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

reconstruct-race-gaps: install db-wait
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
	cd backend && ../$(PYTHON) -m pytest tests/unit -q

test-frontend:
	cd frontend && if [ -x ./node_modules/.bin/vitest ]; then \
		./node_modules/.bin/vitest run; \
	else \
		$(PNPM) install --frozen-lockfile && $(PNPM) test; \
	fi

test-e2e-install:
	cd frontend && if [ -x ./node_modules/.bin/playwright ]; then \
		./node_modules/.bin/playwright install firefox; \
	else \
		$(PNPM) install --frozen-lockfile && $(PNPM) exec playwright install firefox; \
	fi

test-e2e:
	cd frontend && if [ -x ./node_modules/.bin/playwright ]; then \
		./node_modules/.bin/playwright test; \
	else \
		$(PNPM) install --frozen-lockfile && $(PNPM) exec playwright test; \
	fi

lint: lint-backend lint-frontend

lint-backend: install
	cd backend && ../$(PYTHON) -m ruff check .
	cd backend && ../$(PYTHON) -m mypy src tests

lint-frontend:
	cd frontend && if [ -x ./node_modules/.bin/eslint ]; then \
		./node_modules/.bin/eslint src --ext .ts,.tsx --report-unused-disable-directives --max-warnings 0; \
	else \
		$(PNPM) install --frozen-lockfile && $(PNPM) lint; \
	fi

pre-commit: install
	$(PYTHON) -m pre_commit run --all-files

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
demo-api: db-up migrate seed reconstruct-race-gaps fit-degradation-demo
	docker compose up -d backend
	$(MAKE) api-wait
	$(PYTHON) -m webbrowser -t http://localhost:8000/docs
	@echo "Demo API is running at: http://localhost:8000/docs"

## demo: full local demo stack (DB + migrate + seeded data + backend + frontend).
## Opens the React dashboard and leaves Swagger available at :8000/docs.
## Gap reconstruction runs after seed so undercut alerts have gap_to_ahead_ms.
demo: db-up migrate seed reconstruct-race-gaps fit-degradation-demo
	docker compose up -d backend frontend
	$(MAKE) api-wait
	$(PYTHON) -m webbrowser -t http://localhost:5173
	@echo "Demo frontend is running at: http://localhost:5173"
	@echo "Swagger is available at: http://localhost:8000/docs"
