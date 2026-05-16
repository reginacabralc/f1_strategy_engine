# Stream C — Phase 5 Live Demo Validation

> **Branch**: `stream-c-phase5-live-demo-validation`
> **Date**: 2026-05-16
> **Scope**: End-to-end smoke validation of the full demo path before panel-by-panel design begins.

---

## Commands Run

```bash
# Lint
make lint                        # backend ruff + mypy; frontend ESLint

# Tests
make test-backend                # pytest backend/tests/unit
make test-frontend                # vitest run
make test-e2e                    # Playwright

# Live demo validation (stack was already up)
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/sessions
curl -X POST .../api/v1/replay/start -d '{"session_id":"monaco_2024_R","speed_factor":1000}'
# WebSocket listener (Python asyncio + websockets) — see notes below
curl -X POST .../api/v1/replay/stop
curl .../api/v1/backtest/monaco_2024_R?predictor=scipy
curl .../api/v1/backtest/monaco_2024_R?predictor=xgboost
curl -X POST .../api/v1/config/predictor -d '{"predictor":"scipy"}'
curl -X POST .../api/v1/config/predictor -d '{"predictor":"xgboost"}'
python scripts/reconstruct_race_gaps.py --dry-run
```

---

## Phase 1–4 Changes Present

| Item | File | Status |
|------|------|--------|
| RaceTable honest empty state | `frontend/src/components/RaceTable.tsx:124` | ✅ present |
| App metrics from snapshot | `frontend/src/App.tsx:31-50` | ✅ present |
| TrackMapPanel "Static circuit preview" badge | `frontend/src/components/TrackMapPanel.tsx:148` | ✅ present |
| TrackMapPanel footer ("live car coordinates unavailable in V1") | `frontend/src/components/TrackMapPanel.tsx:309` | ✅ present |
| normalizeAlertPayload | `frontend/src/api/ws.ts:59-81` | ✅ present |
| ReplayControls error handling (try/catch + data-testid) | `frontend/src/components/ReplayControls.tsx:92-115` | ✅ present |
| WebSocket V1 contract comments | `frontend/src/api/ws.ts:1-173` | ✅ present |
| WebSocket V1 contract tests | `frontend/src/api/ws.test.ts` | ✅ 7 tests |

---

## Test Results

| Suite | Result |
|-------|--------|
| Backend unit tests (`pytest`) | **383 passed** |
| Frontend unit tests (`vitest`) | **87 passed** (9 files) |
| E2E Playwright (`demo.spec.ts`) | **1 passed** |
| Backend lint (ruff + mypy) | **clean** |
| Frontend lint (ESLint) | **clean** |
| Frontend format (Prettier) | **not installed** — see note |

> **Note — Prettier**: `frontend/node_modules/.bin/prettier` not present in this env. ESLint covers style rules. Not blocking.

---

## Expected Demo Flow

1. User opens http://localhost:5173 — dashboard shell loads with no-session hint
2. User selects a session from the dropdown — session_id shown in Race Order label
3. User clicks Play — `POST /api/v1/replay/start` fires; WS sends `replay_state {state: started}`
4. Dashboard receives `snapshot` messages — RaceTable populates with driver rows, metric cards update
5. Alert panel receives `alert` messages — attacker/defender/lap rendered
6. User clicks Stop — `POST /api/v1/replay/stop` fires; WS sends `replay_state {state: stopped}`
7. BacktestView shows per-predictor precision/recall if session has curated data
8. PredictorToggle lets user switch scipy ↔ xgboost at runtime

---

## Observed Results

### Infrastructure

| Check | Result |
|-------|--------|
| Docker stack (backend + frontend + db) | All 3 containers healthy |
| `GET /health` | `{"status":"ok","version":"0.1.0"}` |
| `GET /api/v1/sessions` | 3 sessions returned (bahrain_2024_R, monaco_2024_R, hungary_2024_R) |
| Frontend reachable (`GET http://localhost:5173/`) | HTTP 200 |

### Replay Flow

| Check | Result |
|-------|--------|
| `POST /api/v1/replay/start` | 202 — `run_id`, `pace_predictor: "scipy"` |
| WebSocket connects | ✅ |
| `replay_state {state: started}` arrives | ✅ |
| `snapshot` messages arrive | ✅ — 199 snapshots for full Monaco 2024 replay |
| `POST /api/v1/replay/stop` | `{"stopped": true}` |

### Snapshot Data Quality

| Field | Expected | Observed | Status |
|-------|----------|----------|--------|
| `session_id` | `"monaco_2024_R"` | ✅ correct | pass |
| `current_lap` | 1..78 | ✅ increments | pass |
| `track_status` | `"GREEN"` | ✅ | pass |
| `track_temp_c` | ~47 °C | ✅ 47.1 | pass |
| `air_temp_c` | ~22 °C | ✅ 22.0 | pass |
| `active_predictor` | `"scipy"` | ✅ | pass |
| `drivers[].position` | 1–20 | ✅ populated | pass |
| `drivers[].compound` | SOFT/MEDIUM/HARD | ✅ populated | pass |
| `drivers[].tyre_age` | int | ✅ populated | pass |
| `drivers[].team_code` | e.g. `"ferrari"` | **null for all drivers** | ⚠️ data |
| `drivers[].gap_to_leader_ms` | int (ms) | **null for all drivers** | ⚠️ data |
| `drivers[].gap_to_ahead_ms` | int (ms) | **null for all drivers** | ⚠️ data |
| `drivers[].undercut_score` | float 0–1 | **null for all drivers** | ⚠️ blocked by gaps |

### Alert Flow

| Check | Result |
|-------|--------|
| `alert` messages during full Monaco 2024 replay | **0 alerts emitted** |
| Root cause | All `gap_to_ahead_ms` null → `compute_relevant_pairs()` returns 0 pairs |

### PR #50/#51 Integrations

| Check | Result |
|-------|--------|
| `GET /api/v1/backtest/monaco_2024_R?predictor=scipy` | 404 with descriptive message (expected — no curated data yet) |
| `GET /api/v1/backtest/monaco_2024_R?predictor=xgboost` | 404 with descriptive message (expected) |
| BacktestView renders "No curated backtest data for this session yet." | ✅ — `data-testid="backtest-unavailable-*"` |
| `POST /api/v1/config/predictor {"predictor":"scipy"}` | 200 — `{"active_predictor":"scipy"}` |
| `POST /api/v1/config/predictor {"predictor":"xgboost"}` | **409 Conflict** — `"XGBoost model not found"` |
| Frontend xgboost error message | ✅ — shows "XGBoost model not available. Staying on scipy." |
| Backend alert format | ✅ spec-shaped fields emitted (`alert_id`, `attacker_code`, `defender_code`, `lap_number`, `ventana_laps`, `predictor_used`) alongside legacy aliases (`attacker`, `defender`, `current_lap`) — normalizeAlertPayload handles both |

---

## Failure Analysis

### F1 — Gap columns are null (blocks alerts)

**Severity**: Blocking for alert demo  
**Classification**: Data / Backend pipeline

**Root cause**: FastF1 does not expose `GapToLeader` or `IntervalToPositionAhead` per lap in the `laps` dataframe. The ingest pipeline (`normalize_laps`) never populates `gap_to_leader_ms` / `gap_to_ahead_ms`, so they remain NULL in the DB for all 1,237 Monaco rows.

`compute_relevant_pairs()` in `backend/src/pitwall/engine/state.py:327` filters pairs by `attacker.gap_to_ahead_ms is not None`. With all gaps null, it returns an empty list on every lap. `evaluate_undercut` is never called. No undercut scores, no alerts.

**What exists**: `scripts/reconstruct_race_gaps.py` and `make reconstruct-race-gaps` are already implemented. A dry-run confirms it would populate:
- Monaco: 1,233/1,237 `gap_to_leader_ms` rows, 1,155/1,237 `gap_to_ahead_ms` rows
- Bahrain and Hungary also ready

**Fix needed**: `make reconstruct-race-gaps` must be run after `make seed` (and ideally chained into the `seed` or `demo` Makefile target by Stream D).

**Frontend impact**: RaceTable handles null gap gracefully (shows "—"). ScoreBar handles null score gracefully (shows "—"). No frontend bug — UI is honest.

---

### F2 — team_code null for all drivers

**Severity**: Low (cosmetic in current UI)  
**Classification**: Data / Backend

**Root cause**: `SqlSessionEventLoader._lap_event()` builds `lap_complete` events from the `laps` table, which has no `team_code` column. The `drivers` table holds global `(driver_code, team_code)` rows. The two are never joined when building replay events, so `DriverState.team_code` is always `None`.

**Frontend impact**: RaceTable renders `"—"` for the Team column (null-safe fallback at line 189). No crash.

**Fix needed**: `SqlSessionEventLoader` (or a session-start event) should join the `drivers` table and populate `team_code` on the initial `DriverState` objects. Stream B owns this.

---

### F3 — No backtest data for Monaco, Bahrain, Hungary

**Severity**: Expected — not a bug  
**Classification**: Data (Stream A backlog)

The curated known-undercuts table is empty. `GET /api/v1/backtest/{session_id}` returns 404 with `"Run 'make backtest' once Stream A has populated the known-undercut table (E9-E10)."` BacktestView renders the unavailable state correctly.

---

### F4 — XGBoost model not trained

**Severity**: Expected — not a bug  
**Classification**: Environment / Data

`models/xgb_pace_v1.json` does not exist. `POST /api/v1/config/predictor {"predictor":"xgboost"}` returns 409 Conflict. Frontend shows "XGBoost model not available. Staying on scipy." which is the correct targeted error path (catches `e.status === 409`).

Run `make train-xgb` after `make ingest-ml-races fit-degradation` to resolve.

---

### F5 — Prettier not installed in frontend node_modules

**Severity**: Low (environment only)  
**Classification**: Environment

`frontend/node_modules/.bin/prettier` is absent. This only affects format-checking; ESLint covers style rules. Tests and lint pass. Not blocking.

---

## What Passed

- Full frontend test suite (87 tests, 9 files) — all components and hooks green
- Full backend unit test suite (383 tests)
- E2E Playwright happy path
- Backend lint (ruff + mypy) — clean
- Frontend lint (ESLint) — clean
- Health, sessions, replay start/stop REST endpoints
- WebSocket emits `snapshot` and `replay_state` correctly
- Frontend snapshot → RaceTable render path (graceful nulls)
- metric cards (Track Temp, Air Temp) populate from snapshot
- Undercut Risk card: stays "—" when `undercut_score` is null (correct)
- PredictorToggle scipy: switch roundtrip confirmed
- PredictorToggle xgboost-missing: 409 → targeted user-facing message
- BacktestView unavailable state: renders correctly on 404
- Backend now emits spec-shaped alerts (dual format), normalizeAlertPayload confirmed correct

## What Failed

| # | Item | Classification |
|---|------|----------------|
| F1 | **Alerts never fire** — `gap_to_ahead_ms` null, `compute_relevant_pairs` returns empty | Data / Backend pipeline |
| F2 | `team_code` null — not joined from `drivers` table | Data / Backend |
| F3 | Backtest 404 for all sessions | Data (Stream A backlog, expected) |
| F4 | XGBoost 409 (no model) | Environment (expected) |
| F5 | Prettier missing | Environment |

---

## Follow-up Actions Before Panel-by-Panel Design

### Blocking

1. **Run `make reconstruct-race-gaps`** (or wire into `make seed`/`make demo` — Stream D).
   After this, undercut scores and alerts will fire during replay. This is the prerequisite for the alert panel to show real data in any demo.

2. **Verify alerts render correctly** after gap reconstruction — run a replay and confirm `alert` WS messages appear with correct `attacker_code`, `defender_code`, `lap_number`, `score`, `confidence`, `estimated_gain_ms`.

### Non-blocking (document and track)

3. **Fix `team_code` propagation** — `SqlSessionEventLoader` should load team codes at session-start so `DriverState.team_code` is populated. Stream B.

4. **Train XGBoost model** (`make train-xgb`) to unblock the predictor toggle for the xgboost path. Stream A.

5. **Curate known undercuts** (`make import-curated-known-undercuts`) to enable BacktestView results. Stream A.

6. **Install Prettier** in frontend or add to `make install-frontend` target. Stream D.

---

## Files Changed This Phase

- `docs/stream-c-phase5-live-demo-validation.md` (this document) — created
