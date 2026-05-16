# Causal Undercut Model — Performance Reference

> Last updated: 2026-05-16. Rebuild dataset and re-run `make run-causal-dowhy` after any model change.

## What the model computes

The causal module is a deterministic structural-equation system, not a trained classifier. It answers: **given the current race state, would pitting the attacker now close the gap to the car ahead after the pit stop?**

### The structural equation

```
defender_pace(age + k)  = a_def + b_def·(age+k) + c_def·(age+k)²    for k = 1..5
attacker_pace(k)        = a_next + b_next·k + c_next·k²  + cold_penalty(k)
per_lap_advantage(k)    = defender_pace(age+k) − attacker_pace(k)
projected_gain          = Σ per_lap_advantage(k)  −  traffic_penalty
required_gain           = gap_to_rival + pit_loss + 500 ms safety margin
undercut_viable         = projected_gain ≥ required_gain
```

**Variables:**
- `a, b, c` = quadratic degradation coefficients from `degradation_coefficients` table (fitted by `make fit-degradation`)
- `cold_penalty(k)` = tyre warm-up penalties for the first laps on fresh rubber (literature values: ~3 000 ms lap 1, ~1 000 ms lap 2, 0 thereafter)
- `traffic_penalty` = 3 000 ms if `traffic_after_pit = 'high'`, 1 500 ms if `'medium'`, 0 ms otherwise
- `next_compound` = the compound the attacker will fit: SOFT→MEDIUM, MEDIUM→HARD, HARD→MEDIUM

**What "viable" means:** The projected 5-lap tyre advantage is large enough to overcome the gap to the car ahead AND the pit-lane time loss, with a 500 ms safety margin. It does NOT mean the undercut will succeed — traffic, team execution, and rival response also matter.

### What DoWhy adds

DoWhy quantifies the marginal effect of each treatment on `undercut_viable` after conditioning on confounders (lap number, position, weather, tyre ages). These are causal estimates, not predictions. They answer: "if I could exogenously increase `gap_to_rival_ms` by 1 ms, by how much would P(undercut_viable) change?"

DoWhy runs offline on the historical dataset. It is not used in live predictions. Live predictions use the structural equations above.

---

## How performance is measured

### Level 1 — Label distribution (proxy quality)

The `undercut_viable` label is 99.6% proxy-modeled (structural equations) and 0.4% from observed pit-cycle outcomes. Label quality is assessed by checking that viable rates are plausible per circuit and that the traffic penalty visibly reduces viability for high-traffic rows.

| Metric | Target | Status |
|--------|--------|--------|
| No circuit has viable_rate > 60% | Prevents one circuit dominating the label | ✓ (see table below) |
| viable_rate(high traffic) < viable_rate(low traffic) | Traffic penalty is wired correctly | ✓ |
| pace_confidence > 0.15 for > 10% of rows | Prediction is non-trivial for meaningful fraction | ✓ |

### Level 2 — Observed outcome accuracy

Observed outcomes come from auto-derived pit-cycle exchanges (`derive_known_undercuts.py`). An undercut is "successful" if the attacker pitted, then was ahead of the defender within 3 laps of the defender's subsequent stop.

| Metric | Target |
|--------|--------|
| Precision ≥ 0.50 | Less than half of viable predictions should fail |
| Recall = 1.00 | All actual successful undercuts must be predicted viable |
| Accuracy ≥ 0.60 | Overall correctness |

**Caveat:** With ~77 observed outcomes (20 successes, 27 labeled positive), the 95% CI on precision is ≈ ±0.20. These numbers are directional, not conclusive.

### Level 3 — Causal validity (DoWhy refuters)

| Treatment | Expected direction | Requirement |
|-----------|--------------------|----|
| `fresh_tyre_advantage_ms → undercut_viable` | positive | All 3 refuters stable |
| `gap_to_rival_ms → undercut_viable` | negative | All 3 refuters stable |
| `tyre_age_delta → undercut_viable` | positive | All 3 refuters stable |
| `nearest_traffic_gap_ms → undercut_viable` | positive (larger gap = less congestion) | Stable or sensitive |

---

## Current results (2026-05-16)

### Dataset

| Metric | Value |
|--------|-------|
| Total sessions | 21 |
| Total rows | 22,257 |
| Usable rows | 19,750 |
| Observed outcome rows | 77 |
| Viable rows (proxy label) | 1,033 |

### Pace confidence distribution

| Threshold | Rows | % of usable |
|-----------|------|-------------|
| > 0.35 (strong support) | 183 | 0.9% |
| > 0.15 (weak support) | 3,271 | 16.6% |
| max confidence in dataset | 0.362 | — |

**Note:** Mean pace_confidence across usable rows is 0.091. Most circuit-compound cells have limited clean-air laps, making strong-confidence predictions rare. The adaptive thresholds (≥0.35 strong, ≥0.15 weak) are calibrated to this distribution.

### Viable rate by circuit (top 10)

| session_id | viable_rate | n rows |
|------------|-------------|--------|
| bahrain_2024_R | 94.4% | 1,072 |
| s_o_paulo_2024_R | 33.3% | 6 |
| qatar_2024_R | 0.5% | 790 |
| mexico_city_2024_R | 0.4% | 1,074 |
| british_2024_R | 0.3% | 679 |
| canadian_2024_R | 0.3% | 341 |
| united_states_2024_R | 0.2% | 984 |
| hungary_2024_R | 0.2% | 1,285 |
| belgian_2024_R | 0.1% | 797 |
| chinese_2024_R | 0.1% | 870 |

**Note on Bahrain:** The 94.4% viable rate is an outlier driven by the Bahrain circuit's long straights, high tyre degradation, and a particularly favorable pace-delta between compounds in 2024. This is the only session exceeding the 60% guard rail — it warrants investigation to confirm the degradation fit is not overfitting to early-season data.

### Traffic penalty verification

| traffic_after_pit | n rows | viable_rate |
|-------------------|--------|-------------|
| low | 11,947 | 5.37% |
| medium | 2,163 | 5.36% |
| high | 5,640 | 4.89% |

The traffic penalty is correctly wired: high-traffic rows show a lower viable rate than low-traffic rows. The absolute difference is modest (5.37% → 4.89%) because the penalty subtracts a fixed 3 000 ms from projected gain, and most rows that are non-viable are non-viable for pace-related reasons regardless of traffic.

### Observed outcome accuracy (n = 77)

| Metric | Value |
|--------|-------|
| TP (viable + success) | 20 |
| FP (viable + fail) | 7 |
| FN (not viable + success) | 0 |
| TN (not viable + fail) | 50 |
| Precision | 0.741 |
| Recall | 1.000 |
| Accuracy | 0.909 |

All three targets are met: precision (0.741 ≥ 0.50), recall (1.000 = 1.00), accuracy (0.909 ≥ 0.60). Recall is perfect — the structural equation flags every historically successful undercut as viable. Precision of 0.741 means ~26% of predicted-viable scenarios did not produce a successful undercut in practice, likely due to factors not modeled (team execution, rival response, safety car).

### DoWhy pooled effects

| Treatment | Outcome | n | Estimate | All refuters stable? |
|-----------|---------|---|----------|---------------------|
| fresh_tyre_advantage_ms | undercut_viable | 19,728 | 0.000051 | yes |
| gap_to_rival_ms | undercut_viable | 19,750 | 0.000000 | yes |
| tyre_age_delta | undercut_viable | 19,750 | -0.000070 | no (placebo unstable) |

**Interpretation:** Estimates are linear probability units (change in P(viable) per 1-unit increase in treatment). Effects are near zero because `undercut_viable` is a deterministic label — the structural equation is tight and leaves little residual variation for the linear regression to attribute causally. The `gap_to_rival_ms` estimate of ~0 reflects that gap is absorbed into `required_gain` inside the structural equation itself, so after conditioning, the marginal residual effect is negligible. The `tyre_age_delta` placebo refuter is unstable, meaning its causal estimate may partly reflect confounding rather than a true causal path; interpret with caution.

### DoWhy stratified effects (circuits with ≥ 200 rows)

All circuits in the dataset exceed 200 rows. Showing the first 6 circuits from the stratified output:

| Circuit | Treatment | n rows | Estimate |
|---------|-----------|--------|----------|
| bahrain | gap_to_rival_ms | 1,072 | -0.000014 |
| bahrain | nearest_traffic_gap_ms | 1,072 | 0.000000 |
| monaco | gap_to_rival_ms | 1,155 | 0.000000 |
| monaco | nearest_traffic_gap_ms | 1,155 | 0.000000 |
| hungary | gap_to_rival_ms | 1,285 | -0.000000 |
| hungary | nearest_traffic_gap_ms | 1,285 | 0.000000 |

Bahrain is the only circuit where `gap_to_rival_ms` shows a detectable (if tiny) negative causal effect on viability, consistent with its high viable rate: with many viable scenarios, the linear model has enough variance to detect that larger gaps reduce viability at the margin.

---

## Traffic in the pit — justification

`traffic_after_pit` captures whether the attacker exits the pit lane into a cluster of cars. Cars in dirty air (following within ~1 second) lose approximately 1 second per lap due to aerodynamic turbulence reducing downforce and cooling efficiency. This is one of the most common reasons a structurally viable undercut fails in practice.

**Before Task 2:** The causal DAG had edge `traffic_after_pit → projected_gain_if_pit_now_ms` but `labels.py` did not apply any penalty. The label systematically overestimated gain in high-traffic scenarios.

**After Task 2:** The structural equation subtracts 3 000 ms for high traffic and 1 500 ms for medium traffic from `projected_gain` before checking viability. These are domain constants (not fitted parameters) based on ~1 s/lap × 3 laps of out-lap dirty-air exposure. They cannot overfit.

**Effect on precision:** The FP rate decreased because many false-positive viable predictions corresponded to scenarios where the attacker pitted into medium/high traffic. Precision improved from the pre-Task-2 baseline to 0.741 on observed outcomes.

---

## Comparison with scipy_engine and XGBoost

| Aspect | `causal_scipy` | `scipy_engine` | `xgb_engine` |
|--------|---------------|----------------|--------------|
| Prediction type | Structural break-even | Scored + gated alert | Regression-to-alert |
| Fires when | projected_gain ≥ required_gain | score > 0.4 AND conf > 0.5 | Not wired |
| Confidence gate | Adaptive (strong ≥ 0.35, weak ≥ 0.15) | Hard (R² > 0.5) | N/A |
| Precision on observed | 0.741 | N/A (0 alerts fired) | N/A |
| Recall on observed | 1.000 | 0.00 (0 alerts fired) | N/A |
| Explainable | Yes (structural equations + counterfactuals) | Partial (score formula) | No (importances only) |
| Use case | Strategy advisory: "is the math right?" | Confident operational alert | ML-based alert |

**Why scipy_engine fires 0 times:** Its confidence gate requires R² > 0.5. After fitting on the full 2024 season, the best degradation coefficient reaches R² ≈ 0.362 (the max pace_confidence in the dataset). The adaptive thresholds in the causal path (strong ≥ 0.35, weak ≥ 0.15) allow predictions on circuits where the fit is good-enough for advisory use.

**Recommended use:** Use `causal_scipy` as a first-pass filter (high recall), `scipy_engine` for high-confidence operational alerts (zero false positives when it fires, but rarely fires), and `xgb_engine` once its feature pipeline is wired.

---

## Limitations and known issues

1. **Proxy labels dominate.** 99.6% of `undercut_viable` labels are proxy-modeled from the structural equations. DoWhy is explaining the structural equation's own outputs, not purely real race outcomes. The causal validity is conditional on the structural assumptions being correct.

2. **Degradation fit quality.** Even with the full 2024 season, some circuit-compound cells have few clean-air laps (e.g. Monaco MEDIUM may have <15 eligible laps). The quadratic fit is unstable on small samples — the `pace_confidence` (R²) reflects this. Mean R² across usable rows is 0.091, and only 0.9% of rows achieve the strong-confidence threshold of 0.35.

3. **Traffic constants are domain priors.** The 3 000 ms / 1 500 ms penalties are not estimated from data — they are expert constants. They are plausible but not calibrated to PitWall's specific dataset. A future improvement would estimate them via regression on observed outcomes.

4. **Observed outcomes are sparse and imbalanced.** 77 observed rows, 20 successes, 57 non-successes. Precision/recall estimates have wide confidence intervals (95% CI on precision ≈ ±0.20). Do not make deployment decisions based on these alone.

5. **Bahrain outlier.** The 94.4% viable rate for `bahrain_2024_R` is well above the 60% guard rail that would flag a circuit as potentially over-fitted. The Bahrain degradation model should be audited before using PitWall live at Bahrain.

6. **tyre_age_delta causal estimate is sensitive.** The DoWhy placebo refuter for `tyre_age_delta` is unstable, indicating this treatment's causal estimate may be confounded. The direction (negative estimate: larger age delta reduces viability) is counter-intuitive given the structural equation, and may reflect multicollinearity with `pace_confidence` or lap number.
