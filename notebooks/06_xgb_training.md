# 06 - XGBoost Pace Training

## Scope

Day 8 trains, evaluates, serializes, and validates the first XGBoost pace
model from the Day 7 leakage-safe dataset.

This is not the Day 9 backtest. It does not add pit-loss features, known
undercut labels, or a full `XGBoostPredictor.predict()` feature pipeline.

## Reproduce

From a clean local DB with Docker available:

```bash
cp .env.example .env
make migrate
make ingest-demo
make fit-degradation
make fit-pit-loss
make fit-driver-offsets
make build-xgb-dataset
make validate-xgb-dataset
make train-xgb
make validate-xgb-model
```

For a faster artifact-only rerun after the dataset already exists:

```bash
make train-xgb
make validate-xgb-model
```

## Modeling Decisions

The target is:

```text
lap_time_delta_ms = lap_time_ms - reference_lap_time_ms
```

This keeps the model focused on pace deltas instead of relearning that Bahrain,
Monaco, and Hungary have different raw lap-time scales.

The split strategy is leave-one-race-out by `session_id`. For each fold, the
holdout race is completely excluded when Day 7 computes reference pace and
driver pace offsets. This is the right V1 split because the production question
is whether the model generalizes to another race, not whether it memorizes laps
from the same session.

Categorical features use one-hot encoding:

- `circuit_id`
- `compound`
- `driver_code`
- `team_code`

Missing or unseen categorical values encode as `UNKNOWN`. Numeric missing values
are left as `NaN` for XGBoost.

`session_id` is kept in the dataset as a fold identifier, but it is not used as
a training feature. Including it would invite memorization and would not help a
new holdout race.

Pit loss is excluded from the lap-level pace model. Pit loss belongs to Day 9
undercut/backtest decision features, where it is combined with gaps and strategy
state rather than used to predict clean-lap pace.

## Model Artifacts

Generated artifacts:

```text
models/xgb_pace_v1.json
models/xgb_pace_v1.meta.json
```

Both paths are generated artifacts and are gitignored.

The model is saved as a native `xgboost.Booster` JSON file because Stream B's
`XGBoostPredictor.from_file()` loads `xgb.Booster` directly.

## Day 8.1 Diagnostics

Latest Day 8.1 run on the three demo races:

| Holdout session | Train rows | Holdout rows | Train MAE | Train RMSE | Train R2 | Holdout MAE | Holdout RMSE | Holdout R2 | Zero MAE | Train-mean MAE | Improvement vs zero |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `bahrain_2024_R` | 2,460 | 1,043 | 340.7 | 502.0 | 0.934 | 14,356.7 | 14,396.3 | -62.499 | 14,431.0 | 14,364.9 | 74.2 |
| `hungary_2024_R` | 2,230 | 1,273 | 299.9 | 441.6 | 0.946 | 2,290.9 | 3,532.1 | -0.096 | 2,553.5 | 2,560.8 | 262.6 |
| `monaco_2024_R` | 2,316 | 1,187 | 240.9 | 356.1 | 0.953 | 6,754.6 | 7,403.6 | -4.040 | 6,515.6 | 6,538.4 | -239.0 |

Holdout target distributions for `lap_time_delta_ms`:

| Holdout session | Count | Mean | Median | Std | Min | P10 | P90 | Max |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `bahrain_2024_R` | 1,043 | 14,431.0 | 14,026.0 | 1,806.6 | 10,792.0 | 12,435.4 | 16,738.0 | 28,398.0 |
| `hungary_2024_R` | 1,273 | 1,652.5 | 1,683.0 | 3,374.6 | -17,246.5 | -597.6 | 4,918.2 | 18,087.0 |
| `monaco_2024_R` | 1,187 | -6,451.8 | -5,991.5 | 3,297.9 | -23,065.0 | -9,790.5 | -3,017.7 | 5,491.5 |

Aggregate holdout metrics:

| Metric | Value |
|---|---:|
| Dataset rows | 10,509 |
| Unique holdout rows across folds | 3,503 |
| Encoded features | 57 |
| Train MAE | 294.7 ms |
| Train RMSE | 438.7 ms |
| Train R2 | 0.943 |
| Holdout MAE | 7,396.0 ms |
| Holdout RMSE | 9,209.6 ms |
| Holdout R2 | -0.080 |
| Zero-delta MAE | 7,432.5 ms |
| Zero-delta RMSE | 9,268.2 ms |
| Train-mean MAE | 7,423.2 ms |
| MAE improvement vs zero | 36.6 ms |

Top feature importances by XGBoost gain:

| Feature | Gain |
|---|---:|
| `circuit_id__bahrain` | 3,931,985,920 |
| `reference_lap_time_ms` | 3,454,194,176 |
| `circuit_id__monaco` | 2,596,353,280 |
| `circuit_id__hungary` | 1,041,256,064 |
| `compound__SOFT` | 260,751,328 |
| `stint_number` | 225,496,816 |
| `driver_pace_offset_ms` | 178,241,136 |
| `lap_number` | 165,057,968 |
| `fuel_proxy` | 123,934,968 |
| `lap_in_stint` | 106,666,472 |

## Interpretation

MAE is the average absolute target error in milliseconds. RMSE penalizes large
misses more heavily than MAE. R2 compares the model to predicting the holdout
mean; negative R2 means the model is not explaining holdout variance well.

The Day 8 model is engineering-complete, but model quality is weak. It barely
improves aggregate MAE over the zero-delta baseline, does not beat zero on
Monaco, and has negative holdout R2. Negative R2 means the model is worse than
predicting the holdout mean for variance explanation.

The train-vs-holdout split makes the main issue explicit. Training MAE is
294.7 ms with R2 0.943, while holdout MAE is 7,396.0 ms with R2 -0.080. That is
not a serialization bug. It is weak generalization under a harsh split.

With only three races, leave-one-race-out is effectively leave-one-circuit-out:
the holdout circuit has no repeated historical context. Bahrain is especially
diagnostic: its target mean is +14.4 s because the fold reference is learned
from Monaco/Hungary training races, so the target/reference shift dominates the
target. Feature gain also confirms the model is leaning heavily on circuit and
reference-lap features rather than learning a portable pace law.

This does not invalidate the project. It exposes a data limitation early:
XGBoost needs more race coverage, repeated circuits across seasons, or richer
circuit/reference descriptors before it can be expected to generalize. Do not
claim the current XGBoost model is accurate.

## Scipy Baseline Status

Scipy comparison is deferred to Day 9. The Day 9 backtest should compare:

- zero-delta baseline
- scipy degradation baseline
- XGBoost pace model

on the same undercut/backtest decision surface.

## V2 Improvements

- Add 8-10+ races before drawing strong model-quality conclusions.
- Prefer repeated circuits across seasons when possible.
- Add richer circuit descriptors or historical reference pace for unseen tracks.
- Add a known-circuit evaluation later, separate from unseen-circuit LORO.
- Tune only after the larger dataset is available.
- Add better traffic modeling and safety-car/VSC context.
- Improve reference pace fallback for sparse circuit/compound groups.
- Add a pair-level undercut outcome dataset for Day 9+ backtesting.
- Persist or register model metadata in `model_registry` once the runtime
  loader needs DB-level model discovery.
