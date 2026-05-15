# ADR 0010 — Temporal expanding-window validation for XGBoost

## Estado

Aceptado — 2026-05-13

## Contexto

The Day 8 XGBoost pipeline is engineering-complete, but its 3-race LORO
evaluation is not a useful quality signal. With Bahrain, Monaco, and Hungary
only, LORO becomes leave-one-circuit-out. The holdout target/reference shift is
larger than the lap-level effects the model is meant to learn.

The model is not considered broken. The validation design and data coverage are
too sparse for the claim we want to make.

## Decisión

Use recent multi-season race coverage and make `temporal_expanding` the primary
ML validation strategy.

- Ingest 2024 and 2025 race sessions from `data/reference/ml_race_manifest.yaml`.
- Keep 2026 entries disabled by default; enable them only when FastF1 has data
  and `race_date <= as_of_date`.
- Keep LORO as a stress test, not the main model-quality claim.
- Build expanding folds by `(season, round_number)`: train on past sessions,
  validate on future sessions.
- Fit reference pace, driver offsets, and encoders from training rows only.
- Tune XGBoost only on temporal validation folds; no final-test leakage.
- Defer CatBoost and LightGBM until the data/split issue is solved.

## Consecuencias

Positive:

- Evaluation now matches how the model would be used over time.
- Temporal leakage has explicit tests and validators.
- The manifest makes data coverage auditable and repeatable.
- XGBoost remains the stable default implementation.

Negative:

- First uncached ingestion of 48 races can take hours and several GB of cache.
- Temporal folds with only demo races are still weak smoke tests, not final
  evidence.
- CatBoost/LightGBM comparison is deferred rather than implemented in this PR.

## Validation

Required commands before using the model as evidence:

```bash
make validate-ml-races
make ingest-ml-races
make fit-degradation
make fit-pit-loss
make fit-driver-offsets
make build-xgb-dataset SPLIT_STRATEGY=temporal_expanding
make validate-xgb-dataset
make tune-xgb
make train-xgb
make validate-xgb-model
make plot-xgb-diagnostics
```

Day 9 backtesting remains out of scope until model quality is assessed with the
expanded temporal dataset.
