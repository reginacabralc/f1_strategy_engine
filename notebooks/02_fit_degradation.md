# 02 — Fit Quadratic Degradation

## Goal

Day 4 builds the baseline tyre degradation fit from the three demo races already
loaded into local TimescaleDB. It does not train XGBoost and does not touch the
replay engine.

The V1 model is:

```text
lap_time_ms = a + b * tyre_age + c * tyre_age^2
```

Groups are fitted by `(circuit_id, compound)` with a session-id fallback in code
if circuit metadata is unavailable.

## Workflow

```bash
cp .env.example .env
make db-up
make migrate
make ingest-demo
make fit-degradation
make validate-degradation
```

Single-session fit:

```bash
.venv/bin/python scripts/fit_degradation.py --session monaco_2024_R
```

All demo sessions:

```bash
.venv/bin/python scripts/fit_degradation.py --all-demo
```

## Clean-air eligibility

Rows are preserved for diagnostics in `clean_air_lap_times` with:

- `fitting_eligible = TRUE/FALSE`
- `exclusion_reason` such as `pit_in_lap`, `pit_out_lap`,
  `non_green_track_status`, `unsupported_compound`, or `invalid_lap_time`

V1 eligible rows require a valid lap time, dry compound (`SOFT`, `MEDIUM`,
`HARD`), tyre age at least 1, no pit-in/pit-out/deleted flag, no interpreted
non-green track status, and a rough race-lap time range of 60s to 180s.

## Outputs

`scripts/fit_degradation.py` refreshes `clean_air_lap_times`, fits coefficients,
and idempotently upserts rows into `degradation_coefficients`.

The console output reports:

```text
session/circuit | compound | n_laps | R2   | RMSE_ms | status
monaco          | MEDIUM   | 123    | 0.71 | 420     | fitted
```

`fitted_warn` means the fit persisted but R² is below 0.60. Insufficient groups
are printed but not persisted.

## ScipyPredictor

`backend/src/pitwall/degradation/predictor.py` implements the current
`PacePredictor` contract from `backend/src/pitwall/engine/projection.py`:

```python
prediction = predictor.predict(PaceContext(
    driver_code="LEC",
    circuit_id="monaco",
    compound="MEDIUM",
    tyre_age=10,
))
```

The predictor loads `quadratic_v1` rows from `degradation_coefficients`, applies
`a + b * tyre_age + c * tyre_age^2`, rounds to whole milliseconds, and uses R²
as prediction confidence.

## Current Day 4 local validation

On the local demo DB after `make fit-degradation` and `make validate-degradation`:

- Diagnostic lap rows: 3,721
- Eligible fitting rows: 3,503
- Persisted coefficient rows: 8
- Monaco coefficient rows: 3
- Best observed demo fit: Monaco MEDIUM, R² 0.362, RMSE 1701 ms

All current Day 4 fits are `fitted_warn` because the raw per-circuit/per-compound
quadratic is still mixing driver/team/fuel effects. That is acceptable for Day 4
foundation, but Day 5 should either improve the clean-air normalization or
document why the R² ≥ 0.6 target is not realistic for a given group.

After the predictor addition, rerun this DB smoke:

```bash
make db-up
make validate-degradation
```

The validation script now also instantiates `ScipyPredictor` and predicts Monaco
MEDIUM at tyre age 10 when coefficients exist. Latest local smoke after a fresh
Docker DB ingest:

```text
ScipyPredictor smoke: monaco MEDIUM age 10 -> 81366 ms (confidence 0.362)
```

## Stream B integration checkpoint

After the Stream B Day 3 merge, Stream A now provides SQL-backed repository
adapters for the API/replay seam:

- `SqlSessionRepository` lists sessions from `sessions` joined to `events`.
- `SqlSessionEventLoader` builds `session_start`, `lap_complete`, and
  `weather_update` replay events from the ingested DB tables.
- `pitwall.api.dependencies` uses those SQL adapters when `DATABASE_URL` is
  configured, with the in-memory fixtures still available when no DB URL exists.

Latest local DB API smoke:

```text
sessions 200 ['bahrain_2024_R', 'monaco_2024_R', 'hungary_2024_R']
start 202 {'session_id': 'monaco_2024_R', 'pace_predictor': 'scipy', ...}
stop 200 {'stopped': True, ...}
```

## Day 5 notes

- Use `ScipyPredictor` from persisted coefficients inside the undercut engine.
- Add richer notebook plots and call out where R² is below 0.6.
- Prepare driver skill offsets once the baseline curve is stable.
- Keep the XGBoost dataset work separate until the Day 7/8 tasks.
