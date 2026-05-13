# 07 — Augmented Temporal XGBoost Model

## Why this exists

The Day 8 model trained and serialized correctly, but the evaluation set was too
small. Three demo races made LORO behave like leave-one-circuit-out, so
reference pace shifted by several seconds between train and holdout races.

This notebook/report documents the Day 8.5 pivot: more recent-season data and
time-aware validation before any Day 9 undercut backtest.

## Reproduce

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

For a fast local smoke on whatever races are already in DB:

```bash
make build-xgb-dataset SPLIT_STRATEGY=temporal_expanding
make validate-xgb-dataset
make tune-xgb
make train-xgb
make validate-xgb-model
make plot-xgb-diagnostics
```

## Current smoke result

On the current local DB, only the three demo races were loaded. The temporal
smoke therefore created two folds:

| Fold | Train | Validate |
|---|---|---|
| `fold_001` | Bahrain 2024 | Monaco 2024 |
| `fold_002` | Bahrain 2024, Monaco 2024 | Hungary 2024 |

This is useful to validate the pipeline, but it is not the final model-quality
claim. Full quality assessment requires the enabled 2024/2025 manifest races.

## Interpretation rules

- Treat LORO as stress-test evidence only.
- Treat temporal expanding CV as the main model-quality signal.
- Do not use validation/test sessions to compute reference pace or driver
  offsets.
- Do not tune on the final test set.
- Do not add pit-loss features to the lap-level pace model.

## Figures

`make plot-xgb-diagnostics` writes:

- `fold_metrics.png`
- `predicted_vs_actual.png`
- `residual_distribution.png`
- `residuals_by_session.png`
- `error_by_tyre_age.png`
- `feature_importance.png`
- `target_distribution_by_fold.png`

Generated figures are intentionally gitignored under `reports/figures/`.
