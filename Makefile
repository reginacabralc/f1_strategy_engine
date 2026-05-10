PYTHON ?= .venv/bin/python
PIP ?= $(PYTHON) -m pip

.PHONY: install db-up db-down up down down-v logs ps migrate \
        ingest-monaco ingest-demo validate-demo seed \
        fit-degradation validate-degradation \
        replay test lint demo

install: .venv/.installed

.venv/.installed: backend/pyproject.toml
	python3 -m venv .venv
	$(PIP) install -U pip
	$(PIP) install -e 'backend[dev]'
	touch .venv/.installed

db-up:
	docker compose up -d db

db-down:
	docker compose down

## Full-stack compose targets (backend + frontend Dockerfiles land in Day 4)
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

migrate: install
	cd backend && ../$(PYTHON) -m alembic -c alembic.ini upgrade head

ingest-monaco: install
	$(PYTHON) scripts/ingest_season.py --year 2024 --round 8 --session R --write-db

ingest-demo: install
	$(PYTHON) scripts/ingest_season.py --year 2024 --round 1 --session R --write-db
	$(PYTHON) scripts/ingest_season.py --year 2024 --round 8 --session R --write-db
	$(PYTHON) scripts/ingest_season.py --year 2024 --round 13 --session R --write-db

validate-demo: install
	$(PYTHON) scripts/validate_demo_ingest.py

seed: ingest-demo

fit-degradation: install
	$(PYTHON) scripts/fit_degradation.py --all-demo

validate-degradation: install
	$(PYTHON) scripts/validate_degradation.py

test: install
	cd backend && ../$(PYTHON) -m pytest tests/unit -q

lint: install
	cd backend && ../$(PYTHON) -m ruff check .
	cd backend && ../$(PYTHON) -m mypy src tests

## SPEED ?= 30  (replay speed multiplier)
## SESSION ?= monaco_2024_R
replay: install
	$(PYTHON) scripts/ingest_season.py --year 2024 --round 8 --session R --write-db
	@echo "Replay via API: POST /api/v1/replay/start  (Stream B Day 3 target)"

## demo: bring up DB, migrate, seed, and open backend. Frontend Dockerfile lands Day 4.
demo: db-up migrate seed
	@echo "Backend: http://localhost:8000  (run 'uvicorn pitwall.api.main:app --port 8000' locally)"
	@echo "Full docker demo available once backend/frontend Dockerfiles land (Stream D Day 4)"
