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

## Day 5 notes

- Use the persisted coefficients as the source for `ScipyPredictor`.
- Add richer notebook plots and call out where R² is below 0.6.
- Prepare driver skill offsets once the baseline curve is stable.
- Keep the XGBoost dataset work separate until the Day 7/8 tasks.
