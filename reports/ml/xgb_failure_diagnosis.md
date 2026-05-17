# XGBoost Undercut Failure Diagnosis

## Executive Summary

PR #58 made the XGBoost pace simulator better, but it did not make the undercut
decision layer useful. The failure is now clearly downstream of lap-level
tuning:

- XGBoost improves replay MAE@k=3 versus scipy: `1424 ms` vs `1619 ms`.
- XGBoost calibrated confidence is no longer the blocker.
- Full score decomposition over Bahrain, Monaco, and Hungary found `60,083`
  evaluated pairs, `0` positive scores, `0` alerts, and `0` confidence-suppressed
  alerts.
- The best raw score was still `-12,048 ms`, so even zero score threshold, zero
  confidence threshold, lower margin, lower pit loss, and weaker cold-tyre
  assumptions do not recover alerts.

The main blocker is the decision surface, not another XGBoost tuning pass. The
current score formula is aligned with "can the attacker erase the whole pit loss
before the defender stops?" while the replay labels are pit-cycle undercut
success labels. Those are different targets.

Recommended next path: **fix label/backtest construction first, then recalibrate
the undercut physics/score formula.** Keep XGBoost as the pace simulator. Do not
promote the pair-level challenger to runtime yet.

## Baseline Evidence

Existing PR #58 artifacts:

| Metric | scipy | XGBoost |
|---|---:|---:|
| Mean MAE@k=3 | `1619 ms` | `1424 ms` |
| Mean alert F1 | `0.0` | `0.0` |
| Default alerts | `0` | `0` |
| Default confidence-suppressed alerts | `0` | `0` |

XGBoost model metadata:

| Item | Value |
|---|---:|
| Target | `session_normalized_delta` |
| Feature set | `no_reference_lap_time_ms` |
| Temporal MAE | `1379.7 ms` |
| Improvement vs zero-delta | `383.0 ms` |
| Calibrated base confidence | `0.755` |

This proves the old raw-R2 confidence bug is not the remaining explanation.

## Score Decomposition

Command:

```bash
docker compose run --rm \
  -v /Users/gabo/Developer/ITAM/Fuentes/f1_strategy_engine:/work \
  -w /work \
  -e PYTHONPATH=/work/backend/src \
  -e DATABASE_URL=postgresql+psycopg://pitwall:pitwall@db:5432/pitwall \
  backend python scripts/diagnose_undercut_scores.py \
  --predictor xgboost \
  --session bahrain_2024_R \
  --session monaco_2024_R \
  --session hungary_2024_R
```

Summary:

| Metric | Value |
|---|---:|
| Evaluated pairs | `60,083` |
| Evaluable `UNDERCUT_VIABLE` decisions | `37,841` |
| Insufficient-data decisions | `22,242` |
| Positive scores | `0` |
| Alerts | `0` |
| Confidence-suppressed | `0` |
| Max score | `0.0` |
| Max raw score | `-12,048 ms` |
| Mean raw score | `-23,312 ms` |
| Pit-loss source | `100% circuit_median` |

Per session:

| Session | Rows | Evaluable | Main blocker | Max raw score |
|---|---:|---:|---|---:|
| Bahrain | `18,900` | `0` | missing XGB reference for attacker fresh `MEDIUM` | n/a |
| Monaco | `17,415` | `16,717` | score/physics | `-12,048 ms` |
| Hungary | `23,768` | `21,124` | score/physics | `-12,301 ms` |

Bahrain XGBoost unsupported detail:

```text
XGBoostPredictor requires reference_lap_time_ms for
session_normalized_delta predictions ('bahrain', 'MEDIUM').
```

That occurred `16,391` times. The trained feature set correctly excludes
`reference_lap_time_ms` as a feature, but the delta target still needs a live
reference to reconstruct absolute lap time at runtime. In Bahrain, the undercut
projection often asks for fresh `MEDIUM` before the live session has a prior
clean `MEDIUM` reference.

For the sessions where XGBoost can evaluate:

| Session | p50 gap recoverable | max gap recoverable | pit loss | p50 current gap | best raw score |
|---|---:|---:|---:|---:|---:|
| Monaco | `1,446 ms` | `9,622 ms` | `20,414 ms` | `1,572 ms` | `-12,048 ms` |
| Hungary | `2,836 ms` | `9,682 ms` | `20,393 ms` | `2,758 ms` | `-12,301 ms` |

The score formula requires:

```text
gap_recuperable_ms > pit_loss_ms + current_gap_ms + margin_ms
```

With a ~20.4s pit loss, the model would need over 20s of cumulative short-horizon
pace advantage before the score becomes positive. The observed XGBoost
projections never get close.

## Label Audit

Command:

```bash
docker compose run --rm \
  -v /Users/gabo/Developer/ITAM/Fuentes/f1_strategy_engine:/work \
  -w /work \
  -e PYTHONPATH=/work/backend/src \
  -e DATABASE_URL=postgresql+psycopg://pitwall:pitwall@db:5432/pitwall \
  backend python scripts/audit_undercut_labels.py \
  --predictor xgboost \
  --session bahrain_2024_R \
  --session monaco_2024_R \
  --session hungary_2024_R
```

Summary:

| Source | Labels | Unobservable by engine |
|---|---:|---:|
| Replay backtest labels | `25` | `21` |
| DB `known_undercuts` labels | `0` | `0` |

Per session:

| Session | Backtest labels | Observable exact-pair labels | Unobservable labels |
|---|---:|---:|---:|
| Bahrain | `13` | `0` | `13` |
| Monaco | `2` | `0` | `2` |
| Hungary | `10` | `4` | `6` |

The current backtest labels are generated from pit-in/final-position replay
logic, not from a curated known-undercut table. Most labels never appear as an
exact attacker-defender pair inside the engine's K-lap decision window, so the
model is penalized for events it could not have alerted on.

For the four observable Hungary labels, scores were still deeply negative:

| Label | Matching decision rows | Max gap recoverable | Best raw score |
|---|---:|---:|---:|
| `PER` vs `RUS`, lap 28 | `89` | `4,626 ms` | `-17,637 ms` |
| `RIC` vs `BOT`, lap 28 | `1` | `3,500 ms` | `-17,997 ms` |
| `GAS` vs `SAR`, lap 33 | `19` | `2,088 ms` | `-20,614 ms` |
| `MAG` vs `BOT`, lap 34 | `1` | `4,668 ms` | `-21,625 ms` |

So F1=0.0 is partly a label/backtest validity problem and partly a score
formula problem. It is not a confidence-threshold problem.

## Threshold And Physics Sweep

Command:

```bash
docker compose run --rm \
  -v /Users/gabo/Developer/ITAM/Fuentes/f1_strategy_engine:/work \
  -w /work \
  -e PYTHONPATH=/work/backend/src \
  -e DATABASE_URL=postgresql+psycopg://pitwall:pitwall@db:5432/pitwall \
  backend python scripts/sweep_undercut_thresholds.py \
  --predictor xgboost \
  --session bahrain_2024_R \
  --session monaco_2024_R \
  --session hungary_2024_R
```

Sweep grid:

- `K={2,3,5,8}`
- `margin_ms={0,250,500,1000}`
- `pit_loss_scale={0.8,1.0,1.2}`
- `cold_tyre_mode={current,half,none}`
- score threshold `0.0..1.0`
- confidence threshold `0.0..1.0`

Result:

| Metric | Value |
|---|---:|
| Sweep rows | `20,736` |
| Rows with at least one alert | `0` |
| Rows with nonzero recall | `0` |
| Max score across decomposition summaries | `0.0` |

Lowering thresholds cannot fix this. Even the permissive physics variants still
do not create a positive score.

## Projection Error

Command:

```bash
docker compose run --rm \
  -v /Users/gabo/Developer/ITAM/Fuentes/f1_strategy_engine:/work \
  -w /work \
  -e PYTHONPATH=/work/backend/src \
  -e DATABASE_URL=postgresql+psycopg://pitwall:pitwall@db:5432/pitwall \
  backend python scripts/diagnose_projection_error.py \
  --predictor xgboost \
  --session bahrain_2024_R \
  --session monaco_2024_R \
  --session hungary_2024_R
```

As-raced cumulative pair projection error:

| Horizon | Rows | MAE | Mean signed error | Max abs error |
|---:|---:|---:|---:|---:|
| K=1 | `34,609` | `921 ms` | `-498 ms` | `6,126 ms` |
| K=2 | `32,636` | `1,285 ms` | `-27 ms` | `10,821 ms` |
| K=3 | `30,858` | `1,847 ms` | `745 ms` | `13,340 ms` |
| K=5 | `27,745` | `3,093 ms` | `2,028 ms` | `24,169 ms` |
| K=8 | `23,605` | `4,746 ms` | `3,570 ms` | `28,631 ms` |

The model is useful as a pace simulator, but cumulative pair projection error
grows quickly with horizon. K=5 is already a several-second decision error
surface. That reinforces the need for a decision-calibrated score, not more
global lap-MAE tuning.

## Runtime Feature Parity

Command:

```bash
docker compose run --rm \
  -v /Users/gabo/Developer/ITAM/Fuentes/f1_strategy_engine:/work \
  -w /work \
  -e PYTHONPATH=/work/backend/src \
  -e DATABASE_URL=postgresql+psycopg://pitwall:pitwall@db:5432/pitwall \
  backend python scripts/diagnose_xgb_runtime_features.py \
  --session bahrain_2024_R \
  --session monaco_2024_R \
  --session hungary_2024_R
```

Summary:

| Runtime feature issue | Count |
|---|---:|
| XGBoost runtime contexts | `120,166` |
| Delta prediction contexts | `120,166` |
| Missing live reference contexts | `19,274` |
| `team_code` unknown | `120,166` |
| `driver_pace_offset_missing` true | `120,166` |
| `lap_in_stint_ratio` missing | `120,166` |
| `gap_to_ahead_ms` missing | `2,640` |

Largest missing-reference bucket:

| Bucket | Missing contexts |
|---|---:|
| `bahrain_2024_R | attacker_fresh | MEDIUM` | `18,900` |

This explains why Bahrain had no evaluable XGBoost undercut decisions in the
score decomposition. It also confirms that runtime replay lacks `team_code`,
so pit-loss lookup always fell back to circuit median and XGBoost always encoded
team as `UNKNOWN`.

## Pair-Level Challenger And Random Forest

Existing challenger report:

| Model | Label surface | Rows | Precision | Recall | F1 | PR-AUC | Brier |
|---|---|---:|---:|---:|---:|---:|---:|
| XGBoost | proxy `undercut_viable` | `5,294` | `0.364` | `0.444` | `0.400` | `0.180` | `0.002` |
| XGBoost | observed `undercut_success` | `27` | `0.364` | `0.444` | `0.400` | `0.326` | `0.330` |
| Random Forest | proxy `undercut_viable` | `5,294` | `0.000` | `0.000` | `0.000` | `0.200` | `0.002` |

Random Forest is not the right next default. It did not beat XGBoost on the
available proxy decision task, and the observed-label validation surface is too
sparse to promote any pair-level model to runtime.

## Exact Failure Mode

1. The lap-level XGBoost model is better than scipy on replay pace MAE, but the
   undercut engine score is still always zero.
2. Confidence is not suppressing alerts.
3. In Bahrain, XGBoost often cannot evaluate attacker fresh-`MEDIUM` contexts
   because the live session-normalized reference is unavailable.
4. In Monaco and Hungary, XGBoost can evaluate most pairs, but projected
   recoverable gap is far below `pit_loss + current_gap + margin`.
5. The current replay labels are mostly not observable by the engine as exact
   pairs in the K-lap decision window.
6. The label target is pit-cycle success, while the score formula subtracts the
   attacker's full pit loss without modeling the defender's later stop. That is
   a target mismatch.

## Recommended Next PR

Do not retune XGBoost again first. The next PR should do this:

1. Fix backtest label construction and scoring:
   - Populate or rebuild `known_undercuts` for the demo sessions.
   - Score only labels observable as exact relevant pairs before the pit
     decision.
   - Separate observed pit-cycle success labels from proxy/final-position labels.

2. Recalibrate the undercut physics:
   - Replace the current score with a pit-cycle expected-gain formulation.
   - Model defender response window explicitly instead of requiring the attacker
     to recover the full pit loss before the defender stops.
   - Keep current thresholds frozen until the new score is calibrated.

3. Fix runtime feature parity:
   - Add `team_code` to SQL replay lap events or enrich `RaceState` from drivers.
   - Derive `lap_in_stint_ratio` in projection/runtime contexts.
   - Add a safe reference fallback or explicit no-reference reason for
     session-normalized delta predictions.

4. Keep pair-level XGBoost and Random Forest offline until observed labels are
   credible.

## Artifacts

Generated local artifacts:

- `reports/ml/undercut_score_decomposition.json`
- `reports/ml/undercut_score_decomposition.csv`
- `reports/ml/undercut_label_audit.json`
- `reports/ml/undercut_projection_error.json`
- `reports/ml/undercut_threshold_sweep_expanded.json`
- `reports/ml/xgb_runtime_feature_parity.json`

Those generated JSON/CSV artifacts remain ignored. This markdown report is the
tracked summary.
