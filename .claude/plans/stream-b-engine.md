# Stream B — Motor & API

> Owner: _por asignar_. Backup: Stream A.
> Cubre Etapas 5, 6, 7 del [plan maestro](00-master-plan.md).

## Mantra

"El motor debe ser leíble en una pizarra. Si no, está mal."

## Responsabilidades

1. Interfaz `RaceFeed` (abstracta).
2. `ReplayFeed` que emite eventos desde DB al ritmo del factor de velocidad.
3. Stub `OpenF1Feed` (V2 implementa).
4. `RaceState` in-memory.
5. Motor de undercut: pares relevantes, scoring, alertas.
6. FastAPI app: routers REST + WebSocket.
7. Edge cases: SC, VSC, lluvia, pit reciente, datos faltantes.
8. Módulo causal explicable de viabilidad de undercut, como capa adicional
   sobre el motor existente y sin reemplazar `PacePredictor`/XGBoost.

## Archivos owned

```
backend/src/pitwall/feeds/
backend/src/pitwall/engine/
backend/src/pitwall/api/
backend/src/pitwall/core/
docs/quanta/01-undercut.md
docs/quanta/04-ventana-undercut.md
docs/quanta/05-replay-engine.md
docs/quanta/08-arquitectura-async.md
docs/interfaces/openapi_v1.yaml          # auto-generado, commit periódico
docs/interfaces/websocket_messages.md
docs/interfaces/replay_event_format.md
```

## Tareas

### Línea nueva — Causal undercut viability module

- [x] **Stream B implementará el causal undercut viability module** como una
  capa adicional explicable para responder `undercut_viable = sí/no` por
  observación `(driver, rival, lap)`, sin reemplazar XGBoost ni el motor
  heurístico existente.
- [x] Plan detallado: [`stream-b-causal-undercut.md`](stream-b-causal-undercut.md).
- [x] Gate conceptual antes de código: validar inventario de variables reales,
  definición operacional de labels históricos, DAG inicial, tratamientos,
  outcomes, confounders y límites de DoWhy.
- [x] Si se agrega `dowhy` como dependencia, escribir ADR mínimo antes de tocar
  `backend/pyproject.toml`.

### Day 1 — Kickoff ✅

- [x] Finalize `docs/interfaces/openapi_v1.yaml` — full V1 in English,
  9 paths with explicit `operationId`s, 17 schemas, error responses
  (400/404/409/503) on every mutating endpoint, request/response
  examples, harmonised enums (`Compound`, `TrackStatus`, `AlertType`,
  `PredictorName`). Validated with `openapi-spec-validator`.
- [x] Finalize `docs/interfaces/websocket_messages.md` — envelope spec,
  8 server→client message types, reconnect policy, heartbeat semantics,
  backpressure rules, versioning rules.
- [x] Finalize `docs/interfaces/replay_event_format.md` — 8 event
  types, ordering guarantees, pacing algorithm, JSON-Lines wire format
  for fixtures, V1 vs V2 (`OpenF1Feed`) differences.
- [x] **Sign-off on Stream A's `PacePredictor`.** Reviewed the
  Protocol, `PaceContext`, and `PacePrediction` definitions in
  `backend/src/pitwall/engine/projection.py`. Contract is sufficient
  for the Day 5 engine call sites described in
  `docs/quanta/04-ventana-undercut.md`. Sign-off is materialised as
  the executable consumer test in
  `backend/tests/contract/test_pace_predictor_contract.py`, which
  exercises the projection loop the way `pitwall.engine.undercut` will
  on Day 5. If Stream A ever changes the surface in a way that breaks
  this consumer pattern, that test fails and the change must be
  renegotiated.

**Cross-doc consistency check (run before merge):** all four
authoritative documents agree on:

- `Compound` ∈ `[SOFT, MEDIUM, HARD, INTER, WET]`
- `TrackStatus` ∈ `[GREEN, SC, VSC, YELLOW, RED]`
- `AlertType` ∈ 6 values (`UNDERCUT_VIABLE`, `UNDERCUT_RISK`,
  `UNDERCUT_DISABLED_RAIN`, `SUSPENDED_SC`, `SUSPENDED_VSC`,
  `INSUFFICIENT_DATA`)
- `PredictorName` ∈ `[scipy, xgboost]`
- `humidity` is reported as percent (0-100), and the field is named
  `humidity_pct` everywhere it appears.

### Day 2 — Skeleton (E5 + E7) ✅

- [x] **FastAPI app with `/health`, `/ready`, `/api/v1/sessions`.**
  Module entry point at `backend/src/pitwall/api/main.py::create_app()`;
  module-level `app` for `uvicorn pitwall.api.main:app`. Sessions route
  reads from a `SessionRepository` Protocol — Stream A drops the SQL
  implementation in on Day 3 by editing one function in
  `pitwall/api/dependencies.py`. V1 default is
  `InMemorySessionRepository` populated with the three demo races.
- [x] **`RaceFeed` interface** in `backend/src/pitwall/feeds/base.py`,
  with `Event` envelope and per-event payload `TypedDict`s mirroring
  `docs/interfaces/replay_event_format.md`.
- [x] **`ReplayFeed` skeleton** in
  `backend/src/pitwall/feeds/replay.py` — accepts an in-memory
  `Iterable[Event]`, sorts by `ts`, paces with a `t0`-anchored
  algorithm (no drift under slow consumers). `stop()` cancels any
  in-flight sleep. `OpenF1Feed` stub raises
  `OpenF1FeedNotImplementedError` on instantiation per ADR 0002.
- [x] **Replay unit tests** — 10 tests in
  `backend/tests/unit/feeds/test_replay.py` covering: timestamp-order
  guarantee at factor 1000× (with shuffled input), the "factor 1000×
  finishes quickly" benchmark, low-factor pacing actually waits,
  `stop()` during a sleep terminates promptly, empty input yields
  nothing, idempotent `stop()`, post-stop iteration is empty,
  Protocol adherence, and rejection of `speed_factor <= 0`.
- [x] **OpenAPI export script** at `scripts/export_openapi.py`.
  Outputs JSON (default) or YAML (auto-detected from extension). The
  authoritative CI workflow is Stream D's responsibility (Day 7), but
  the contract test that backs it lives in
  `backend/tests/contract/test_openapi_export.py` and is parametrised
  over an `IMPLEMENTED` table that grows as Stream B lands routes.

#### What I added that is normally Stream D's

To unblock Day 2, `backend/pyproject.toml` gained five runtime
dependencies (`fastapi`, `uvicorn[standard]`, `pydantic`,
`pydantic-settings`, `structlog`) and three dev dependencies
(`httpx`, `pyyaml`, `openapi-spec-validator`). The block is clearly
labelled "Stream B, Day 2" so D's Day 1 becomes a verify-and-extend
rather than a conflict.

#### Smoke run

`uv pip install -e ".[dev]"` then `pytest tests/ -v`:
**60 passed in 6.75 s** (10 replay + 8 API + 11 OpenAPI contract +
4 PacePredictor contract + 27 projection unit tests). Export script
generates a 3-path / 2-schema spec; every Day-2 `operationId` matches
the static `docs/interfaces/openapi_v1.yaml`.



### Day 3 — Replay completo (E5) ✅

- [x] **`core/topics.py`** — `Topics` dataclass with three `asyncio.Queue`
  channels (`events`, `alerts`, `snapshots`). ADR 0007: no broker.
  Queues are created synchronously (Python 3.10+) and stored on
  `app.state` by `create_app()`.
- [x] **`repositories/events.py`** — `SessionEventLoader` Protocol +
  `InMemorySessionEventLoader` fixture loader. Same seam pattern as
  `SessionRepository`: Stream A drops a SQL implementation in by
  editing `api.dependencies.get_event_loader`.
- [x] **`engine/replay_manager.py`** — `ReplayManager` drives one
  active `ReplayFeed` into `topics.events` via a background
  `asyncio.Task`. Exposes `start(session_id, speed_factor, events) → UUID`,
  `stop() → UUID | None`, and `is_running` / `current_session_id`
  properties. `stop()` signals the feed, waits 2 s, then cancels.
- [x] **`api/routes/replay.py`** — `POST /api/v1/replay/start`
  (`startReplay`, 202) and `POST /api/v1/replay/stop` (`stopReplay`,
  200) with operationIds matching the static spec. 409 on duplicate
  start, 404 when session has no events.
- [x] **`api/main.py`** updated — lifespan for graceful shutdown,
  `Topics` + `ReplayManager` created synchronously in `create_app()`
  and stored on `app.state`. Replay router included.
- [x] **`api/dependencies.py`** updated — `get_event_loader()`,
  `get_replay_manager(request)`, `get_topics(request)` providers added.
- [x] **104 tests passing** (8 replay API + 8 `ReplayManager` unit +
  17 OpenAPI contract + 4 `PacePredictor` contract + 27 projection unit
  + 10 `ReplayFeed` + 5 sessions + 3 health + 4 DB engine + 4 dataset
  + 2 degradation writer + 4 fit + 6 normalize + 4 ingest writer + 2
  degradation writer).
- [x] **Contract test** `test_openapi_export.py` `IMPLEMENTED` dict
  extended with `/api/v1/replay/start` and `/api/v1/replay/stop`.

#### DB note
Post-merge Stream A integration is wired. `SessionEventLoader` still
owns the protocol seam, and `ReplayFeed` remains storage-agnostic, but
`api.dependencies.get_event_loader()` now returns Stream A's
`SqlSessionEventLoader` when `DATABASE_URL` is configured. The same
dependency module returns `SqlSessionRepository` for `/api/v1/sessions`.
Without `DATABASE_URL`, both seams keep the in-memory fallback.

The `"hungarian_2024_R"` → `"hungary_2024_R"` slug inconsistency is
canonicalized by Stream A migrations `0003_canonical_hungary_slug.py`
and `0004_canonical_hungary_coefficient_sources.py`, so existing local
DB volumes can run `make migrate` instead of being wiped.

### Day 4 — Estado del motor (E6 prep) ✅

- [x] **`engine/state.py`** — `DriverState` + `RaceState` dataclasses.
  `RaceState.apply(event)` dispatches on all 8 event types
  (`session_start`, `session_end`, `lap_complete`, `pit_in`, `pit_out`,
  `track_status_change`, `weather_update`, `data_stale`). Unknown types
  silently ignored.
  Key fields: `position`, `gap_to_leader_ms`, `gap_to_ahead_ms`
  (3-lap rolling average), `last_lap_ms` (valid laps only),
  `compound`, `tyre_age`, `is_in_pit`, `is_lapped`, `last_pit_lap`,
  `stint_number`, `laps_in_stint`, `data_stale`.
- [x] **`compute_relevant_pairs(state)`** — filters in-race drivers
  (position known, not in pit, not lapped, not stale), sorts by
  position, returns `(attacker, defender)` pairs with
  `attacker.gap_to_ahead_ms < 30_000 ms`.
- [x] **34 tests** in `backend/tests/unit/engine/test_state.py` —
  all 8 event types, gap smoothing (1/2/3 samples + window rollover),
  pit-out resets gap history, `compute_relevant_pairs` with all
  filter combinations, empty/single-driver edge cases.
- [x] **223 tests passing** total across the entire backend suite.

### Day 5 — Motor V1 (E6) ✅ ⭐

- [x] **`engine/projection.py`** extended — `COLD_TYRE_PENALTIES_MS = (800, 300, 0)`
  and `project_pace(driver_code, circuit_id, compound, start_age, k, predictor, *,
  apply_cold_tyre_penalty)` projecting k lap times forward.
- [x] **`engine/pit_loss.py`** — `PitLossTable`, `DEFAULT_PIT_LOSS_MS = 21_000`,
  `lookup_pit_loss(circuit, team, table)` with team → circuit median → constant
  fallback chain.
- [x] **`engine/undercut.py`** — `UndercutDecision` frozen dataclass +
  `evaluate_undercut(state, atk, def_, predictor, pit_loss_ms)` implementing
  §6.4–6.8 math: cumulative gap recovery over K_MAX=5 laps, score normalised by
  pit_loss, confidence = min(R²_defender, R²_attacker). Alert when
  `score > 0.4 AND confidence > 0.5`.
- [x] **`engine/state.py`** — `DriverState.undercut_score: float | None = None` added;
  reset to `None` and repopulated by the loop on each `lap_complete`.
- [x] **`engine/loop.py`** — `EngineLoop` (background asyncio task):
  reads `topics.events` → `RaceState.apply()` → on `lap_complete`:
  evaluate all pairs → update `undercut_score` → broadcast `alert` messages →
  broadcast `snapshot`. `Broadcaster` Protocol decouples engine from API layer.
  `set_predictor()` for runtime swap.
- [x] **`api/connections.py`** — `ConnectionManager`: `connect/disconnect/broadcast_json`
  (1 s send timeout removes dead clients).
- [x] **`api/ws.py`** — `WebSocket /ws/v1/live`: accepts, registers with
  `ConnectionManager` via `websocket.app.state`, heartbeat ping every 15 s,
  cleans up on disconnect.
- [x] **`api/main.py`** updated — `ConnectionManager` + `EngineLoop` created
  synchronously in `create_app()`; lifespan tries to reload `ScipyPredictor` from
  DB at startup (silent fallback to empty predictor when DB unavailable).
- [x] **`api/dependencies.py`** updated — `get_connection_manager`,
  `get_engine_loop` providers added.
- [x] **250 tests passing** (6 pit_loss + 5 project_pace + 9 undercut + 7 WS/CM
  + all prior tests).

#### Hito S1 integration path
The full pipeline is wired: `POST /api/v1/replay/start` → `ReplayManager` →
`topics.events` → `EngineLoop` → `ConnectionManager` → `/ws/v1/live` clients.
To receive a live `UNDERCUT_VIABLE` alert:
1. `make db-up && make migrate && make ingest-demo && make fit-degradation`
   (loads real coefficients — R² target ≥ 0.5)
2. `uvicorn pitwall.api.main:app` (lifespan loads predictor from DB)
3. `wscat -c ws://localhost:8000/ws/v1/live`
4. `POST /api/v1/replay/start` with a session that has degraded-tyre scenarios

### Día 6 — Endpoints REST (E7) ✅

- [x] **`GET /api/v1/sessions/{session_id}/snapshot`** — returns the in-memory
  `RaceState` for the session currently being replayed. 404 when no active replay
  or replay is for a different session. Response serialises every `DriverState`
  (position, gap, compound, tyre_age, undercut_score) plus `active_predictor` and
  `last_event_ts`. Tested: 404 cases, shape, driver sorting by position, predictor
  reflection.
- [x] **`GET /api/v1/degradation?circuit=&compound=`** — returns fitted quadratic
  coefficients (a, b, c) and R² from `degradation_coefficients`. 404 when the DB
  has not been seeded. 400 on unknown compound. Case-insensitive for both query
  params. Follows the same repository seam pattern as sessions: `InMemoryDegradationRepository`
  as default (→ 404), `SqlDegradationRepository` wired when DB is available.
  Tested: 404, 400, correct coefficient values, 5 valid compounds.
- [x] **OpenAPI export with all 7 implemented endpoints, validated in CI.**
  `test_openapi_export.py` `IMPLEMENTED` dict extended with the two new paths.
  All 7 `operationId`s verified to match `docs/interfaces/openapi_v1.yaml` exactly.
  23 contract tests passing.
- [x] **`scripts/ws_demo_client.py`** — demo client that connects to `/ws/v1/live`
  and prints `alert` messages (attacker, defender, score, confidence, estimated_gain_ms)
  and `snapshot` messages (lap, track_status, driver count) in a human-readable format.
  Requires `pip install websockets`.

#### New files — Day 6

- `backend/src/pitwall/repositories/degradation.py` — `CoefficientRow` dataclass,
  `DegradationRepository` Protocol, `InMemoryDegradationRepository`.
- `backend/src/pitwall/repositories/sql.py` extended — `SqlDegradationRepository`
  queries `degradation_coefficients WHERE model_type = 'quadratic_v1'`.
- `backend/src/pitwall/api/routes/degradation.py` — `getDegradationCurve` route.
- `backend/src/pitwall/api/schemas.py` extended — `DriverStateOut`, `RaceSnapshotOut`,
  `DegradationCoefficients`, `DegradationSamplePoint`, `DegradationCurve`,
  `PredictorName`.
- `backend/src/pitwall/engine/loop.py` extended — `predictor_name` property.
- `backend/src/pitwall/api/dependencies.py` extended — `get_degradation_repository`.
- `backend/src/pitwall/api/main.py` extended — `degradation_routes.router` included.

#### Smoke run — Day 6

**198 tests passing.** ruff clean, mypy clean (78 source files). All 7 implemented
`operationId`s match the static OpenAPI spec. `EngineLoop` end-to-end pipeline
verified: events → state → undercut_score written per lap_complete.

### Día 7 — OpenAPI y polish ✅

- [x] **OpenAPI validation in CI.** `test.yml` `ruff-mypy` job now includes a
  dedicated "Validate live OpenAPI spec" step that instantiates `create_app()`,
  calls `.openapi()`, and passes the result to `openapi_spec_validator.validate()`.
  Fails CI if the generated spec is not valid OpenAPI 3.0. Contract test extended
  with `test_live_spec_is_valid_openapi` (runs in both CI jobs via pytest).
- [x] **`PACE_PREDICTOR` toggle → structlog at startup.** `main.py` lifespan now
  emits a `pitwall_startup` structured log event with `pace_predictor` and
  `version` fields immediately before the engine loop starts. A `pitwall_shutdown`
  event is logged on graceful exit. Uses `get_logger(__name__)` from `core.logging`.
- [x] **`POST /api/v1/config/predictor`** (`setActivePredictor`, tag `config`).
  - `scipy` → always succeeds: reloads `ScipyPredictor` from DB (empty fallback if
    DB unreachable). Calls `engine_loop.set_predictor(predictor, "scipy")`.
  - `xgboost` → 409 when `models/xgb_pace_v1.json` is missing (run
    `make train-xgb`). 409 from `ImportError` when the runtime lacks the
    `xgboost` package.
  - Returns `SetPredictorResponse { active_predictor }`.
  - Unknown predictor name (not in `Literal["scipy", "xgboost"]`) → 422 from
    Pydantic validation (FastAPI standard).

#### New / modified files

- `backend/src/pitwall/api/routes/config.py` — new route file.
- `backend/src/pitwall/api/schemas.py` — added `SetPredictorRequest`,
  `SetPredictorResponse`.
- `backend/src/pitwall/core/config.py` — added `xgb_model_path` setting
  (default `"models/xgb_pace_v1.json"`).
- `backend/pyproject.toml` — added `ignore_missing_imports = true` to
  `[tool.mypy]` so local `mypy src tests` and CI `mypy src tests` are identical
  (no more `--ignore-missing-imports` flag divergence).
- `backend/src/pitwall/api/main.py` — config router included; startup/shutdown
  structlog events added.
- `backend/tests/contract/test_openapi_export.py` — `test_live_spec_is_valid_openapi`
  added; `/api/v1/config/predictor` added to `IMPLEMENTED`.
- `backend/tests/unit/api/test_config.py` — 8 tests.
- `.github/workflows/test.yml` — "Validate live OpenAPI spec" step added.

#### Smoke run — Day 7

**210 tests passing.** ruff clean, mypy clean (80 source files, no `--ignore-missing-imports` flag required). 8 implemented paths in live spec, all valid OpenAPI 3.0.

### Día 8 — Edge cases (E6) ✅

- [x] **SC/VSC: `SUSPENDED_SC` / `SUSPENDED_VSC`, no undercut calculation.**
  `_on_lap_complete()` in `loop.py` checks `state.track_status` before evaluating
  pairs. When `"SC"` or `"VSC"`, it broadcasts one session-level alert via
  `_suspension_message()` (alert_type, null attacker/defender) and skips all
  pair evaluation. Snapshot still broadcast every lap. YELLOW flag does NOT
  suspend evaluation (only SC/VSC per plan §6.9).
- [x] **Rain (INTER/WET): `UNDERCUT_DISABLED_RAIN`.**
  Guard added at top of `evaluate_undercut()` in `undercut.py`. If either
  attacker or defender compound is INTER or WET (case-insensitive), returns
  `UndercutDecision(alert_type="UNDERCUT_DISABLED_RAIN", should_alert=False)`.
- [x] **Stint < 3 laps: `INSUFFICIENT_DATA`.**
  Already implemented (Day 5). Guard at `attacker.laps_in_stint < 3` in
  `evaluate_undercut()` remains. Not broadcast as alert (`should_alert=False`).
- [x] **Datos stale: driver excluded from pairs.**
  Already implemented (Day 4). `compute_relevant_pairs()` filters `data_stale=True`
  drivers. The `data_stale` event from the feed sets the flag; automatic detection
  (> 2 laps without lap_time) is V1.5.
- [x] **Pit stop reciente: no alertar undercut sobre quien acaba de parar.**
  Guard added in `evaluate_undercut()`: if `defender.laps_in_stint < 2`
  (defender on outlap or pre-first-lap), returns `INSUFFICIENT_DATA`. Protects
  against misleading "attacker should undercut a defender who already pitted."
- [x] **`XGBoostPredictor` loadable from `models/xgb_pace_v1.json`.**
  Created `backend/src/pitwall/ml/__init__.py` and `backend/src/pitwall/ml/predictor.py`.
  `XGBoostPredictor.from_file(path)` loads an `xgb.Booster` (native JSON format,
  no sklearn dependency). `predict()` is now metadata-driven: it preserves
  `feature_schema.feature_names`, maps unseen categorical values to `UNKNOWN`,
  uses XGBoost-native missing values for absent numeric live fields, and converts
  `lap_time_delta_ms` to absolute lap time with a live-safe reference. Satisfies
  `PacePredictor` Protocol (isinstance check passes). Optional `.meta.json`
  sidecar loaded for training metadata.
  `POST /api/v1/config/predictor {"predictor": "xgboost"}` already wired in Day 7:
  checks model file existence → 409 if missing, otherwise loads and calls
  `engine_loop.set_predictor()`.

#### New / modified files — Day 8

- `backend/src/pitwall/ml/__init__.py` — new module.
- `backend/src/pitwall/ml/predictor.py` — `XGBoostPredictor` class.
- `backend/src/pitwall/engine/loop.py` — SC/VSC branch in `_on_lap_complete()`,
  `_suspension_message()` builder.
- `backend/src/pitwall/engine/undercut.py` — rain guard, recent-pit guard.
- `backend/tests/unit/engine/test_loop.py` — 8 new tests (SC, VSC, GREEN,
  YELLOW, snapshot-always, score-reset invariant).
- `backend/tests/unit/engine/test_undercut.py` — 8 new tests (INTER/WET/lowercase,
  defender-0-laps, defender-1-lap, defender-2-laps resumes).
- `backend/tests/unit/ml/test_xgboost_predictor.py` — 9 tests (from_file, sidecar,
  missing file, predict error, Protocol compliance).

#### Smoke run — Day 8

**234 tests passing.** ruff clean, mypy clean (85 source files).
SC/GREEN transition verified: SUSPENDED_SC during SC, UNDERCUT_VIABLE after green.
Rain/pit edge cases verified inline. XGBoostPredictor Protocol compliance verified.
`brew install libomp` required locally (macOS only); ubuntu-latest CI has it pre-installed.

### Día 9 — Confidence y filtros finales (E7) ✅

- [x] **`data_quality_factor` real.** `_data_quality_factor(attacker)` function added to
  `engine/undercut.py`. Reduces confidence when stint < 8 laps (linear ramp `laps/8`)
  and when traffic gap < 1500 ms (−0.2 penalty). Clamped to [0, 1].
  Applied in `evaluate_undercut()`: `confidence = min(R²_def, R²_atk) * data_quality_factor(atk)`.
- [x] **Calibratable cold-tyre penalties.** `project_pace()` in `engine/projection.py` now
  accepts optional `cold_tyre_penalties: tuple[int, ...] | None` parameter. When `None`,
  uses module-level `COLD_TYRE_PENALTIES_MS = (800, 300, 0)`.
  New module `engine/calibration.py` exports `calibrate_cold_tyre_penalties(outlap_deltas, n_penalty_laps)`:
  takes list of per-lap delta lists → median per lap → clamp negatives to 0.
- [x] **Property-based tests with `hypothesis`.**
  `tests/unit/engine/test_undercut_properties.py` with 5 `@given` tests:
  - `test_no_viable_when_equal_pace_predictor` (300 ex): equal pace → score = 0.
  - `test_no_viable_when_attacker_faster_than_defender` (300 ex): faster defender → score = 0.
  - `test_no_alert_when_confidence_below_threshold` (200 ex): R² < 0.5 → should_alert = False.
  - `test_score_always_in_zero_one` (400 ex): score ∈ [0, 1] always.
  - `test_should_alert_iff_both_thresholds_exceeded` (500 ex): alert ↔ both thresholds.
- [x] **`GET /api/v1/backtest/{session_id}`** (`getBacktestResult`, tag `backtest`).
  Runs replay-derived backtests for `predictor=scipy|xgboost` and returns
  precision/recall/F1, lead time and MAE@k metrics. Returns 404 only when no
  replay events are available for the requested session. Unknown predictor → 422.
  `BacktestResult` + `UndercutMatch` schemas added to `api/schemas.py`.
  Wired in `api/main.py` + added to `IMPLEMENTED` in contract test.

#### New / modified files — Day 9

- `backend/src/pitwall/engine/calibration.py` — new module.
- `backend/src/pitwall/engine/undercut.py` — `_data_quality_factor`, `_FULL_QUALITY_LAPS`,
  `_TRAFFIC_GAP_MS`, `_TRAFFIC_CONFIDENCE_PENALTY` constants; confidence updated.
- `backend/src/pitwall/engine/projection.py` — `cold_tyre_penalties` optional param.
- `backend/src/pitwall/api/routes/backtest.py` — real `getBacktestResult` runner.
- `backend/src/pitwall/api/schemas.py` — `UndercutMatch`, `BacktestResult`.
- `backend/src/pitwall/api/main.py` — `backtest_routes.router` included.
- `backend/tests/contract/test_openapi_export.py` — backtest path added to `IMPLEMENTED`.
- `backend/tests/unit/engine/test_undercut_properties.py` — 5 hypothesis tests.
- `backend/tests/unit/engine/test_data_quality.py` — 25 unit tests.

#### Smoke run — Day 9

**265 tests passing (231 unit + 34 contract).** ruff clean, mypy clean (89 source files).
All 9 implemented endpoints match static OpenAPI spec. Hypothesis tests: 1700 total examples
across 5 invariants. `data_quality_factor` verified: short-stint lowers confidence, traffic
lowers confidence, both together can suppress alerts below threshold. Calibration roundtrip
verified.

### Día 10 — Demo ✅

- [x] **Snapshot on WS (re)connect.** `ws.py` now sends `EngineLoop.get_snapshot()` to each
  client immediately after `cm.connect()`. Returns `None` when no session is active (no
  message sent); returns the full `snapshot` dict when a session has started.
  Per spec: "After reconnecting, the client receives a fresh snapshot."
  `EngineLoop.get_snapshot()` method added to `engine/loop.py`.
- [x] **`replay_state` WS broadcast on start/stop.** `api/routes/replay.py` updated:
  `start_replay` broadcasts `replay_state(started)` after `replay_manager.start()`.
  `stop_replay` broadcasts `replay_state(stopped)` after `replay_manager.stop()`.
  Session/run_id captured from private `_session_id`/`_run_id` before stop() clears them
  (task may finish before stop() is called with short fixtures).
  Response object built before the broadcast `await` to avoid `started_at=None` race.
- [x] **End-to-end in-process pipeline tests.** `tests/unit/engine/test_e2e_pipeline.py`
  (13 tests, no DB, no real WS connections):
  - `test_one_snapshot_per_lap_complete` — 1 snapshot/lap invariant.
  - `test_snapshot_contains_active_predictor_scipy` — predictor name in payload.
  - `test_snapshot_drivers_sorted_by_position` — driver ordering invariant.
  - `test_snapshot_get_snapshot_method_reflects_state` — `get_snapshot()` None/dict lifecycle.
  - `test_predictor_switch_reflected_in_snapshots` — scipy → xgboost mid-session.
  - `test_set_predictor_name_reflected_on_get_snapshot` — get_snapshot() after switch.
  - `test_unsupported_predictor_does_not_crash_loop` — UnsupportedContextError is handled.
  - `test_xgboost_predictor_satisfies_protocol` — XGBoostPredictor isinstance(PacePredictor).
  - `test_xgboost_predictor_without_feature_schema_raises_unsupported` — metadata guard verified.
  - `test_viable_undercut_alert_emitted_with_scipy` — ScipyPredictor end-to-end shape check.
  - `test_alert_payload_has_required_fields` — UNDERCUT_VIABLE alert field completeness.
  - `test_replay_start_broadcasts_replay_state` — HTTP + WS integration.
  - `test_replay_stop_broadcasts_replay_state` — HTTP + WS integration.
- [x] **WS reconnect tests.** `tests/unit/api/test_ws.py` extended:
  - `test_ws_sends_snapshot_on_connect_when_session_active` — snapshot received on connect.
  - `test_ws_no_snapshot_sent_when_no_session_active` — no message when idle.

#### New / modified files — Day 10

- `backend/src/pitwall/engine/loop.py` — `get_snapshot()` method.
- `backend/src/pitwall/api/ws.py` — snapshot sent on connect via `engine_loop.get_snapshot()`.
- `backend/src/pitwall/api/routes/replay.py` — `replay_state` broadcasts; `started_at` race fix.
- `backend/tests/unit/engine/test_e2e_pipeline.py` — 13 new tests.
- `backend/tests/unit/api/test_ws.py` — 2 new reconnect tests + `_MockEngineLoop` helper.

#### Smoke run — Day 10

**280 tests passing (246 unit + 34 contract), ruff clean, mypy clean (90 source files).**
Full pipeline verified with ScipyPredictor and XGBoostPredictor runtime contract end-to-end.
`replay_state(started)` + `replay_state(stopped)` confirmed in WS stream.
Snapshot on reconnect confirmed via `_MockEngineLoop` injection.

## Definition of Done por tarea
- Código + tests + docs.
- Si cambia formato de eventos / mensajes / endpoints: actualizar `docs/interfaces/`.
- Si introduce comportamiento nuevo del motor: actualizar quanta correspondiente.

## Riesgos del stream
1. **Drift de replay a factor alto**: mitigado procesando por evento siguiente, no wall-clock.
2. **WebSocket backpressure**: timeout de 1s por send, desconectar clientes lentos.
3. **Race conditions**: testear con `asyncio.gather` + assertions de orden.
4. **Tentación de meter Kafka**: NO. ADR 0007 es claro.

## Coordinación
- **Con A**: `PacePredictor`, `pit_loss_estimates`, `degradation_coefficients`, schema laps.
- **Con C**: OpenAPI shape, WebSocket messages, lap_update timing.
- **Con D**: Dockerfile backend, env vars, tests integración.
