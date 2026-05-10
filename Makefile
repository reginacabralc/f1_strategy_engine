PYTHON ?= .venv/bin/python
PIP ?= $(PYTHON) -m pip

.PHONY: install db-up db-down migrate ingest-monaco ingest-demo validate-demo fit-degradation validate-degradation test lint

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

fit-degradation: install
	$(PYTHON) scripts/fit_degradation.py --all-demo

validate-degradation: install
	$(PYTHON) scripts/validate_degradation.py

test: install
	cd backend && ../$(PYTHON) -m pytest tests/unit -q

lint: install
	cd backend && ../$(PYTHON) -m ruff check .
	cd backend && ../$(PYTHON) -m mypy src tests
