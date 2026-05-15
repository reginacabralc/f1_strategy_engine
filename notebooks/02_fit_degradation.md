# 02 — Fit Quadratic Degradation

## Goal

Day 5 stabilizes the baseline tyre degradation fit from the three demo races
loaded into local TimescaleDB. This report documents persisted coefficients,
real R2/RMSE, and the `ScipyPredictor` smoke path expected by the Stream B
engine/API flow.

This does not train XGBoost, create training splits, compute pit loss, or change
the undercut engine internals.

The V1 model is:

```text
lap_time_ms = a + b * tyre_age + c * tyre_age^2
```

Groups are fitted by `(circuit_id, compound)` with a session-id fallback in code
if circuit metadata is unavailable.

## Reproducible Workflow

```bash
cp .env.example .env
make test
make lint
make down-v
make migrate
make ingest-demo
make validate-demo
make fit-degradation
make validate-degradation
```

`make migrate`, `make ingest-demo`, `make validate-demo`,
`make fit-degradation`, and `make validate-degradation` all depend on
`db-wait`, so the DB container is started and checked with `pg_isready` before
SQL commands run.

Single-session fit:

```bash
.venv/bin/python scripts/fit_degradation.py --session monaco_2024_R
```

All demo sessions:

```bash
.venv/bin/python scripts/fit_degradation.py --all-demo
```

Report persisted coefficients and predictor smoke:

```bash
make report-degradation
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

## Current Day 5 local validation

On a clean local DB after:

```bash
make down-v
make migrate
make ingest-demo
make fit-degradation
make validate-degradation
```

- Diagnostic lap rows: 3,721
- Eligible fitting rows: 3,503
- Persisted coefficient rows: 8
- Monaco coefficient rows: 3
- Best observed demo fit: Monaco MEDIUM, R² 0.362, RMSE 1701 ms

Persisted coefficient table:

| circuit_id | compound | n_laps | R2    | RMSE_ms | source_sessions |
|------------|----------|--------|-------|---------|-----------------|
| bahrain | HARD | 731 | 0.017 | 1058 | `bahrain_2024_R` |
| bahrain | SOFT | 312 | 0.125 | 2125 | `bahrain_2024_R` |
| hungary | HARD | 823 | 0.040 | 1318 | `hungary_2024_R` |
| hungary | MEDIUM | 412 | 0.128 | 2047 | `hungary_2024_R` |
| hungary | SOFT | 38 | 0.084 | 2872 | `hungary_2024_R` |
| monaco | HARD | 764 | 0.190 | 1988 | `monaco_2024_R` |
| monaco | MEDIUM | 391 | 0.362 | 1701 | `monaco_2024_R` |
| monaco | SOFT | 32 | 0.032 | 1460 | `monaco_2024_R` |

All current fits are `fitted_warn` because R2 is below 0.60. This is acceptable
for the MVP baseline because it proves the end-to-end data/model contract:
clean-air rows are extracted, coefficients are persisted idempotently, and the
engine can consume the `PacePredictor` shape. It is not acceptable to present
these curves as high-quality tyre models yet.

Post-correction, the fit uses a neutralized lap-time proxy before fitting:

- driver median offsets are removed within each `(circuit_id, compound)` group,
- later race laps are adjusted with a transparent fuel-burn proxy,
- close-car traffic is adjusted with a `gap_to_ahead_ms` dirty-air penalty.

This improves the input hygiene without changing the quadratic model shape or
the persisted coefficient schema. The remaining limitation is that these are
still proxies, not direct fuel load, aero wake, or driver-performance telemetry.

After the predictor addition, rerun this DB smoke:

```bash
make db-up
make validate-degradation
```

The validation script now also instantiates `ScipyPredictor` and predicts Monaco
MEDIUM at tyre age 10 when coefficients exist. Latest clean-DB smoke:

```text
ScipyPredictor smoke: monaco MEDIUM age 10 -> 81366 ms (confidence 0.362)
```

Unit coverage also verifies:

- `ScipyPredictor` loads persisted-style coefficient rows.
- It satisfies the runtime-checkable `PacePredictor` Protocol.
- Missing coefficients raise `UnsupportedContextError`.
- R2 is clamped into the `PacePrediction.confidence` `[0, 1]` range.
- `engine.undercut.evaluate_undercut()` accepts a DB-loaded `ScipyPredictor`
  without a shape mismatch.

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

- Day 5 Stream A is complete as a functional baseline/report, not as a
  high-R2 model.
- Recommended next step is Day 6 pit-loss estimation. This supports the engine
  decision threshold without changing the pace-model data split or starting
  XGBoost work.
- After pit loss, revisit model quality with explicit driver/team/fuel
  normalization. Do not choose a train/test split or XGBoost feature plan
  without a separate review.
- Keep the XGBoost dataset work separate until the Day 7/8 tasks.
