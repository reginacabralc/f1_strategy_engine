# 01 — Explore FastF1 One-Round Ingestion

## Demo target

- Race: Monaco GP 2024
- Round: 8
- Session: R
- Local session id: `monaco_2024_R`

## Setup

Create and install the repo-root virtual environment:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -U pip
.venv/bin/python -m pip install -e 'backend[dev]'
```

FastF1 cache defaults to `data/cache`. Override it with:

```bash
FASTF1_CACHE_DIR=/path/to/cache .venv/bin/python scripts/ingest_season.py
```

## Run one-round ingestion

Default demo target:

```bash
.venv/bin/python scripts/ingest_season.py
```

Explicit equivalent:

```bash
.venv/bin/python scripts/ingest_season.py --year 2024 --round 8 --session R
```

Expected local outputs:

```text
data/processed/monaco_2024_R/
  drivers.parquet
  laps.parquet
  pit_stops.parquet
  stints.parquet
  weather.parquet
  metadata.json
```

## Known FastF1 caveats

- FastF1 columns vary by season/session, so normalization treats missing columns as `None`.
- Pit stop duration is not guaranteed as a standalone table in the loaded session; Day 2 derives pit markers from lap pit-in/pit-out fields.
- Timedelta values are converted to integer milliseconds before write boundaries.
- Deleted, invalid, and pit laps are preserved with flags; Day 3 fitting code decides what to exclude.
- The first run can be slow because FastF1 downloads and populates `data/cache`.

## Day 3 next steps

- Ingest the three demo races: Bahrain 2024 round 1, Monaco 2024 round 8, Hungary 2024 round 13.
- Connect the writer to real DB/Alembic utilities once Stream D lands them.
- Prepare degradation-fitting inputs from normalized laps and stints.
- Start the scipy degradation fit and document filtering choices.

## Day 3 DB ingest workflow

From a clean clone with Docker installed:

```bash
cp .env.example .env
make db-up
make migrate
make ingest-demo
make validate-demo
```

`make ingest-demo` writes the three demo races to local TimescaleDB:

- Bahrain 2024, round 1, race session R
- Monaco 2024, round 8, race session R
- Hungary 2024, round 13, race session R

`make validate-demo` prints counts for `laps`, `stints`, `pit_stops`, and
`weather`, then prints clean lap availability by `(session_id, compound)` using
the same filter planned for Day 4 degradation inputs.

## Day 4 degradation workflow

```bash
make migrate
make fit-degradation
make validate-degradation
```

Details live in `notebooks/02_fit_degradation.md`.
