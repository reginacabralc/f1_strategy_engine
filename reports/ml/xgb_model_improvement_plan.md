# XGBoost Undercut Modeling Improvement Report

## Decision

Selected approach: keep the lap-level XGBoost pace model as the short-horizon
simulator, harden its temporal tuning/metrics, and replace raw R2 confidence with
metadata-backed validation support. The pair-level undercut model remains an
offline challenger because observed success labels are still too sparse for a
runtime decision layer.

Random Forest was evaluated as a sanity challenger for the pair task. It did not
win: on proxy labels it produced F1 0.0, so it is not a better runtime direction.

## Baseline Before This Pass

The strongest documented temporal setup before this pass used
`TARGET_STRATEGY=session_normalized_delta` and
`FEATURE_SET=no_reference_lap_time_ms`.

| Metric | Previous value |
|---|---:|
| Usable rows | 151,363 |
| Usable sessions | 47 |
| Temporal folds | 5 |
| XGBoost MAE | 1,561.9 ms |
| XGBoost RMSE | 4,614.4 ms |
| XGBoost R2 | 0.007 |
| Zero-delta MAE | 1,762.7 ms |
| Train-mean MAE | 1,612.9 ms |
| Improvement vs zero | 200.8 ms |

Runtime failure mode: `XGBoostPredictor` used aggregate R2 as confidence. With
R2 near 0.007, the undercut engine's `confidence > 0.5` gate was unreachable
even when XGBoost improved MAE.

## Experiments Run

- Expanded XGBoost tuning from a small curated list to a deterministic structured
  random search: 24 candidates total, including 12 seeded random candidates.
- Evaluated `reg:squarederror`, `reg:absoluteerror`, and
  `reg:pseudohubererror`, with varied depth, eta, child weight, subsampling,
  regularization, gamma, rounds, `hist`, and early stopping.
- Added optional quantile winsorization for robust training labels. It is
  recorded in metadata but was not selected in the reproduced run.
- Added richer pace metrics: median, p75, p90 absolute error, signed bias, target
  distribution, and signed bias by circuit, compound, tyre-age bucket, driver,
  and team.
- Added threshold sweeps to the replay-backed undercut comparison.
- Added an offline pair-level XGBoost challenger and a Random Forest challenger
  over `data/causal/undercut_driver_rival_lap.parquet`.

## Selected Lap Model

| Item | Selected value |
|---|---|
| Target | `session_normalized_delta` |
| Feature set | `no_reference_lap_time_ms` |
| Candidate | `candidate_18` |
| Objective | `reg:absoluteerror` |
| Eval metric | `mae` |
| Rounds | 100 |
| Early stopping | 20 |
| `max_depth` | 5 |
| `eta` | 0.032881845587215686 |
| `min_child_weight` | 1 |
| `subsample` | 0.5229121918278311 |
| `colsample_bytree` | 0.6139491378257734 |
| `lambda` | 5 |
| `alpha` | 0 |
| `gamma` | 20 |
| `tree_method` | `hist` |

## Metrics After This Pass

| Metric | Value |
|---|---:|
| XGBoost MAE | 1,379.7 ms |
| XGBoost RMSE | 4,585.0 ms |
| XGBoost R2 | 0.020 |
| Zero-delta MAE | 1,762.7 ms |
| Train-mean MAE | 1,612.9 ms |
| Improvement vs zero | 383.0 ms |
| Improvement vs train-mean | 233.2 ms |
| Train-validation MAE gap | 208.8 ms |
| Calibrated base confidence | 0.755 |

The model now beats zero-delta by 21.7% MAE and beats train-mean by 14.5% MAE on
aggregate temporal CV. R2 is still weak, so confidence is intentionally no longer
interpreted as R2.

## Decision Metrics

`make compare-predictors` over Bahrain, Monaco, and Hungary 2024:

| Metric | scipy | XGBoost |
|---|---:|---:|
| Mean MAE@k=3 | 1,619 ms | 1,424 ms |
| Mean alert F1 | 0.0 | 0.0 |
| Default alerts | 0 | 0 |
| Default confidence-suppressed alerts | 0 | 0 |

Interpretation: XGBoost is now the stronger pace simulator on the replay-backed
comparison, but it is not yet a complete undercut decision layer. The no-alert
failure is no longer explained by the old XGBoost confidence bug; the default
threshold sweep reports zero confidence-suppressed alerts. The remaining failure
is the score/label decision surface and sparse observed undercut labels.

## Pair-Level Challenger

`make evaluate-undercut-challengers` result:

| Model | Label surface | Rows | Precision | Recall | F1 | PR-AUC | Brier |
|---|---|---:|---:|---:|---:|---:|---:|
| XGBoost | proxy `undercut_viable` | 5,294 | 0.364 | 0.444 | 0.400 | 0.180 | 0.002 |
| XGBoost | observed `undercut_success` | 27 | 0.364 | 0.444 | 0.400 | 0.326 | 0.330 |
| Random Forest | proxy `undercut_viable` | 5,294 | 0.000 | 0.000 | 0.000 | 0.200 | 0.002 |

The observed-label sample is only 27 validation rows, so the pair model is not
credible enough to promote. Proxy-label results are useful for diagnostics but
would mostly learn the current scipy/structural heuristic.

## Runtime Confidence

`XGBoostPredictor` now reads `confidence_calibration` from model metadata:

- fold win rate vs zero,
- aggregate improvement vs zero,
- aggregate improvement vs train mean,
- train-validation gap,
- runtime feature support penalties for unknown categorical values and missing
  live numerics.

The predictor still falls back to legacy R2 confidence for old artifacts that do
not contain calibration metadata.

## Limitations

- Alert precision/recall/F1 remain 0.0 on the demo replay comparison.
- Pair-level observed labels are too sparse for runtime promotion.
- The lap model still has weak R2 and large tail errors, especially in early
  stint and high-shift circuit groups.
- Generated artifacts under `data/ml/`, `models/`, and most `reports/ml/*.json`
  remain local outputs unless the repo already tracks that class of artifact.

## Reproduce

```bash
make validate-ml-races
make validate-xgb-dataset
make tune-xgb FEATURE_SET=no_reference_lap_time_ms TARGET_STRATEGY=session_normalized_delta
make train-xgb FEATURE_SET=no_reference_lap_time_ms
make validate-xgb-model
make evaluate-undercut-challengers
make compare-predictors
PYTHONPATH=backend/src .venv/bin/python -m pytest backend/tests/unit/ml -q
PYTHONPATH=backend/src .venv/bin/python -m pytest backend/tests/unit/engine/test_backtest.py backend/tests/unit/engine/test_undercut.py -q
make test-backend
make lint-backend
```
