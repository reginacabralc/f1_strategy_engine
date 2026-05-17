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
make diagnose-xgb-shift
make evaluate-xgb-baselines
make run-xgb-ablations
make tune-xgb FEATURE_SET=no_reference_lap_time_ms TARGET_STRATEGY=session_normalized_delta
make train-xgb FEATURE_SET=no_reference_lap_time_ms
make validate-xgb-model
make evaluate-undercut-challengers
make plot-xgb-diagnostics
```

For a fast local smoke on whatever races are already in DB:

```bash
make build-xgb-dataset SPLIT_STRATEGY=temporal_expanding
make validate-xgb-dataset
make diagnose-xgb-shift
make evaluate-xgb-baselines
make run-xgb-ablations
make tune-xgb FEATURE_SET=no_reference_lap_time_ms TARGET_STRATEGY=session_normalized_delta
make train-xgb FEATURE_SET=no_reference_lap_time_ms
make validate-xgb-model
make evaluate-undercut-challengers
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
- Treat Day 8.2 diagnostics as a gate before Day 9: XGBoost must beat
  zero-delta and train-mean baselines on aggregate temporal CV.
- Do not use validation/test sessions to compute reference pace or driver
  offsets.
- Do not tune on the final test set.
- Do not add pit-loss features to the lap-level pace model.

## Day 8.2 target/reference diagnostics

The first full-manifest run showed the model remained weak even after adding
2024/2025 coverage. The most important symptom was target/reference shift:
early temporal folds had target means around -9.6 s and +12.0 s. Day 8.2
therefore adds:

- `reports/ml/xgb_dataset_shift_report.json` and `.md` for fold/session target
  distributions, reference source counts, driver offset source counts, failed
  ingestions, and zero-usable sessions.
- `reports/ml/baseline_ladder.json` so XGBoost is compared against zero,
  train-mean, circuit+compound, tyre-age curve, and driver/team-adjusted
  baselines.
- `reports/ml/feature_ablation_report.json` for controlled feature group
  checks.
- `TARGET_STRATEGY` experiments for session-normalized, stint-relative,
  absolute-lap-time, and season+circuit+compound targets.

Known data edge cases are explicit: the rerun loaded 2024 Qatar successfully,
while 2024 Sao Paulo ingested but produced zero dry usable rows because FastF1
exposed blank/WET compound data under non-standard conditions.

Observed Day 8.2 result:

- Selected target: `session_normalized_delta`.
- Selected feature set: `no_reference_lap_time_ms`.
- Selected XGBoost config: depth 2, eta 0.02, subsample 0.8, colsample 0.8,
  min-child-weight 20, lambda 20, alpha 5, 200 rounds.
- Aggregate temporal CV: MAE 1,561.9 ms, RMSE 4,614.4 ms, R² 0.007.
- Baselines: zero-delta MAE 1,762.7 ms; train-mean MAE 1,612.9 ms.
- Gate: passed by 200.8 ms vs zero-delta (11.4%) and by 51.0 ms vs
  train-mean; all five folds improve over zero-delta.

## Day 8.6 runtime-first hardening

The undercut-oriented pass kept the same target and feature set, but expanded
tuning to a deterministic 24-candidate search and fixed XGBoost runtime
confidence.

- Selected candidate: `candidate_18`.
- Selected objective: `reg:absoluteerror`.
- Selected config: depth 5, eta 0.032881845587215686, subsample
  0.5229121918278311, colsample 0.6139491378257734, min-child-weight 1,
  lambda 5, alpha 0, gamma 20, `tree_method=hist`, 100 rounds, early stopping 20.
- Aggregate temporal CV: MAE 1,379.7 ms, RMSE 4,585.0 ms, R2 0.020.
- Baselines: zero-delta MAE 1,762.7 ms; train-mean MAE 1,612.9 ms.
- Gate: passed by 383.0 ms vs zero-delta (21.7%) and by 233.2 ms vs
  train-mean.
- Runtime confidence: metadata-calibrated base confidence 0.755, with penalties
  for unknown runtime circuit/compound/driver/team and missing live numeric
  features. Raw R2 is no longer used as the main confidence gate.

Replay-backed decision metrics still show F1 0.0 for both scipy and XGBoost.
After the confidence fix, the default threshold sweep reports zero
confidence-suppressed alerts, so the remaining blocker is the score/label
decision surface rather than XGBoost confidence.

The pair-level XGBoost and Random Forest challengers are offline only. XGBoost
gets proxy-label F1 0.400, but observed-success validation has only 27 rows.
Random Forest gets proxy-label F1 0.0. Neither should become runtime default.

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
