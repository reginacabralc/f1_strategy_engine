# Stream B — Causal undercut viability module

> Owner: Stream B. Inputs: Stream A data/ML artifacts. Consumers: engine/API/WS and later Stream C explanations.
> Status: Phase 1-10 implemented for the independent `causal_scipy` MVP.
> API/WS wiring remains intentionally deferred until the output shape is accepted.

## Goal

Add an explainable causal layer for:

```text
undercut_viable = yes/no
```

The unit of observation is `(session_id, attacker_driver, rival_driver, lap_number)`.
This module does not replace `ScipyPredictor`, `XGBoostPredictor`, or
`evaluate_undercut()`. It sits beside the existing undercut engine to explain
why a live pair looks viable or not, and to run offline causal analyses with
DoWhy.

## Decision Locked

We will implement the causal graph module as an **independent alternative**
to compare against the current XGBoost path.

Explicit decisions:

- XGBoost is **not required** to build the causal graph.
- XGBoost must **not define** the DAG edges, treatments, outcomes, or
  confounders.
- The DAG is built from motorsport/domain assumptions and variables available
  in PitWall data.
- The first causal MVP should use transparent, auditable inputs:
  `ScipyPredictor`, degradation coefficients, pit-loss estimates, reconstructed
  gaps, tyre deltas, race phase, weather, and traffic proxies.
- XGBoost may later be used only as an optional pace-estimation variant inside
  a node such as `expected_pace`, never as the source of causal structure.
- The comparison target is:

```text
Scipy undercut engine   vs   XGBoost undercut engine   vs   Causal graph module
```

The reason for this separation is important: current XGBoost holdout metrics are
weak on the three-race demo set, so the causal graph module should not inherit
XGBoost errors. The causal module should provide a second, explainable decision
path for `undercut_viable`, not a wrapper around the current ML model.

## Why This Belongs To Stream B

Stream B owns the replay loop, `RaceState`, relevant-pair selection, undercut
scoring, alerts, FastAPI, and WebSocket. The causal module is a decision/explainability
layer over a live driver-rival-lap observation, so Stream B owns implementation.
Stream A remains the provider of historical lap data, degradation coefficients,
pit-loss estimates, and XGBoost pace artifacts.

## Non-Goals

- Do not replace XGBoost or `PacePredictor`.
- Do not use XGBoost to construct the causal graph.
- Do not make XGBoost a mandatory dependency of the causal MVP.
- Do not use DoWhy as a classifier.
- Do not treat feature importance as causal evidence.
- Do not add new endpoints, WebSocket fields, DB schema, or dependencies until
  the data/label design is accepted.
- Do not use variables that are only known after the decision as live features.

## Current Data Audit

Available in schema / runtime:

- `laps`: lap time, sectors, compound, tyre age, pit-in/out flags, validity,
  track status, position, optional gaps, timestamp.
- `stints`: reconstructed stint number, compound, lap range, tyre age at start.
- `weather`: track temp, air temp, humidity, rainfall.
- `pit_stops`: pit lap, duration when available, new compound, optional pit loss.
- `degradation_coefficients`: quadratic degradation by `(circuit_id, compound)`.
- `pit_loss_estimates`: pit loss by circuit/team plus circuit/global fallback.
- `driver_skill_offsets`: persisted driver pace offsets.
- `RaceState`: live position, smoothed gap-to-ahead, last lap, compound, tyre
  age, stint number, laps in stint, pit status, track status, weather.
- `evaluate_undercut()`: projected gain, score, confidence, pit loss, current gap.

Important gaps:

- FastF1 lap cache has lap/sector/compound/tyre/track-status/position/weather
  columns, but not direct `gap_to_leader_ms` or `gap_to_ahead_ms`.
- The schema and engine support gaps, but current ingestion does not derive
  them. Stream B added a repeatable FastF1 lap-end timestamp reconstruction
  command: `make reconstruct-race-gaps`.
- `OpenF1Feed` is a V2 stub. Live in V1 means replayed historical FastF1.
- `known_undercuts` exists in schema, but curated rows and backtest runner are
  not implemented yet.
- DoWhy is not currently a backend dependency; adding it requires an ADR.

Current pre-Phase 3 DB prep status on the local DB volume:

- `gap_to_leader_ms`: populated for 3,717 / 3,721 lap rows.
- `gap_to_ahead_ms`: populated for 3,512 / 3,721 lap rows.
- Global `gap_to_ahead_ms` coverage is 94.4%, above the Phase 3 threshold.
- `degradation_coefficients`: 8 rows fitted.
- `pit_loss_estimates`: 28 rows fitted.
- `driver_skill_offsets`: 103 rows fitted and validated.
- `known_undercuts`: 35 rows auto-derived from observed pit-cycle exchanges
  (`13` successful, `22` unsuccessful). Human curation can still refine later.

Phase 3 may start from this volume. Every dataset row must still carry gap
source/confidence flags because the gap source is reconstructed, not direct
interval telemetry.

## Variable Inventory

### Available Now

- `session_id`, `season`, `circuit_id`, `lap_number`, `total_laps`
- `position`, `lap_time_ms`, `sector_1_ms`, `sector_2_ms`, `sector_3_ms`
- `compound`, `tyre_age`, `stint_number`, `laps_in_stint`
- `is_pit_in`, `is_pit_out`, `is_valid`, `track_status`
- `track_temp_c`, `air_temp_c`, `humidity_pct`, `rainfall`
- `pit_loss_ms` from `pit_loss_estimates` fallback lookup
- `degradation_estimate` through `PacePredictor` / degradation coefficients
- `driver_pace_offset_ms` from `driver_skill_offsets` when fitted
- `undercut_score`, `estimated_gain_ms`, `confidence` from `evaluate_undercut()`

### Derivable Now

- `laps_remaining = total_laps - lap_number`
- `race_phase` / `race_progress`
- `fuel_proxy = 1 - lap_number / total_laps`
- `current_gap_to_car_ahead` and `gap_to_rival`, from reconstructed FastF1
  lap-end timestamp gaps
- `current_gap_to_car_behind`, from adjacent field order and reconstructed gaps
- `tyre_age_delta = defender.tyre_age - attacker.tyre_age`
- `fresh_tyre_advantage` from projected defender worn pace minus attacker fresh pace
- `projected_gain_if_pit_now`, `projected_gap_after_pit`,
  `required_gain_to_clear_rival`
- `undercut_window_open` from break-even within `K_MAX`
- `traffic_after_pit` / `clean_air_potential` as coarse proxies from projected
  pit-exit position against reconstructed field gaps
- `field_spread` from reconstructed gaps
- `number_of_pit_stops_already` from `stint_number - 1`
- `safety_car_status`, `virtual_safety_car_status`, `yellow_flag` from
  `track_status`

### Ideal Future

- True live OpenF1 intervals/gaps and pit-out traffic at sub-lap resolution
- Overtake difficulty by circuit/DRS/train context
- Teammate and team strategy context
- Remaining tyre sets / compound availability
- Mandatory compound rule status beyond simple dry-compound inference
- Rival likely pit window learned from strategy history
- Real dirty-air / DRS / ERS / car-damage telemetry
- Robust multi-season known-undercut labels

### Not Recommended As Live Causal Inputs

- `pit_now` as a feature for `undercut_viable` because it is downstream of the
  viability assessment and team choice.
- `pit_decision` as a feature because it is the system recommendation.
- `undercut_success` as a feature because it is future outcome.
- Final classification, final gaps, post-race positions, or future pit laps.
- XGBoost feature importance as a substitute for causal effect.

## Causal Problem Definition

- Unit: `driver-rival-lap`.
- Main decision target: `undercut_viable`.
- Operational definition: undercut is viable on lap `t` if the attacker, by
  pitting now against the relevant rival, has a documented and model-supported
  opportunity to gain the pit cycle before the rival stops or within a short
  window `N` laps, after pit loss, current gap, cold-tyre penalty, traffic proxy,
  track status, and confidence gates.
- Recommendation output: `pit_decision`, derived after viability and other
  strategy constraints; never the causal target.

Treatment candidates:

- `fresh_tyre_advantage`
- `gap_to_rival`
- `traffic_after_pit`
- `tyre_age_delta`
- `pit_now`, only for observed historical effect on `undercut_success`

Outcome candidates:

- `undercut_viable` for explaining modeled viability.
- `undercut_success_within_n_laps` for executed stops.
- `position_gain_after_pit_window`.
- `gap_delta_to_rival_after_pit_window`.

Confounders:

- `circuit_id`, `race_phase`, `lap_number`, `laps_remaining`
- `track_temp_c`, `air_temp_c`, `rainfall`, `track_status`
- attacker/rival tyre compound and age
- attacker/rival pace/degradation estimates
- current position, gap, field spread, traffic proxy
- pit loss estimate

## Initial DAG

```text
circuit_id -> pit_loss_estimate
circuit_id -> overtake_difficulty_proxy
circuit_id -> degradation_estimate

track_temp_c -> degradation_estimate
air_temp_c -> degradation_estimate
rainfall -> track_status
track_status -> undercut_viable

tyre_compound -> degradation_estimate
tyre_age -> degradation_estimate
degradation_estimate -> current_pace

rival_tyre_compound -> rival_degradation_estimate
rival_tyre_age -> rival_degradation_estimate
rival_degradation_estimate -> rival_expected_pace

current_pace -> fresh_tyre_advantage
rival_expected_pace -> fresh_tyre_advantage
tyre_age_delta -> fresh_tyre_advantage

gap_to_rival -> projected_gap_after_pit
pit_loss_estimate -> projected_gap_after_pit
traffic_after_pit -> projected_gain_if_pit_now
fresh_tyre_advantage -> projected_gain_if_pit_now

projected_gap_after_pit -> undercut_viable
projected_gain_if_pit_now -> undercut_viable
required_gain_to_clear_rival -> undercut_viable
laps_until_rival_expected_pit -> undercut_viable
laps_remaining -> undercut_viable
race_phase -> undercut_viable

undercut_viable -> pit_decision
pit_decision -> pit_now
pit_now -> undercut_success
```

Modeling caveat: when `undercut_viable` is a proxy produced by the existing
projector, causal estimates into that label explain the projectors assumptions,
not objective F1 truth. For observed causal effect of actually pitting, use
`pit_now -> undercut_success` with confounder adjustment.

## Historical Label Design

For each eligible `driver-rival-lap`:

1. Build attacker/rival pair from current race order. MVP uses consecutive
   ahead/behind pairs; later allow strategic rivals within a configurable gap.
2. Reconstruct or load current gap and field gaps.
3. Lookup pit loss for attacker circuit/team.
4. Project attacker fresh-tyre pace and rival worn-tyre pace for `N = 3..5`.
5. Estimate pit-exit position and traffic proxy.
6. Define `undercut_viable_label = 1` if projected gain clears:

```text
projected_gain_if_pit_now >= pit_loss + gap_to_rival + safety_margin
```

   within the window, with green-track, dry-compound, non-stale data, and
   confidence gates.
7. Mark this label as `proxy_modeled`, not observed causal truth.

For laps where the attacker actually pitted:

1. `pit_now = 1`.
2. Observe `undercut_success` over the next `N` laps or until both cars complete
   the pit cycle.
3. Success if the attacker exits ahead of the rival, gains net position versus
   the rival after the exchange, or improves gap by a documented threshold.

For laps where the attacker did not pit:

- `pit_now = 0`.
- `undercut_success` is unobserved/censored.
- `undercut_viable_label` can still be computed as a proxy with the projector,
  but must not be treated as observed causal success.

## DoWhy Use

DoWhy should be used offline to formalize assumptions and estimate selected
effects, not to make the primary live classification.

MVP analyses:

- `treatment='fresh_tyre_advantage'`, `outcome='undercut_viable'`
- `treatment='gap_to_rival'`, `outcome='undercut_viable'`
- `treatment='traffic_after_pit'`, `outcome='undercut_viable'`
- `treatment='pit_now'`, `outcome='undercut_success'` only on executed/censored
  historical pit opportunities

Methods:

- `backdoor.linear_regression` for continuous treatment prototypes.
- Propensity score matching/stratification for binary `pit_now`.
- For binary outcomes, document the limitation of linear probability estimates
  or use compatible logistic/statistical estimators where supported.

Refuters:

- random common cause
- placebo treatment
- data subset refuter

## Predictor Independence And Comparison

The causal module should support predictor/source variants, but the MVP default
is the independent transparent path:

```text
causal_scipy:
  expected_pace_source = ScipyPredictor / degradation_coefficients
  undercut_viable = DAG-informed rule + documented thresholds
  explanation = causal factors from the graph

causal_xgb_later:
  expected_pace_source = XGBoostPredictor
  undercut_viable = same DAG-informed rule
  status = optional comparison only after XGBoost runtime prediction is reliable
```

The first comparison should report:

- `scipy_engine`: existing `evaluate_undercut()` with `ScipyPredictor`.
- `xgb_engine`: existing `evaluate_undercut()` with `XGBoostPredictor`, only
  once runtime prediction is implemented.
- `causal_scipy`: causal graph module using transparent pace/degradation inputs.

Metrics:

- precision, recall, F1 against curated historical undercuts when available,
- lead time in laps,
- false positives/false negatives by circuit and race phase,
- agreement/disagreement table between `scipy_engine`, `xgb_engine`, and
  `causal_scipy`,
- explanation sanity checks for top causal factors.

If curated undercuts are still missing, compare first against proxy
`undercut_viable_label` and label the result explicitly as proxy evaluation, not
ground truth.

## Simulation, Prediction, And Explanation

The causal graph module must support three related but distinct capabilities:

### 1. Predict Current Viability

Given the current live/replay observation:

```text
RaceState + attacker + rival + lap_number
```

compute:

```text
undercut_viable = yes/no
required_gain_ms = pit_loss + gap_to_rival + safety_margin
projected_gain_ms = projected fresh-tyre advantage minus traffic penalty
support_level = strong | weak | insufficient
```

This prediction is not produced by training the graph. It is produced by the
DAG-informed structural equations and transparent parameters.

### 2. Simulate Counterfactual Scenarios

The module should be able to run "what-if" scenarios by intervening on selected
variables while holding the rest of the observation fixed. Examples:

```text
do(pit_now = true)
do(pit_lap = current_lap + 1)
do(traffic_after_pit = low)
do(pit_loss_estimate = pit_loss_estimate + 1000)
do(fresh_tyre_advantage = fresh_tyre_advantage + 500)
```

MVP scenarios:

- base case: evaluate current lap as observed,
- pit now,
- pit next lap,
- pit now with high pit-exit traffic,
- pit now with low pit-exit traffic,
- pit loss sensitivity `±1000 ms`.

Expected output shape:

```text
scenario_name
undercut_viable
required_gain_ms
projected_gain_ms
projected_gap_after_pit
main_limiting_factor
```

This is the main strategic value of the causal graph: it can answer "what would
happen if we changed one condition?", not only "what pattern did a predictor
learn historically?"

### 3. Explain The Decision

For each prediction or simulation, emit a compact explanation based on the DAG
nodes that most constrained or enabled viability:

```text
Undercut viable because gap_to_rival is inside the pit-loss-adjusted window,
fresh_tyre_advantage is high, rival tyre age is high, and projected pit-exit
traffic is low.
```

When data support is weak, say so explicitly:

```text
Undercut not supported: gap_to_rival is large and projected traffic_after_pit is
high. Support is weak because gap_to_rival was reconstructed, not observed.
```

## Live Use

On each `lap_complete`, build a `driver-rival-lap` observation for every relevant
pair. The live module may produce:

```text
undercut_viable: bool
causal_explanation: list[str]
counterfactuals: list[scenario_result]
support_level: "strong" | "weak" | "insufficient"
top_factors: gap_to_rival, fresh_tyre_advantage, traffic_after_pit, tyre_age_delta
```

Example explanation:

```text
Undercut viable because gap_to_rival is inside the pit-loss-adjusted window,
fresh_tyre_advantage is high, rival tyre age is high, and projected pit-exit
traffic is low.
```

Live language must be careful: say "consistent with the causal model" or
"model-supported" unless the historical refutation tests support stronger claims.

## Proposed Future Files

```text
backend/src/pitwall/causal/
  __init__.py
  graph.py
  dataset_builder.py
  labels.py
  estimators.py
  live_inference.py
  explain.py

backend/tests/unit/causal/
  test_causal_dataset.py
  test_causal_graph.py
  test_undercut_labels.py

docs/CAUSAL_MODEL.md
```

Do not add these files until the conceptual gate is accepted.

## Phased Plan

### Phase 1 — Repo/Data Audit

- [x] Read current plans, docs, schema, replay, engine, XGBoost, degradation,
  pit-loss, frontend surface, and generated data locations.
- [x] Add reproducible audit command:
  `make audit-causal-inputs` / `scripts/audit_causal_inputs.py`.
- [x] Verify in a running DB whether demo sessions have non-null gap fields.
  Audit result: all three demo sessions have `0` populated `gap_to_leader_ms`
  rows and `0` populated `gap_to_ahead_ms` rows.
- [x] Define the gap reconstruction gate before causal labels. If the audit
  reports `GAP_RECONSTRUCTION_REQUIRED`, Phase 3 must reconstruct lap-end
  timestamp gaps or load another trusted gap source before labels are built.
- [x] Record current DB artifact readiness. Audit result: raw ingest exists
  (`3,721` lap rows), but `degradation_coefficients`, `pit_loss_estimates`,
  `driver_skill_offsets`, and `known_undercuts` are empty in the audited DB
  volume.
- [x] Add and run lap-end timestamp gap reconstruction:
  `make reconstruct-race-gaps`. Final audited coverage:
  `gap_to_leader_ms=99.9%`, `gap_to_ahead_ms=94.4%`.
- [x] Fit required pre-Phase 3 artifacts on the same DB volume:
  `degradation_coefficients=8`, `pit_loss_estimates=28`,
  `driver_skill_offsets=103`.
- [x] Add and run observed pit-cycle known-undercut derivation:
  `make derive-known-undercuts`. Final audited result:
  `known_undercuts=35` (`13` successful, `22` unsuccessful).

### Phase 2 — Variable Inventory And Assumptions

- [x] Freeze a table of variables with status: `available_now`,
  `derivable_now`, `ideal_future`, `not_recommended` in
  `docs/CAUSAL_MODEL.md`.
- [x] Explicitly document historical vs live availability in
  `docs/CAUSAL_MODEL.md`.
- [x] Document leakage rules for pair-level causal data in
  `docs/CAUSAL_MODEL.md`.

### Phase 3 — Historical Driver-Rival-Lap Dataset

- [x] Use valid reconstructed `gap_to_ahead_ms` / `gap_to_leader_ms`; keep the
  small number of missing-position rows explicitly marked as insufficient support.
- [x] Include `gap_source='reconstructed_fastf1_time'` for lap-line timestamp gaps.
- [x] Join auto-derived `known_undercuts` only as evaluation/outcome data, never
  as live input features.
- [x] Build offline dataset rows from `laps`, `stints`, `weather`,
  `pit_loss_estimates`, `degradation_coefficients`, and `driver_skill_offsets`.
- [x] Start with consecutive race-order rivals only.
- [x] Include source/confidence flags for derived gaps and proxy labels.
- [x] Add repeatable build command: `make build-causal-dataset`.
  Latest result: `3,512` rows, `3,512` usable rows, `1,026`
  `undercut_viable=true` rows, and `14` observed success rows.

### Phase 4 — Label Construction

- [x] Implement and test `undercut_viable_label` as a documented proxy.
- [x] Implement and test `undercut_success` only for executed pit cycles.
- [x] Keep censored/unobserved outcomes explicit.
- [x] Keep XGBoost completely out of causal labels: no XGBoost features,
  predictions, or feature importances are used.

### Phase 5 — DAG Documentation

- [x] Encode the initial DAG in DOT/GML/string.
- [x] Document every edge and confounder in `docs/CAUSAL_MODEL.md`.
- [x] Mark speculative/future variables as unavailable.
- [x] Add DAG unit tests for export and acyclic validation.

### Phase 6 — DoWhy Prototype

- [x] Add ADR for `dowhy` dependency.
- [x] Create a small reproducible notebook/script over the driver-rival-lap
  dataset.
- [x] Estimate simple effects first; no complex causal ML.
- [x] Use the `causal_scipy` path first so results are independent from XGBoost.
- [x] Add repeatable command: `make run-causal-dowhy`.
- [x] Keep binary outcome limitation documented as linear probability estimate.

### Phase 7 — Refutation Tests

- [x] Add random common cause refuter.
- [x] Add placebo treatment refuter.
- [x] Add data subset refuter.
- [x] Report when estimates are unstable or unsupported.

### Phase 8 — Live Lap-by-Lap Integration

- [x] Convert current `RaceState` pair into causal observation.
- [x] Reuse `evaluate_undercut()` projections rather than duplicating math.
- [x] Keep causal live inference behind a separate module/output so it can be
  compared against XGBoost instead of depending on it.
- [x] Produce current-lap `undercut_viable` prediction from structural equations.
- [x] Produce counterfactual scenario results for pit-now, pit-next-lap,
  traffic-high/low, and pit-loss sensitivity.
- [x] Return explainability metadata without changing alert semantics first.

### Phase 9 — Explainability Output

- [x] Produce compact human-readable explanations.
- [x] Add confidence/support wording.
- [x] Explain both the base-case prediction and each counterfactual scenario.
- [x] Later coordinate with Stream C before adding UI/WS fields.

### Phase 10 — Tests And Documentation

- [x] Unit-test dataset construction, graph shape, label logic, and live
  observation conversion.
- [x] Update `docs/CAUSAL_MODEL.md`.
- [x] If API/WS shape changes, update `docs/interfaces/` in the same PR.
  No API/WS shape changed in this phase, so no interface document update was
  required.

### Post-Phase 10 Corrections

- [x] Add a reproducible extended-data command:
  `make prepare-causal-extended-data`.
- [x] Add `scripts/fit_degradation.py --all-sessions` so newly ingested races
  can contribute degradation coefficients instead of being excluded by
  `--all-demo`.
- [x] Add manual known-undercut curation import:
  `make import-curated-known-undercuts`.
- [x] Add a tracked curation template:
  `data/curation/known_undercuts_curated.csv`.
- [x] Preserve auto-derived known undercuts while importing curated rows with
  `notes LIKE 'curated_manual_v1%'`.
- [x] Improve `traffic_after_pit` from a coarse projected-gap proxy to a
  field-aware projected pit-exit reconstruction.
- [x] Add engine disagreement reporting:
  `make compare-causal-engines`.
- [x] Report XGBoost comparison as unavailable until `XGBoostPredictor.predict()`
  has a runtime feature pipeline.
- [x] Verify one additional race ingestion locally:
  `mexico_city_2024_R`.

## MVP In 2 Days

1. Finish gap audit and reconstruction decision.
2. Document final variable inventory and DAG.
3. Build a minimal offline driver-rival-lap dataset for the three demo races.
4. Generate proxy `undercut_viable_label` using the existing undercut projector.
5. Run one DoWhy estimand/refuter pair on a small stable treatment, preferably
   `fresh_tyre_advantage -> undercut_viable`.
6. Produce the independent `causal_scipy` baseline for comparison against the
   existing XGBoost path.
7. Add deterministic simulation outputs for base case, pit-now,
   pit-next-lap, traffic-high/low, and pit-loss sensitivity.
8. Add explanations for prediction and simulations.
9. Add `docs/CAUSAL_MODEL.md` explaining limitations.
10. Do not wire live API/WS until the offline labels pass sanity checks.

## Acceptance Criteria

- Clear inventory of available, derivable, future, and rejected variables.
- Documented DAG.
- Historical `driver-rival-lap` dataset exists.
- Explicit definition of decision target, treatment candidates, outcomes, and
  confounders.
- DoWhy prototype runs on the dataset.
- At least one refutation test exists.
- XGBoost remains in place and is not replaced.
- XGBoost is not used to construct the DAG.
- The first causal MVP can run without XGBoost runtime predictions.
- Results can be compared as `scipy_engine` vs `xgb_engine` vs `causal_scipy`.
- The module can predict current-lap `undercut_viable`.
- The module can simulate documented counterfactual scenarios.
- The module explains why each base-case or simulated result is viable/not viable.
- Live loop can eventually emit a lap-by-lap explanation for `undercut_viable`.
- Stream B remains the explicit owner in `.claude/plans/stream-b-engine.md`.

## Critical Risks

- If gaps are not populated or reconstructed, `undercut_viable` cannot be
  labeled honestly.
- If `undercut_viable` is generated by the same heuristic used in live scoring,
  causal analysis explains the heuristic, not necessarily real race outcomes.
- `pit_now` is confounded by team strategy, position, tyres, traffic, and safety
  car context; naive estimates will be biased.
- Small data volume (three demo races) makes DoWhy estimates unstable. The MVP
  should emphasize assumptions, labels, and refuters over numeric certainty.
