# Stream C — Phase 0 Contract Audit

> **Branch**: `stream-c-phase0-contract-audit`
> **Date**: 2026-05-15
> **Scope**: Read-only audit of backend routes, WebSocket events, and frontend
> mock/static data usage. No functional changes to components.

---

## 1. Confirmed API Endpoints

All routes are mounted under the FastAPI app in `backend/src/pitwall/api/main.py`.

### Health

| Method | Path | Status | Notes |
|--------|------|--------|-------|
| `GET` | `/health` | ✅ live | Always 200 when process is alive |
| `GET` | `/ready` | ✅ live | 503 until DB is reachable |

### Sessions

| Method | Path | Operation ID | Status | Notes |
|--------|------|--------------|--------|-------|
| `GET` | `/api/v1/sessions` | `listSessions` | ✅ live | Returns `SessionSummary[]` |
| `GET` | `/api/v1/sessions/{session_id}/snapshot` | `getSessionSnapshot` | ✅ live | 404 if no active replay for that session |

`SessionSummary` fields: `session_id`, `circuit_id`, `season`, `round_number`, `date`, `total_laps`.

`RaceSnapshotOut` fields: `session_id`, `current_lap`, `track_status`, `track_temp_c`, `air_temp_c`,
`humidity_pct`, `drivers[]`, `active_predictor`, `last_event_ts`.

### Replay

| Method | Path | Operation ID | Status | Notes |
|--------|------|--------------|--------|-------|
| `POST` | `/api/v1/replay/start` | `startReplay` | ✅ live | Body: `{session_id, speed_factor}`. 409 if already running |
| `POST` | `/api/v1/replay/stop` | `stopReplay` | ✅ live | Idempotent. Returns `{stopped, run_id}` |

`speed_factor` defaults to 30, range 1–1000. Both routes broadcast a `replay_state` WS message.

### Degradation

| Method | Path | Operation ID | Status | Notes |
|--------|------|--------------|--------|-------|
| `GET` | `/api/v1/degradation?circuit=&compound=` | `getDegradationCurve` | ✅ wired; ⚠️ 404 until seeded | Returns `DegradationCurve` with quadratic coefficients `{a, b, c}`, `r_squared`, `n_samples`, `sample_points[]`. 404 if DB not seeded — run `make fit-degradation`. |

Valid compounds: `SOFT`, `MEDIUM`, `HARD`, `INTER`, `WET`.

### Predictor Config

| Method | Path | Operation ID | Status | Notes |
|--------|------|--------------|--------|-------|
| `POST` | `/api/v1/config/predictor` | `setActivePredictor` | ✅ live (scipy); ⚠️ 409 for xgboost | Body: `{predictor: "scipy"\|"xgboost"}`. xgboost returns 409 until `make train-xgb` has been run. |

### Backtest

| Method | Path | Operation ID | Status | Notes |
|--------|------|--------------|--------|-------|
| `GET` | `/api/v1/backtest/{session_id}?predictor=` | `getBacktestResult` | ⛔ always 404 | Route is wired but implementation is a `raise HTTPException(404)` stub. Blocked on Stream A (E9–E10) populating the curated known-undercut table. |

### Causal (Stream D addition)

| Method | Path | Operation ID | Status | Notes |
|--------|------|--------------|--------|-------|
| `GET` | `/api/v1/causal/prediction?...` | `getCausalPrediction` | ✅ live | Query-param–driven; no DB needed. Returns `CausalPredictionOut` with counterfactuals. Not yet in frontend client. |

### WebSocket

| Endpoint | Protocol | Notes |
|----------|----------|-------|
| `/ws/v1/live` | WebSocket | Reconnect with exponential backoff 1→2→4→8→16 s. Server sends current snapshot on connect. |

---

## 2. Confirmed WebSocket Message Types

### Actually emitted by the backend

| Type | Source file | When |
|------|-------------|------|
| `snapshot` | `engine/loop.py:168` | After every `lap_complete` event; also on WS connect if session is active |
| `alert` | `engine/loop.py:165` | For each undercut-viable pair per lap; also `SUSPENDED_SC`/`SUSPENDED_VSC` on safety-car laps |
| `ping` | `api/ws.py:79` | Every 15 s when no client frame received |
| `replay_state` | `api/routes/replay.py:113,154` | On `POST /replay/start` (state=`started`) and `POST /replay/stop` (state=`stopped`) |

### Defined in spec / frontend types but NOT emitted by backend

| Type | Where defined | Status | Root cause |
|------|---------------|--------|------------|
| `lap_update` | `docs/interfaces/websocket_messages.md`, `frontend/src/api/ws.ts` | ❌ not emitted | Engine loop emits a full `snapshot` after each `lap_complete`; no per-driver incremental message |
| `pit_stop` | spec + `ws.ts` | ❌ not emitted | Pit information flows through `snapshot.drivers[].is_in_pit`; no standalone pit event broadcast |
| `track_status` | spec + `ws.ts` | ❌ not emitted | SC/VSC triggers a `SUSPENDED_SC`/`SUSPENDED_VSC` `alert` instead; no standalone `track_status` message |
| `error` | spec + `ws.ts` | ❌ not emitted (implicitly) | Connection errors cause disconnect rather than an `error` frame; route does not call `broadcast_json` with `type=error` |

`useRaceFeed.ts` has `case` branches for `lap_update`, `pit_stop`, and `track_status` that are **dead code** in V1.

---

## 3. Alert Payload Mismatch (Critical)

The backend `_alert_message()` in [engine/loop.py](../backend/src/pitwall/engine/loop.py#L241) sends:

```json
{
  "type": "alert",
  "payload": {
    "alert_type": "UNDERCUT_VIABLE",
    "attacker": "NOR",
    "defender": "VER",
    "score": 0.7234,
    "confidence": 0.6100,
    "estimated_gain_ms": 1800,
    "pit_loss_ms": 22000,
    "gap_actual_ms": 2500,
    "session_id": "monaco_2024_R",
    "current_lap": 23
  }
}
```

The frontend `AlertPayload` interface in [api/ws.ts](../frontend/src/api/ws.ts) expects:

| Field in frontend type | Backend sends | Gap |
|------------------------|---------------|-----|
| `alert_id` | _nothing_ | ❌ missing — `AlertPanel` uses it as React key; will be `undefined` |
| `attacker_code` | `attacker` | ❌ name mismatch — panel renders blank |
| `defender_code` | `defender` | ❌ name mismatch — panel renders blank |
| `lap_number` | `current_lap` | ❌ name mismatch — panel shows `Lundefined` |
| `ventana_laps` | _nothing_ | ⚠️ in type but not rendered in `AlertPanel` |
| `predictor_used` | _nothing_ | ⚠️ in type but not rendered in `AlertPanel` |
| `estimated_gain_ms` | `estimated_gain_ms` | ✅ |
| `pit_loss_ms` | `pit_loss_ms` | ✅ |
| `gap_actual_ms` | `gap_actual_ms` | ✅ |
| `score` | `score` | ✅ |
| `confidence` | `confidence` | ✅ |
| `alert_type` | `alert_type` | ✅ |
| `session_id` | `session_id` | ✅ |

**Impact**: `AlertPanel` currently renders blank attacker/defender codes and `Lundefined` for the lap number when real alerts arrive. This needs to be fixed before Phase 1 connects the live feed.

**Fix owner**: Stream B (owns the backend alert encoder) should rename `attacker`→`attacker_code`, `defender`→`defender_code`, `current_lap`→`lap_number`, and add `alert_id` (UUID) to `_alert_message()`. Stream C adapts `AlertPayload` if the backend change is delayed.

---

## 4. Frontend Files — Mock / Static Behaviour

### RaceTable — [components/RaceTable.tsx](../frontend/src/components/RaceTable.tsx)

- **Mock**: imports `mockRaceOrder.json` and uses it as the default for the `drivers` prop.
- **When live**: `App.tsx` passes `snapshot?.drivers` — mock is bypassed as soon as a WS snapshot arrives.
- **Phase 1 action**: No structural change needed. Remove the default fallback once alert-payload mismatch is resolved and data flows reliably.

### TrackMapPanel — [components/TrackMapPanel.tsx](../frontend/src/components/TrackMapPanel.tsx)

- **Mock**: 6 hardcoded drivers with static SVG `(x, y)` coordinates on a Monaco outline.
- **When live**: `App.tsx` calls `<TrackMapPanel />` with **no props** — mock is always shown.
- **Root cause**: The backend snapshot contains no car telemetry coordinates. FastF1 historical data does not provide real-time positional streams.
- **Phase 1 action**: Keep as static preview. Add a `// TODO(stream-c-p2): wire real car positions if telemetry source available` note in the component.

### App.tsx METRICS — [App.tsx:15–24](../frontend/src/App.tsx#L15-L24)

- **Mock**: 4 hardcoded `MetricCard` values: Track Temp `42°C`, Air Temp `28°C`, Pit Loss `~23s`, Undercut Risk `HIGH`.
- **When live**: Never updates — values are compile-time constants.
- **Available real data**: `snapshot.track_temp_c`, `snapshot.air_temp_c`, `snapshot.humidity_pct`. Pit loss and undercut risk are computed by the engine but not surfaced as a dedicated field in the snapshot (only per-driver `undercut_score`).
- **Phase 1 action**: Replace Track Temp and Air Temp with `snapshot` values. Derive Undercut Risk from max `undercut_score` across drivers. Pit Loss can remain static (~23 s Monaco) or come from a future dedicated endpoint.

### BacktestView — [components/BacktestView.tsx](../frontend/src/components/BacktestView.tsx)

- **No mock data** — calls `GET /api/v1/backtest/{session_id}` via `useBacktest`.
- Backend returns 404 (stub). Frontend shows "No curated backtest data for this session yet." — correct placeholder behaviour.
- **Phase 1 action**: None needed. Will work automatically once Stream A populates the backtest table.

### PredictorToggle — [components/PredictorToggle.tsx](../frontend/src/components/PredictorToggle.tsx)

- **No mock data** — calls `POST /api/v1/config/predictor` via `usePredictor`.
- Handles 409 (xgboost not loaded) with user-visible error. Active predictor from `snapshot?.active_predictor`.
- **Phase 1 action**: None needed.

### DegradationChart — [components/DegradationChart.tsx](../frontend/src/components/DegradationChart.tsx)

- **No mock data** — calls `GET /api/v1/degradation?circuit=&compound=` via `useDegradation`.
- Handles 404 with "run `make fit-degradation`" message.
- **Phase 1 action**: None needed. Works once Stream A seeds the DB.

### ReplayControls — [components/ReplayControls.tsx](../frontend/src/components/ReplayControls.tsx)

- **No mock data** — calls `startReplay`/`stopReplay` from `api/client.ts`.
- Skip/Step buttons are intentionally disabled (no backend support).
- Gets `replayState`, `currentLap`, `totalLaps` from parent props (via `useRaceFeed` + `useSessions`).
- **Phase 1 action**: None needed.

---

## 5. Stream Dependencies

### Stream A owns
| Capability | Unlocks in frontend |
|------------|---------------------|
| `make fit-degradation` → degradation coefficients in DB | `DegradationChart` renders real curves |
| `make train-xgb` → XGBoost model at `models/xgb_pace_v1.json` | `PredictorToggle` xgboost button no longer 409s |
| Curated known-undercut table (E9–E10) | `BacktestView` shows precision/recall/F1 |

Stream C **must not** render degradation or backtest data with mocks — the 404/loading states are correct while Stream A work is in progress.

### Stream B owns
| Capability | Unlocks in frontend |
|------------|---------------------|
| Fix `_alert_message()` field names (`attacker_code`, `defender_code`, `lap_number`, `alert_id`) | `AlertPanel` renders correctly |
| `POST /api/v1/replay/start` + replay engine loop running | `RaceTable` receives live `snapshot` data |
| WebSocket snapshot on every `lap_complete` | All live panels update |

Stream C **blocks on Stream B** for the alert payload fix before Phase 1 can display real alerts.

### Stream D owns
| Capability | Unlocks in frontend |
|------------|---------------------|
| `make demo` → full stack launch | End-to-end demo path |
| Causal endpoint (`/api/v1/causal/prediction`) | Not yet wired in frontend; Stream C Phase 2 candidate |

---

## 6. Recommended Stream C Contract

### Phase 1 — Safe to implement now (no Stream A/B blockers)

These changes use only endpoints that are already live and correct:

1. **Fix App.tsx METRICS**: Wire Track Temp and Air Temp from `snapshot.track_temp_c` / `snapshot.air_temp_c`. Derive "Undercut Risk" label from `Math.max(...snapshot.drivers.map(d => d.undercut_score ?? 0))`.
2. **TrackMapPanel**: Add comment marking it as a permanent static preview until a telemetry source exists. Keep "Static preview" badge.
3. **RaceTable default fallback**: Conditionally show empty state when no snapshot instead of mock data (prevents confusion in production demos).
4. **Causal frontend hook** (optional): Add `getCausalPrediction` to `api/client.ts` to expose the Stream D endpoint for future use.

### Phase 2 — Needs Stream B alert fix first

5. **AlertPanel live data**: After Stream B fixes `_alert_message()` field names, verify `AlertPanel` renders correctly with real alerts. Add `alert_id` fallback key (`${attacker}-${lap}`) until Stream B lands the fix.
6. **TrackMapPanel with undercut highlight**: Highlight drivers with `undercut_score > 0.65` on the map (even if positions are static, the highlight is meaningful).
7. **SessionPicker → auto-start replay**: Connect `SessionPicker` selection to auto-trigger `POST /api/v1/replay/start` with default `speed_factor=30`.

### Never implement in Stream C (by design)

- Do not add mock data for backtest or degradation — 404 placeholders are correct.
- Do not implement `lap_update`, `pit_stop`, or `track_status` handlers — backend does not emit these in V1.
- Do not add Kafka, Redis, or any new broker.

---

## 7. Files Changed in This Audit

This audit is read-only. Only this document was created:

- `docs/stream-c-phase0-contract-audit.md` (this file)

---

## 8. Appendix — Snapshot Payload Shape (as emitted by backend)

```json
{
  "v": 1,
  "type": "snapshot",
  "ts": "2024-05-26T13:45:21.503Z",
  "payload": {
    "session_id": "monaco_2024_R",
    "current_lap": 23,
    "track_status": "GREEN",
    "track_temp_c": 38.2,
    "air_temp_c": 24.0,
    "humidity_pct": 62.0,
    "active_predictor": "scipy",
    "last_event_ts": "2024-05-26T13:45:21.000Z",
    "drivers": [
      {
        "driver_code": "VER",
        "team_code": "RBR",
        "position": 1,
        "gap_to_leader_ms": 0,
        "gap_to_ahead_ms": null,
        "last_lap_ms": 74521,
        "compound": "MEDIUM",
        "tyre_age": 18,
        "is_in_pit": false,
        "is_lapped": false,
        "last_pit_lap": null,
        "stint_number": 1,
        "undercut_score": null
      }
    ]
  }
}
```

Note: The `"v": 1` field is in the envelope but not in the frontend `WsEnvelope` TypeScript type — this is harmless (extra JSON fields are ignored). Frontend types do not need to be updated for this.

---

## 9. Appendix — Alert Payload Shape (as actually emitted by backend today)

```json
{
  "v": 1,
  "type": "alert",
  "ts": "2024-05-26T13:46:10.000Z",
  "payload": {
    "alert_type": "UNDERCUT_VIABLE",
    "attacker": "NOR",
    "defender": "VER",
    "score": 0.7234,
    "confidence": 0.6100,
    "estimated_gain_ms": 1800,
    "pit_loss_ms": 22000,
    "gap_actual_ms": 2500,
    "session_id": "monaco_2024_R",
    "current_lap": 23
  }
}
```

Compare to what the spec (`websocket_messages.md`) and frontend type (`AlertPayload`) expect — see §3 above.
