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

### Día 1 — Kickoff
- [ ] Proponer `docs/interfaces/openapi_v1.yaml` esqueleto.
- [ ] Proponer `docs/interfaces/websocket_messages.md`.
- [ ] Proponer `docs/interfaces/replay_event_format.md`.
- [ ] Acordar interfaz `PacePredictor` con Stream A.

### Día 2 — Skeleton (E5 + E7)
- [ ] FastAPI app con `/health`, `/api/v1/sessions` (lista de sesiones desde DB).
- [ ] Interfaz `RaceFeed` en `feeds/base.py`.
- [ ] `ReplayFeed` esqueleto con fixture sintético en memoria.
- [ ] Test unitario: ReplayFeed emite eventos en orden con factor 1000×.
- [ ] OpenAPI export en CI.

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
