# Phase 5C — Live Alert Verification

**Branch**: `phase5c-live-alert-verification`  
**Date**: 2026-05-16  
**Author**: Stream C

---

## Summary

Phase 5C runs the Monaco 2024 replay through the undercut engine in-process and
verifies whether real `UNDERCUT_VIABLE` alerts fire end-to-end after the Phase 5B
gap-reconstruction fix. The answer is **no alerts fire** under green-flag conditions.
This document classifies the remaining blockers precisely.

---

## 1. Phase 5B Presence Confirmed

`make demo` dependency chain (from Makefile):

```
demo: db-up migrate seed reconstruct-race-gaps fit-degradation-demo
    docker compose up -d backend frontend
    $(MAKE) api-wait
    $(PYTHON) -m webbrowser -t http://localhost:5173
```

- `reconstruct-race-gaps` depends on `db-wait` ✓
- Gap reconstruction runs after seed, before `fit-degradation-demo` ✓
- `docs/walkthrough.md` step 3 and troubleshooting section updated in Phase 5B ✓
- `infra/runbook.md` includes cause #5 (NULL gap_to_ahead_ms) ✓

---

## 2. Baseline Checks

| Check | Result |
|-------|--------|
| `make lint` (ruff + mypy + eslint) | **PASS** — all clean |
| `make test-backend` (pytest) | **PASS** — 383 tests |
| `make test-frontend` (vitest) | **PASS** — 87 tests (9 files) |
| `make test-e2e` | Skipped — no display available in WSL2 environment |

---

## 3. Gap Reconstruction Status

Queried from the local demo DB (`pitwall-db` container):

| Session | Total rows | gap_to_ahead_ms populated |
|---------|-----------|--------------------------|
| bahrain_2024_R | 1,129 | 1,072 (94.9%) |
| monaco_2024_R | 1,237 | 1,155 (93.4%) |
| hungary_2024_R | 1,355 | 1,285 (94.8%) |

Gap data is populated. The Phase 5A data blocker is resolved.

---

## 4. Degradation Coefficients

8 `quadratic_v1` coefficient rows in DB:

| circuit_id | compound | R² | n_laps |
|-----------|---------|-----|--------|
| bahrain | HARD | 0.0174 | 731 |
| bahrain | SOFT | 0.1249 | 312 |
| hungary | HARD | 0.0399 | 823 |
| hungary | MEDIUM | 0.1277 | 412 |
| hungary | SOFT | 0.0841 | 38 |
| monaco | HARD | 0.1897 | 764 |
| monaco | MEDIUM | 0.3622 | 391 |
| monaco | SOFT | 0.0315 | 32 |

**Critical observation**: all R² values are below the engine's confidence threshold of 0.5.
Best fit is Monaco MEDIUM at R²=0.362.

---

## 5. Live Engine Verification

Verification script: `scripts/verify_alerts_phase5c.py`  
Method: loads Monaco 2024 events from DB, runs them through `RaceState.apply()` and
`evaluate_undercut()` in-process. No WebSocket or HTTP server required.

### Monaco 2024 results

```
Events loaded        : 1,438
lap_complete events  : 1,237
Pairs evaluated      : 17,415
  INSUFFICIENT_DATA  : 698
  UNDERCUT_VIABLE    : 16,717
UNDERCUT_VIABLE where should_alert=True : 0

Blocker breakdown (for UNDERCUT_VIABLE decisions):
  score_too_low (score ≤ 0.4)       : 16,717
  confidence_too_low (conf ≤ 0.5)   : also 0 — both blockers apply

First UNDERCUT_VIABLE example (should_alert=False):
  attacker: PIA  defender: LEC  lap: 4
  score: 0.0000  (threshold: 0.4)
  confidence: 0.0332  (threshold: 0.5)
  estimated_gain_ms: -29,407
  gap_actual_ms: 799
```

### Cross-session summary

| Session | INSUFFICIENT_DATA | UNDERCUT_VIABLE | score>0.4 | conf>0.5 | Alerts |
|---------|------------------|----------------|-----------|----------|--------|
| monaco_2024_R | 698 | 16,717 | 0 | 0 | **0** |
| bahrain_2024_R | 18,900 | 0 | 0 | 0 | **0** |
| hungary_2024_R | 2,644 | 21,124 | 0 | 0 | **0** |

---

## 6. Alert Emission Path (Code Review)

The WebSocket emission path is correct and unchanged from the Phase 5B baseline.

### Backend path

1. `EngineLoop._on_lap_complete()` calls `compute_relevant_pairs(state)` for all
   pairs where `gap_to_ahead_ms < 30,000 ms` and both drivers are on track.
2. For each pair, `evaluate_undercut()` returns an `UndercutDecision`.
3. If `decision.should_alert == True`, `_alert_message(decision, state, predictor_name)`
   is broadcast via `ConnectionManager.broadcast_json()`.
4. `_alert_message` emits both spec-shaped fields (`alert_id`, `attacker_code`,
   `defender_code`, `lap_number`) and legacy aliases (`attacker`, `defender`,
   `current_lap`).
5. SC/VSC condition correctly broadcasts `SUSPENDED_SC`/`SUSPENDED_VSC` instead
   of evaluating pairs.

Example alert payload shape (spec-complete, never emitted from demo data):

```json
{
  "v": 1,
  "type": "alert",
  "ts": "2026-05-16T04:00:00.000000+00:00",
  "payload": {
    "alert_id": "monaco_2024_R:42:NOR:VER:UNDERCUT_VIABLE",
    "alert_type": "UNDERCUT_VIABLE",
    "lap_number": 42,
    "attacker_code": "NOR",
    "defender_code": "VER",
    "ventana_laps": 5,
    "predictor_used": "scipy",
    "attacker": "NOR",
    "defender": "VER",
    "score": 0.6543,
    "confidence": 0.5100,
    "estimated_gain_ms": 1500,
    "pit_loss_ms": 21000,
    "gap_actual_ms": 2100,
    "session_id": "monaco_2024_R",
    "current_lap": 42
  }
}
```

### Frontend path

- `useRaceFeed.ts` handles `type="alert"` messages with `normalizeAlertPayload()` ✓
- `normalizeAlertPayload` accepts both spec-shaped and legacy-shaped payloads ✓
- `AlertPanel` renders `attacker_code`, `defender_code`, `lap_number`,
  `estimated_gain_ms`, `score`, `confidence` — all correct ✓
- 11 AlertPanel tests pass (including rendering, empty state, CRITICAL/WARN/INFO
  levels, Lundefined prevention) ✓
- `normalizeAlertPayload` is unchanged and retained ✓

---

## 7. Blocker Classification (Precise)

### Blocker 1 — Score = 0 for Monaco and Hungary (PRIMARY)

**Category**: engine logic / circuit physics  
**Affected sessions**: monaco_2024_R, hungary_2024_R

The `evaluate_undercut` formula:

```python
raw_score = (gap_recuperable_ms - pit_loss_ms - gap_actual_ms - UNDERCUT_MARGIN_MS) / pit_loss_ms
score = max(0.0, min(1.0, raw_score))
```

At Monaco 2024, `gap_recuperable_ms` (the projected net gain from 5 laps on fresh vs.
worn tyres) is **always ≤ 0**. Example: `estimated_gain_ms = -29,407 ms` at lap 4.

Root cause: Monaco is not a tyre degradation circuit. The quadratic coefficients fitted
on Monaco 2024 data are nearly flat (very small `b` and `c` terms). With minimal
degradation, fresh tyres provide almost no pace advantage over worn tyres in a 5-lap
projection window. A 21 s pit stop cannot be recovered.

This is **correct engine behaviour**. Monaco 2024 strategy was driven entirely by VSC
deployment (the engine correctly emits `SUSPENDED_VSC` during those periods and skips
pair evaluation). Under green flag, Monaco undercuts were not viable — the engine
agrees.

Hungary 2024 shows the same pattern (all R² < 0.13, score = 0 for all 21,124 pairs).

### Blocker 2 — Confidence below threshold for all sessions (SECONDARY)

**Category**: thresholds vs. model quality  
**Affected sessions**: all three

The engine threshold: `CONFIDENCE_THRESHOLD = 0.5`.  
Max R² across all fitted coefficients: **0.362** (Monaco MEDIUM).

Formula: `confidence = min(R²_def, R²_atk) × data_quality_factor(attacker)`.

Even if score were above threshold (which it is not), confidence would still block all
alerts. No (circuit, compound) cell has R² ≥ 0.5 in the current demo fit.

This means the confidence threshold is currently **unreachable** with three-race demo data.

### Blocker 3 — Bahrain: all pairs INSUFFICIENT_DATA

**Category**: data / model coverage  
**Affected session**: bahrain_2024_R

The `_NEXT_COMPOUND` heuristic:
```python
_NEXT_COMPOUND = {"SOFT": "MEDIUM", "MEDIUM": "HARD", "HARD": "MEDIUM", ...}
```

Bahrain 2024 used only HARD and SOFT compounds. No MEDIUM laps were driven. The
degradation fitter correctly finds no MEDIUM data for Bahrain and writes no MEDIUM
coefficient.

When the engine evaluates a HARD-compound driver who might pit to MEDIUM, it calls
`predictor.predict(circuit="bahrain", compound="MEDIUM")` which raises
`UnsupportedContextError` → `INSUFFICIENT_DATA`. This affects all 18,900 Bahrain pairs.

This is a **design limitation** of the `_NEXT_COMPOUND` heuristic: it always projects
the "standard" next compound rather than checking what compound is actually available.

---

## 8. Frontend AlertPanel Status

The AlertPanel component is ready to render real alerts if they ever arrive:

- Empty state: "No alerts — start a replay to receive live strategy alerts" ✓
- Alert rendering: `attacker → defender`, level badge (CRITICAL/WARN/INFO),
  lap number, estimated gain, score %, confidence % ✓
- No blank `attacker_code` / `defender_code` (both `normalizeAlertPayload` guards
  and AlertPanel display are correct) ✓
- No "Lundefined" issue ✓
- 11 unit tests confirm rendering correctness ✓

The AlertPanel **does not need changes** for Phase 5C.

---

## 9. Pass/Fail Classification

| Item | Result |
|------|--------|
| Phase 5B wired correctly | **PASS** |
| `make lint` | **PASS** |
| `make test` (383 + 87) | **PASS** |
| gap_to_ahead_ms populated | **PASS** |
| Degradation coefficients present | **PASS** |
| Relevant pairs computed | **PASS** (16,717+ per session) |
| `evaluate_undercut` reachable | **PASS** |
| WebSocket emission path correct | **PASS** (code review) |
| `normalizeAlertPayload` retained | **PASS** |
| AlertPanel renders alerts | **PASS** (unit tests) |
| Real alerts fire during replay | **FAIL** |

**Overall Phase 5C result: FAIL — no UNDERCUT_VIABLE alerts fire for any demo session.**

---

## 10. Remaining Blockers Before Panel-by-Panel Design

The WebSocket, engine, and frontend wiring are all correct. The blockers are in the
model and threshold layer:

| Priority | Blocker | Recommended fix |
|----------|---------|-----------------|
| HIGH | Score = 0 for Monaco/Hungary (low degradation) | Use a session with real green-flag strategy action (e.g., 2024 Singapore, Baku, or Monza). OR reduce `K_MAX` to 3 and `UNDERCUT_MARGIN_MS` to 200 ms to lower the break-even bar. |
| HIGH | Confidence threshold 0.5 unreachable | Lower `CONFIDENCE_THRESHOLD` from 0.5 to 0.25–0.30 to match the best available R² (0.362). The threshold was designed for a richer model; the 3-race demo fit doesn't meet it. |
| MEDIUM | Bahrain: no MEDIUM coefficient → all INSUFFICIENT_DATA | Either fit a Bahrain MEDIUM coefficient using data from comparable circuits, or extend the `_NEXT_COMPOUND` heuristic to check available compound coverage before projecting. |

Panel-by-panel design can proceed with the understanding that alerts will render
correctly once the model/threshold blocker is resolved.

---

## 11. Commands Run

```bash
make lint                                          # PASS
make test                                          # PASS (383 backend + 87 frontend)
docker compose up -d db                           # start demo DB
make db-wait                                      # wait for Postgres
# DB queries: lap count, gap coverage, degradation coefficients, circuit_id
PYTHONPATH=backend/src python scripts/verify_alerts_phase5c.py  # in-process verification
```

---

## 12. Files Changed in Phase 5C

| File | Change |
|------|--------|
| `scripts/verify_alerts_phase5c.py` | New — in-process alert verification script |
| `docs/stream-c-phase5c-live-alert-verification.md` | New — this document |
| `docs/progress.md` | Updated with Phase 5C entry |

---

## Post-PR #55 integration scan

After the initial Phase 5C validation, PR #55 (`integration: connect 4 streams into one runnable stack`) was merged into `main`.

Relevant effects:
- Added typed frontend client support for `/api/v1/causal/prediction`.
- Added Docker fallback behavior for frontend test/lint commands.
- Added rebuild targets for backend/frontend containers.
- Updated README integration guidance.
- Did not resolve the alert-firing blocker identified in Phase 5C.

Conclusion:
PR #55 helps future integration and panel design, especially for a future causal/counterfactual panel, but it does not change the Phase 5C result. Alerts still require a follow-up calibration/demo-scenario fix.