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



### Día 3 — Replay completo (E5)
- [ ] `ReplayFeed` lee de DB real (no fixture).
- [ ] `topics.py` con `events_topic`, `alerts_topic`, `snapshot_topic`.
- [ ] Endpoint `POST /api/v1/replay/start`, `POST /api/v1/replay/stop`.
- [ ] Tests: replay de 10 vueltas mock genera 10 lap_complete events.

### Día 4 — Estado del motor (E6 prep)
- [ ] `RaceState` y `DriverState` dataclasses.
- [ ] `RaceState.apply(event)` con tests para cada tipo de evento.
- [ ] `compute_relevant_pairs(state)` con filtros (gap < 30s, no doblados, etc.).
- [ ] Tests con escenarios sintéticos.

### Día 5 — Motor V1 (E6) ⭐
- [ ] `engine/projection.py` con `project_pace(driver, compound, age, k, predictor)`.
- [ ] `engine/pit_loss.py` con lookup + fallbacks.
- [ ] `engine/undercut.py::evaluate_undercut(state, atk, def_, predictor)`.
- [ ] Decisión emite alerta si score > 0.4 AND confidence > 0.5.
- [ ] WebSocket `/ws/v1/live` enviando `snapshot` + `alert`.
- [ ] **Hito S1**: replay → motor con `ScipyPredictor` real → cliente WS recibe alerta.

### Día 6 — Endpoints REST (E7)
- [ ] `/api/v1/sessions/{id}/snapshot`.
- [ ] `/api/v1/degradation?circuit=&compound=`.
- [ ] OpenAPI export con todos los endpoints, validado en CI.
- [ ] Cliente Python de prueba en `scripts/ws_demo_client.py`.

### Día 7 — OpenAPI y polish
- [ ] Auto-export OpenAPI a `docs/interfaces/openapi_v1.yaml` en CI.
- [ ] Validador `openapi-spec-validator` en CI.
- [ ] Toggle `PACE_PREDICTOR` vía env var → log en startup.
- [ ] Endpoint `POST /api/v1/config/predictor` para cambio en runtime.

### Día 8 — Edge cases (E6)
- [ ] SC/VSC: emite `SUSPENDED_SC` / `SUSPENDED_VSC`, no calcula undercut.
- [ ] Lluvia (compound INTER/WET): emite `UNDERCUT_DISABLED_RAIN`.
- [ ] Stint < 3 vueltas: emite `INSUFFICIENT_DATA`.
- [ ] Datos stale (> 2 vueltas sin lap): driver excluido de pares.
- [ ] Pit stop reciente: no alertar undercut sobre quien acaba de parar.
- [ ] `XGBoostPredictor` cargable desde `models/xgb_pace_v1.json`.

### Día 9 — Confidence y filtros finales (E7)
- [ ] `data_quality_factor` real (no constante).
- [ ] Cold tyre penalty calibrado del histórico.
- [ ] Tests property-based con `hypothesis` para invariantes.
- [ ] Endpoint `/api/v1/backtest/{session_id}` (delega a Stream A).

### Día 10 — Demo
- [ ] Dry-run completo Mónaco con ambos predictores.
- [ ] Smoke tests E2E pasan.
- [ ] WebSocket reconexión funciona tras reinicio del backend.

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
