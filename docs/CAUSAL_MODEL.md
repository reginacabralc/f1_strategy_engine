# Causal Undercut Viability Model

> Status: Phase 1-2 complete. This document freezes the initial repo/data
> audit, variable inventory, live/historical availability, leakage rules, and
> running-DB causal input audit result.

## Decision

The causal module is an independent, explainable decision path for:

```text
undercut_viable = yes/no
```

It is designed to compare against the existing XGBoost path, not to wrap it.
XGBoost is not required to build the causal graph, does not define causal edges,
and is not a dependency of the first causal MVP.

The first implementation target is:

```text
causal_scipy
```

using transparent inputs: degradation coefficients, `ScipyPredictor`,
pit-loss estimates, reconstructed gaps, tyre deltas, race phase, weather, and
traffic proxies.

## Phase 1 Repo/Data Audit

### Files And Modules Reviewed

- Project/process docs: `CLAUDE.md`, `AGENTS.md`, `README.md`,
  `docs/progress.md`, `docs/architecture.md`, `docs/walkthrough.md`.
- Plans: `.claude/plans/00-master-plan.md`,
  `.claude/plans/stream-a-data.md`, `.claude/plans/stream-b-engine.md`,
  `.claude/plans/stream-b-causal-undercut.md`.
- Interfaces: `docs/interfaces/db_schema_v1.sql`,
  `docs/interfaces/replay_event_format.md`,
  `docs/interfaces/websocket_messages.md`,
  `docs/interfaces/openapi_v1.yaml`.
- Engine/runtime: `backend/src/pitwall/engine/state.py`,
  `backend/src/pitwall/engine/undercut.py`,
  `backend/src/pitwall/engine/projection.py`,
  `backend/src/pitwall/engine/loop.py`,
  `backend/src/pitwall/engine/pit_loss.py`.
- Data/ML: `backend/src/pitwall/ingest/`, `backend/src/pitwall/degradation/`,
  `backend/src/pitwall/pit_loss/`, `backend/src/pitwall/pace_offsets/`,
  `backend/src/pitwall/ml/`.
- Repositories/scripts: `backend/src/pitwall/repositories/sql.py`,
  `scripts/ingest_season.py`, `scripts/fit_degradation.py`,
  `scripts/fit_pit_loss.py`, `scripts/fit_driver_offsets.py`,
  `scripts/build_xgb_dataset.py`, `scripts/train_xgb.py`.
- Reports: `notebooks/02_fit_degradation.md`,
  `notebooks/03_pit_loss_estimation.md`, `notebooks/04_driver_team_offsets.md`,
  `notebooks/05_xgb_dataset.md`, `notebooks/06_xgb_training.md`.

### Data Sources In The Current Repo

| Source | Current use | Live/historical | Notes |
|--------|-------------|-----------------|-------|
| FastF1 cache | Historical lap, weather, timing app data | Historical/replay | V1 source of truth. Cache exists locally for Bahrain, Monaco, Hungary 2024. |
| Timescale/Postgres | Normalized runtime and model tables | Historical and replay-live | Docker DB was not available in this environment, so DB contents must be audited by script. |
| ReplayFeed | Emits DB rows as live-like events | Replay-live | V1 live path. |
| OpenF1Feed | Stub only | Future live | Not usable in V1. |
| Local model files | XGBoost artifacts when trained | Historical/runtime | `models/` currently only has `.gitkeep` in this workspace. |

### Running-DB Audit Result

The audit was run against the existing project DB volume through a temporary
Timescale container on `localhost:55432`, because host port `5432` was occupied
by another local Postgres that rejected the repo credentials.

Result:

| Artifact | Rows |
|----------|------|
| sessions | 3 |
| laps | 3,721 |
| stints | 166 |
| pit_stops | 214 |
| weather | 512 |
| degradation_coefficients | 0 |
| pit_loss_estimates | 0 |
| driver_skill_offsets | 0 |
| known_undercuts | 0 |

Gap coverage:

| Session | Lap rows | `gap_to_leader_ms` rows | `gap_to_ahead_ms` rows |
|---------|----------|-------------------------|-----------------------|
| `bahrain_2024_R` | 1,129 | 0 | 0 |
| `hungary_2024_R` | 1,355 | 0 | 0 |
| `monaco_2024_R` | 1,237 | 0 | 0 |

Weather coverage is complete for available weather rows, and track status is
mostly populated (`GREEN` for 3,604 lap rows, `NULL` for 117 rows).

### Critical Gap Finding

The schema and engine support:

```text
gap_to_leader_ms
gap_to_ahead_ms
```

but the current FastF1 ingestion path does not derive these fields from the
available FastF1 lap columns. Local FastF1 cache inspection shows lap columns
such as `Time`, `LapTime`, sectors, `Compound`, `TyreLife`, `Stint`,
`TrackStatus`, and `Position`, but not direct gap columns.

The running DB audit confirms zero populated gap rows. This means Phase 3 cannot
honestly create `undercut_viable` labels until one of these is true:

1. DB audit confirms `gap_to_ahead_ms` is already populated by some existing
   local data path, or
2. gap reconstruction is implemented from cumulative timing data, or
3. another trusted gap source is loaded.

The repeatable audit command is:

```bash
make audit-causal-inputs
```

It reads whichever database `DATABASE_URL` points to; start the compose DB first
only when local port `5432` is free, or pass an alternate `DATABASE_URL`.

This report currently says `GAP_RECONSTRUCTION_REQUIRED`, so gap reconstruction
is a hard prerequisite for Phase 3. The same DB volume also needs
`make fit-degradation`, `make fit-pit-loss`, and `make fit-driver-offsets` before
the causal dataset can use pace, pit-loss, and driver-offset inputs.

## Phase 2 Variable Inventory

### Available Now

| Variable | Source | Historical | Replay-live | Notes |
|----------|--------|------------|-------------|-------|
| `session_id` | `sessions`, `laps`, `RaceState` | yes | yes | Stable identifier. |
| `season` | `events` | yes | no direct live field | Join by session. |
| `circuit_id` | `events`, session_start payload | yes | yes | Core confounder and pit-loss key. |
| `lap_number` | `laps`, `RaceState.current_lap` | yes | yes | Unit timestamp. |
| `total_laps` | `sessions`, session_start payload | yes | yes | Required for laps remaining. |
| `current_position` | `laps.position`, `DriverState.position` | yes | yes | Use as context/confounder, not outcome. |
| `lap_time_ms` | `laps`, `DriverState.last_lap_ms` | yes | yes | Valid laps only for pace. |
| `sector_1_ms`, `sector_2_ms`, `sector_3_ms` | `laps` | yes | event payload | Available but not currently used by engine. |
| `tyre_compound` | `laps.compound`, `DriverState.compound` | yes | yes | Dry compounds for MVP. |
| `tyre_age` | `laps.tyre_age`, `DriverState.tyre_age` | yes | yes | Must be online-replicable. |
| `stint_number` | `stints`, `DriverState.stint_number` | yes | yes | Derived by ingestion/runtime. |
| `laps_in_stint` | `DriverState` | no direct DB column | yes | Can derive from stints historically. |
| `track_status` | `laps`, `RaceState.track_status` | yes | yes | SC/VSC/rain guards. |
| `track_temp_c`, `air_temp_c`, `humidity_pct`, `rainfall` | `weather`, `RaceState` | yes | yes | Weather updates are not lap-synchronous. |
| `pit_loss_estimate` | `pit_loss_estimates`, `lookup_pit_loss()` | yes | yes | Weak quality on small demo data. |
| `degradation_estimate` | `degradation_coefficients`, `ScipyPredictor` | yes | yes | Low R2 documented. |
| `driver_pace_offset_ms` | `driver_skill_offsets` | yes | no direct live field | Historical prior, fold-safe care needed. |

### Derivable Now

| Variable | Derivation | Historical | Replay-live | Notes |
|----------|------------|------------|-------------|-------|
| `laps_remaining` | `total_laps - lap_number` | yes | yes | Safe. |
| `race_phase` | bucketed `lap_number / total_laps` | yes | yes | Confounder. |
| `fuel_proxy` | `1 - lap_number / total_laps` | yes | yes | Proxy only. |
| `gap_to_rival` | `gap_to_ahead_ms` or reconstructed cumulative time | conditional | conditional | Hard prerequisite. |
| `current_gap_to_car_ahead` | same as above | conditional | conditional | Must carry source flag. |
| `current_gap_to_car_behind` | reconstruct from adjacent order | conditional | conditional | Useful for traffic risk. |
| `tyre_age_delta` | `rival_tyre_age - attacker_tyre_age` | yes | yes | Good treatment candidate. |
| `fresh_tyre_advantage` | projected rival worn pace minus attacker fresh pace | yes | yes | Use `causal_scipy` first. |
| `projected_gain_if_pit_now` | sum fresh-tyre advantage over N laps | yes | yes | Structural equation. |
| `required_gain_to_clear_rival` | `pit_loss + gap + safety_margin` | conditional | conditional | Depends on gap. |
| `projected_gap_after_pit` | current gap + pit loss minus gains | conditional | conditional | Depends on gap. |
| `traffic_after_pit` | projected pit-exit position vs field gaps | conditional | conditional | Proxy, source flag required. |
| `clean_air_potential` | inverse of traffic proxy | conditional | conditional | Proxy. |
| `field_spread` | spread of reconstructed gaps | conditional | conditional | Proxy. |
| `number_of_pit_stops_already` | `stint_number - 1` | yes | yes | Safe. |
| `pit_now` | pit flags at current lap | yes | yes | Treatment only for success analysis, not viability input. |

### Ideal Future

| Variable | Why useful | Suggested proxy now |
|----------|------------|---------------------|
| Live OpenF1 intervals/gaps | Real gap timing without reconstruction | cumulative lap-time reconstruction |
| Overtake difficulty | Circuit and DRS/train context affects success | `circuit_id` fixed effects |
| Remaining tyre sets | Strategy feasibility | none reliable in current data |
| Mandatory compound rule status | Avoid illegal recommendations | dry-compound/stint history heuristic |
| Rival likely pit window | Determines if undercut window closes | stint age/race phase heuristic |
| Dirty air / DRS / ERS / damage | Explains pace deviations and traffic | `gap_to_ahead_ms`, `dirty_air_proxy_ms` |
| Team strategy context | Team orders/double-stack constraints | none reliable in current data |

### Not Recommended

| Variable | Reason |
|----------|--------|
| `pit_decision` as input | It is the system recommendation, downstream of viability. |
| `pit_now` as input to `undercut_viable` | Team action is downstream/confounded; use it only as treatment for observed success. |
| `undercut_success` as input | Future outcome. |
| Future pit laps | Post-decision leakage. |
| Final classification / final gaps | Post-race leakage. |
| XGBoost feature importance | Predictive attribution, not causal structure. |

## Live Vs Historical Availability Rules

1. A variable is live-eligible only if it can be computed from events observed at
   or before the current lap.
2. Historical features must be rebuilt using the same information boundary as
   live replay. Do not use future pit laps, final positions, or final gaps.
3. Any reconstructed variable must carry a source flag, for example:
   `observed`, `reconstructed`, `proxy`, or `missing`.
4. The first causal MVP should run without XGBoost runtime predictions.
5. `known_undercuts` supports evaluation, not feature construction.

## Leakage Rules For Pair-Level Causal Data

- Unit of observation is `(session_id, attacker_driver, rival_driver, lap_number)`.
- Features must be known at lap `t`.
- `undercut_viable_label` may be proxy-modeled from structural equations, but
  must be marked as `proxy_modeled`.
- `undercut_success` is observed only when a pit cycle is executed; otherwise it
  is censored/unobserved.
- Do not mix target outcomes into features.
- Do not compute driver offsets, reference paces, or calibration parameters from
  holdout sessions when evaluating generalization.
- Do not compare DoWhy estimates as if they were classifier metrics.

## Phase 1-2 Exit Criteria

- Reproducible audit command exists: `make audit-causal-inputs`.
- Critical gap issue is documented.
- Variable inventory is frozen with `available_now`, `derivable_now`,
  `ideal_future`, and `not_recommended`.
- Historical vs replay-live availability is documented.
- Leakage rules are documented.
- Running-DB gap coverage has been checked and is zero for all three demo
  sessions.
- Next implementation phase is blocked on gap reconstruction and model artifact
  fitting before labels are built.
