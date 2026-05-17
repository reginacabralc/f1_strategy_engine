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

## Day 8.2 Diagnostics And Improvement Gate

- `make diagnose-xgb-shift` writes target/reference shift diagnostics under
  `reports/ml/`.
- `make evaluate-xgb-baselines` writes a leakage-safe baseline ladder. XGBoost
  must beat zero-delta and train-mean before Day 9 backtesting.
- `make run-xgb-ablations` checks whether circuit one-hots, reference pace, and
  driver offsets improve temporal validation or only memorize fold shifts.
- `make build-xgb-dataset TARGET_STRATEGY=...` supports controlled target
  experiments: `lap_time_delta`, `session_normalized_delta`,
  `stint_relative_delta`, `absolute_lap_time`, and
  `season_circuit_compound_delta`.
- `make tune-xgb` evaluates curated candidates plus a deterministic structured
  random search including non-square objectives, regularization, sampling, early
  stopping, and varied boost rounds.
- Selection criterion is validation MAE, then RMSE, then train-validation MAE gap.
- `make plot-xgb-diagnostics` writes matplotlib figures under `reports/figures/`.
- CatBoost and LightGBM are deferred to V2 to avoid destabilizing the default
  environment before the data coverage problem is solved.

## Observed Day 8.2 Result

The selected Day 8.2 target is `session_normalized_delta`: each lap is measured
against prior clean dry laps in the same session and compound, with a
fold-training reference fallback. This removed the extreme fold-mean warnings
seen with `lap_time_delta`.

The selected feature set is `no_reference_lap_time_ms`; ablation showed that
removing the unstable reference feature produced the best temporal validation
MAE.

Final temporal CV on the full 2024/2025 manifest:

- Ingestion: attempted 48, succeeded 48, failed 0, skipped six disabled 2026
  races.
- Dataset: 151,363 usable rows, 47 usable sessions, five expanding folds.
- Zero-usable session: 2024 Sao Paulo, `unsupported_or_missing_compound`.
- Selected XGBoost config: `reg:absoluteerror`, `max_depth=5`,
  `eta=0.032881845587215686`, `subsample=0.5229121918278311`,
  `colsample_bytree=0.6139491378257734`, `min_child_weight=1`, `lambda=5`,
  `alpha=0`, `gamma=20`, `tree_method=hist`, `num_boost_round=100`, early
  stopping 20.
- Aggregate temporal CV: MAE 1,379.7 ms, RMSE 4,585.0 ms, R2 0.020.
- Baselines: zero-delta MAE 1,762.7 ms, train-mean MAE 1,612.9 ms.
- Gate: passed. XGBoost beats zero-delta by 383.0 ms (21.7%) and beats
  train-mean by 233.2 ms.
- Runtime confidence is calibrated from temporal validation support instead of
  raw aggregate R2. The current model sidecar reports base confidence 0.755.

## Validation Boundary

This work starts the model-side portion of Day 9 but does not promote a
pair-level decision model to runtime. The current replay-backed comparison
selects XGBoost as the stronger pace simulator, while alert F1 remains 0.0 and
must be solved at the decision-label/threshold layer.
