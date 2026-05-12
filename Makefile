PYTHON ?= .venv/bin/python
PIP ?= $(PYTHON) -m pip

.PHONY: install db-up db-wait db-down up down down-v logs ps migrate \
        ingest ingest-monaco ingest-demo validate-demo seed \
        fit-degradation validate-degradation report-degradation \
        fit-pit-loss validate-pit-loss \
        fit-driver-offsets validate-driver-offsets \
        replay test test-backend lint demo serve-api

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

## Compose currently includes db, migrate, and backend; frontend is pending Stream C.
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
	cd backend && ../$(PYTHON) -m alembic -c alembic.ini upgrade head

ingest-monaco: install db-wait
	$(PYTHON) scripts/ingest_season.py --year 2024 --round 8 --session R --write-db

## YEAR ?= 2024  ROUND ?= 8  SESSION_CODE ?= R
ingest: install db-wait
	$(PYTHON) scripts/ingest_season.py --year $(or $(YEAR),2024) --round $(or $(ROUND),8) --session $(or $(SESSION_CODE),R) --write-db

ingest-demo: install db-wait
	$(PYTHON) scripts/ingest_season.py --year 2024 --round 1 --session R --write-db
	$(PYTHON) scripts/ingest_season.py --year 2024 --round 8 --session R --write-db
	$(PYTHON) scripts/ingest_season.py --year 2024 --round 13 --session R --write-db

validate-demo: install db-wait
	$(PYTHON) scripts/validate_demo_ingest.py

seed: ingest-demo

fit-degradation: install db-wait
	$(PYTHON) scripts/fit_degradation.py --all-demo

validate-degradation: install db-wait
	$(PYTHON) scripts/validate_degradation.py

report-degradation: validate-degradation

fit-pit-loss: install db-wait
	$(PYTHON) scripts/fit_pit_loss.py

validate-pit-loss: install db-wait
	$(PYTHON) scripts/validate_pit_loss.py

fit-driver-offsets: install db-wait
	$(PYTHON) scripts/fit_driver_offsets.py

validate-driver-offsets: install db-wait
	$(PYTHON) scripts/validate_driver_offsets.py

test: install
	cd backend && ../$(PYTHON) -m pytest tests/unit -q

test-backend: test

lint: install
	cd backend && ../$(PYTHON) -m ruff check .
	cd backend && ../$(PYTHON) -m mypy src tests

serve-api: install
	$(PYTHON) -m uvicorn pitwall.api.main:app --reload --port 8000

## SPEED ?= 30  (replay speed multiplier)
## SESSION ?= monaco_2024_R
replay: install db-wait
	$(PYTHON) scripts/ingest_season.py --year 2024 --round 8 --session R --write-db
	@echo "Replay via API: POST /api/v1/replay/start  (Stream B Day 3 target)"

## demo: DB up (Docker), migrations and seed via local venv.
## Then start Docker backend with: docker compose up -d backend
## Frontend pending Stream C. Requires: cp .env.example .env first.
demo: db-up migrate seed
	@echo "Data ready. Start the backend with: docker compose up -d backend"
	@echo "Then open: http://localhost:8000/docs"
	@echo "Frontend/browser demo is pending Stream C."
