# 05 — XGBoost Pace Dataset

## Goal

Day 7 builds the lap-level pace dataset for XGBoost training. This step does
not train the model; runtime prediction is covered by `XGBoostPredictor`.

Generated artifacts:

```text
data/ml/xgb_pace_dataset.parquet
data/ml/xgb_pace_dataset.meta.json
```

`data/ml/` is gitignored because these files are generated artifacts.

## Reproduce

```bash
cp .env.example .env
make migrate
make ingest-demo
make fit-degradation
make fit-pit-loss
make fit-driver-offsets
make build-xgb-dataset
make validate-xgb-dataset
```

## Target

The current default target is:

```text
session_normalized_delta_ms = lap_time_ms - median(prior clean dry laps in the same session+compound)
```

It is stored in the shared `lap_time_delta_ms` column for experiment
compatibility. When a live-safe prior session+compound reference is unavailable,
the dataset falls back to the fold-training reference pace. The older
`lap_time_delta` target remains available for stress tests, but the temporal
modeling gate selected `session_normalized_delta` because it reduced
target/reference shift.

For fallback reference pace, lookup order is:

1. training-session median for `(circuit_id, compound)`,
2. training-session global median for `compound`,
3. mark row unusable with `missing_reference`.

## Split

The main split is `temporal_expanding` by session event order. LORO remains
available as a stress test.

For the historical three-race smoke, LORO created:

```text
fold_bahrain_2024_R
fold_hungary_2024_R
fold_monaco_2024_R
```

Each fold has rows marked `split=train` or `split=validation`/`split=holdout`.
Reference pace and driver offsets for evaluation rows are computed only from
that fold's training sessions.

## Driver Offsets

Driver pace offset is included as a feature, but it is recomputed fold-safely
inside the dataset builder. Persisted all-race offsets are not used for holdout
features because that would leak the holdout race into evaluation.

Lookup order:

1. training-session median residual for `(driver_code, circuit_id, compound)`,
2. training-session median residual for `(driver_code, compound)`,
3. `0.0` with `driver_pace_offset_missing = true`.

## Traffic Features

Traffic is represented by dynamic proxy features:

```text
is_in_traffic = gap_to_ahead_ms < 1500
dirty_air_proxy_ms = max(0, 2000 - gap_to_ahead_ms)
```

This keeps traffic as an observed context feature instead of baking it into a
static correction.

## Pit Loss Exclusion

Pit loss is intentionally excluded from the lap-level pace dataset. Pit loss is
part of the undercut decision layer and Day 9 backtest features, not the Day 7
pace model. The dataset validator fails if any column containing `pit_loss`
appears.

## Feature Columns

```text
session_id
circuit_id
driver_code
team_code
compound
tyre_age
lap_number
stint_number
lap_in_stint
lap_in_stint_ratio
race_progress
fuel_proxy
track_temp_c
air_temp_c
position
gap_to_ahead_ms
gap_to_leader_ms
is_in_traffic
dirty_air_proxy_ms
driver_pace_offset_ms
driver_pace_offset_missing
reference_lap_time_ms
```

Target column:

```text
lap_time_delta_ms
```

## Filtering

V1 includes only:

- SOFT, MEDIUM, HARD compounds,
- green-flag laps,
- valid non-deleted laps,
- non pit-in and non pit-out laps,
- rows with `lap_time_ms` and `tyre_age`.

## Validation

`make validate-xgb-dataset` checks:

- parquet and metadata files exist,
- row count is positive and matches metadata,
- required columns exist,
- target is non-null for usable rows,
- temporal folds exist by default,
- evaluation folds do not list evaluation sessions as training sessions,
- evaluation driver-offset source sessions do not contain the evaluation session,
- no pit-loss columns exist,
- dry compounds and clean-lap filters are respected.

## Day 8 Training Handoff

The Day 8 training report is `notebooks/06_xgb_training.md`. It uses this
dataset unchanged, trains native `xgboost.Booster` fold models plus one final
all-data model, and reports the real zero-delta baseline comparison.

## V2 Improvements

- ingest more races and seasons,
- improve traffic modeling beyond simple gap proxies,
- add SC/VSC-aware pit-loss adjustment in the decision layer,
- build richer reference pace hierarchies,
- keep the pair-level undercut outcome dataset as an offline challenger until
  observed success labels are large enough for runtime promotion.
