PYTHON ?= .venv/bin/python
PIP ?= $(PYTHON) -m pip
PNPM ?= $(shell command -v pnpm >/dev/null 2>&1 && echo pnpm || echo "corepack pnpm")

.PHONY: install db-up db-wait db-down up down down-v logs ps migrate \
        ingest ingest-monaco ingest-demo validate-demo seed \
        ingest-ml-races validate-ml-races \
        fit-degradation validate-degradation report-degradation \
        fit-pit-loss validate-pit-loss \
        fit-driver-offsets validate-driver-offsets \
        build-xgb-dataset validate-xgb-dataset diagnose-xgb-shift \
        evaluate-xgb-baselines run-xgb-ablations \
        tune-xgb train-xgb validate-xgb-model \
        plot-xgb-diagnostics \
        audit-causal-inputs reconstruct-race-gaps derive-known-undercuts \
        import-curated-known-undercuts build-causal-dataset run-causal-dowhy \
        compare-causal-engines prepare-causal-extended-data \
        replay test test-backend test-frontend lint lint-backend lint-frontend \
        demo serve-api api-wait

install: .venv/.installed

.venv/.installed: backend/pyproject.toml
	python3 -m venv .venv
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

test: test-backend test-frontend

test-backend: install
	cd backend && ../$(PYTHON) -m pytest tests/unit -q

test-frontend:
	cd frontend && $(PNPM) install --frozen-lockfile
	cd frontend && $(PNPM) test

lint: lint-backend lint-frontend

lint-backend: install
	cd backend && ../$(PYTHON) -m ruff check .
	cd backend && ../$(PYTHON) -m mypy src tests

lint-frontend:
	cd frontend && $(PNPM) install --frozen-lockfile
	cd frontend && $(PNPM) lint

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

## demo: DB up (Docker), migrations and seed via local venv, then API up.
## Opens Swagger automatically. Requires: cp .env.example .env first.
demo: db-up migrate seed
	docker compose up -d backend
	$(MAKE) api-wait
	$(PYTHON) -m webbrowser -t http://localhost:8000/docs
	@echo "Demo API is running at: http://localhost:8000/docs"
