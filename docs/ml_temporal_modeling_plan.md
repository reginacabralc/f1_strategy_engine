# ML Temporal Modeling Implementation Outline

## Objective

Replace the 3-race-only XGBoost quality claim with a manifest-driven,
recent-season pipeline and leakage-safe temporal validation.

## Data Coverage

- `data/reference/ml_race_manifest.yaml` is the source of race coverage.
- 2024 and 2025 race sessions are enabled by default.
- 2026 entries are disabled by default and must be enabled only after FastF1
  availability is confirmed.
- `scripts/ingest_race_manifest.py` writes `data/ml/ingestion_report.json`
  with attempted, succeeded, skipped, and failed sessions.

## Split Strategy

Primary split: `temporal_expanding`.

- Sessions are ordered by `(season, round_number)`.
- `event_order` is written into the dataset for validation.
- Each fold trains only on sessions before the validation window.
- Reference pace, driver offsets, and categorical encoders are fit from training
  rows only.
- LORO remains available with `SPLIT_STRATEGY=loro` as a stress test.

## Tuning And Diagnostics

- `make tune-xgb` evaluates a curated 8-candidate XGBoost search.
- Selection criterion is validation MAE, then RMSE, then train-validation MAE gap.
- `make plot-xgb-diagnostics` writes matplotlib figures under `reports/figures/`.
- CatBoost and LightGBM are deferred to V2 to avoid destabilizing the default
  environment before the data coverage problem is solved.

## Validation Boundary

This work does not start Day 9 backtesting. The next gate is to ingest the full
manifest, rebuild temporal folds, review model quality, and only then run the
undercut backtest.
