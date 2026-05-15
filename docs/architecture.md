# Arquitectura — PitWall

> Documento de referencia técnica del sistema. Acompaña al [plan maestro](../.claude/plans/00-master-plan.md) (que cubre el cómo construir) con el qué se construye.

## 1. Visión general

PitWall es un sistema event-driven con un único proceso backend (FastAPI + asyncio), una base de datos relacional con extensión time-series (TimescaleDB), un frontend React, y un componente de ML (XGBoost) integrado al motor detrás de una interfaz común.

```text
┌──────────────────────┐
│  FastF1 (cache)      │
│  CSV/Parquet local   │
└──────────┬───────────┘
           │  scripts/ingest_season.py
           ▼
┌──────────────────────┐
│ PostgreSQL +         │
│ TimescaleDB          │
│  • laps (hyper)      │
│  • pit_stops         │
│  • stints            │
│  • degradation_*     │
│  • alerts (hyper)    │
│  • model_registry    │
└──────────┬───────────┘
           │
   ┌───────┴────────────────────────────────────────┐
   ▼                                                 ▼
┌─────────────────┐              ┌──────────────────────────────┐
│ Replay Engine   │              │ Degradation Fit (scipy)      │
│ (ReplayFeed)    │              │ + XGBoost Trainer            │
│ implements      │              │  → models/xgb_pace_v1.json   │
│ RaceFeed        │              └────────────┬─────────────────┘
└────────┬────────┘                           │
         │ asyncio.Queue                      │
         ▼                                     ▼
   ┌──────────────────────────────────────────────┐
   │ Undercut Engine                               │
   │  • RaceState (in-memory)                      │
   │  • PacePredictor interface                    │
   │     ├─ ScipyPredictor                         │
   │     └─ XGBoostPredictor                       │
   │  • Pair selection + scoring + alerts          │
   └────────┬─────────────────────────────────────┘
            │
   ┌────────┴───────────────┐
   ▼                        ▼
┌──────────────┐    ┌────────────────┐
│ FastAPI REST │    │ WebSocket /ws  │
│ /api/v1/...  │    │ live snapshots │
└──────┬───────┘    └────────┬───────┘
       │                     │
       └──────────┬──────────┘
                  ▼
          ┌──────────────┐
          │ React + Vite │
          │  Dashboard   │
          └──────────────┘
```

## 2. Componentes

| # | Componente | Lenguaje | Owner | Notas |
|---|------------|----------|-------|-------|
| 1 | Ingestor histórico | Python (Polars + FastF1) | Stream A | CLI scripts; carga 2024 a TimescaleDB |
| 2 | Degradation fit (scipy) | Python | Stream A | Cuadrática por (circuito × compuesto) |
| 3 | XGBoost trainer | Python | Stream A | Dataset LORO con target `lap_time_delta_ms`; serializa Booster JSON + sidecar metadata |
| 4 | RaceFeed interface | Python (abstract) | Stream B | Contrato común para replay y futuro live |
| 5 | ReplayFeed | Python (asyncio) | Stream B | Lee DB, emite eventos al ritmo del factor |
| 6 | OpenF1Feed (stub V1) | Python | Stream B | Implementación dummy; real en V2 |
| 7 | Undercut Engine | Python (asyncio) | Stream B | RaceState in-memory + cálculo de pares |
| 8 | PacePredictor interface | Python | Stream A+B | Implementaciones: scipy y xgboost |
| 9 | FastAPI app | Python | Stream B | REST + WebSocket en mismo proceso |
| 10 | React dashboard | TypeScript | Stream C | Vite, TanStack Query, Tailwind, Recharts |
| 11 | Postgres + Timescale | SQL | Stream A+D | Hypertables: laps, alerts, live_lap_events |
| 12 | docker-compose | YAML | Stream D | 4 servicios: db, migrate, backend, frontend |
| 13 | CI (GitHub Actions) | YAML | Stream D | lint, test, build de imágenes |

## 3. Flujo de datos: alerta de undercut (secuencia)

```text
Replay tick (vuelta N completa)
   │
   ▼
ReplayFeed emite evento `lap_complete{driver, lap_time, compound, tyre_age}`
   │
   ▼
asyncio.Queue
   │
   ▼
UndercutEngine.consume()
   │
   ├── RaceState.apply(event)   # actualiza posición, gap, neumáticos
   │
   ├── compute_relevant_pairs(state)
   │     # filtra pares consecutivos con gap < 30s, no doblados, no pit reciente
   │
   └── for (attacker, defender) in pairs:
         decision = evaluate_undercut(state, attacker, defender, predictor)
            # 1. pit_loss = pit_loss_estimates[(circuit, attacker.team)]
            # 2. proyectar pace defender k=1..5: predictor.predict(defender, k) + driver_offset
            # 3. proyectar pace attacker k=1..5: predictor.predict(attacker, fresh_compound, k)
            # 4. gap_recuperable_acumulado(k)
            # 5. score = clamp((gain - pit_loss - gap) / pit_loss, 0, 1)
            # 6. confidence = min(R²_defender, R²_attacker) * data_quality
         if decision.should_alert:
            await alerts_topic.publish(decision)
            await db.persist(decision)

WebSocket subscribers reciben `alert` y `snapshot`
React UI actualiza tabla y feed en < 200 ms
```

### Causal viability boundary

The causal module answers only:

```text
Given the current pre-pit race state, is an undercut viable right now?
```

Its target is `undercut_viable`. The main DAG ends at that node and excludes
`pit_decision`, `pit_now`, and `undercut_success`, because those are downstream
team-action and post-pit outcome variables. Historical pit-cycle outcomes may
still be retained for evaluation/backtest, but they are not parents, children,
or features of the main viability graph.

The final comparison before the target uses:

```text
projected_gap_after_pit_ms =
  required_gain_to_clear_rival_ms - projected_gain_if_pit_now_ms
```

`projected_gap_after_pit_ms <= 0` means the modeled undercut clears the rival
after the safety margin; positive values mean the attacker has not gained enough.

## 4. Estado in-memory: `RaceState`

Reconstruible desde el feed (no es source of truth, no se persiste):

```python
@dataclass
class DriverState:
    driver_code: str
    team_code: str
    position: int
    gap_to_leader_ms: int
    gap_to_ahead_ms: int | None
    last_lap_ms: int | None
    compound: str
    tyre_age: int                   # vueltas en este compuesto
    is_in_pit: bool
    is_lapped: bool
    last_pit_lap: int | None
    stint_number: int
    data_stale_since: datetime | None

@dataclass
class RaceState:
    session_id: str
    current_lap: int
    track_status: str               # GREEN, SC, VSC, RED, YELLOW
    track_temp_c: float | None
    drivers: dict[str, DriverState]
    last_event_ts: datetime
```

## 5. Decisiones que enmarcan el diseño

| Decisión | Doc | Resumen |
|----------|-----|---------|
| Stack base | [ADR 0001](adr/0001-stack-base.md) | Python + FastAPI + React + TimescaleDB |
| Replay-first en V1 | [ADR 0002](adr/0002-replay-first.md) | No live OpenF1 hasta V2 |
| TimescaleDB sí, Redis no | [ADR 0003](adr/0003-timescaledb.md) | Higiene de queries, no escala |
| Baseline scipy antes que XGBoost | [ADR 0004](adr/0004-baseline-scipy-antes-de-xgboost.md) | Heurística primero, ML después |
| Monorepo | [ADR 0005](adr/0005-monorepo-vs-polirepo.md) | Backend + frontend en mismo repo |
| Polars vs pandas | [ADR 0006](adr/0006-polars-vs-pandas.md) | Polars por velocidad y API declarativa |
| Asyncio sin broker | [ADR 0007](adr/0007-asyncio-sin-broker.md) | `asyncio.Queue` in-process suficiente |
| OpenAPI como fuente de verdad | [ADR 0008](adr/0008-openapi-como-fuente-verdad.md) | Generado por FastAPI; cliente TS lo consume |
| Resultado XGBoost vs scipy | [ADR 0009](adr/0009-xgboost-vs-scipy-resultados.md) | Por escribir tras E10 |

## 6. Boundaries y dependencias entre módulos

```text
backend/src/pitwall/
  api/         ← depende de engine, db
  engine/      ← depende de feeds (interface), degradation, ml (predictor)
  feeds/       ← depende de db (read-only)
  ingest/      ← depende de db (write)
  degradation/ ← depende de db (read-write)
  ml/          ← depende de db (read-write), degradation (referencia)
  db/          ← núcleo, no depende de nada interno
  core/        ← config, logging, topics; usado por todos
```

Reglas:

- `engine/` **no importa** de `api/`. Si necesita responder a algo, publica en un topic.
- `feeds/` **no importa** de `engine/`. Solo emite eventos.
- `api/` **no importa** de `feeds/` directamente. Lee del estado in-memory del engine.

## 7. Tamaños esperados

### XGBoost training baseline

Stream A Day 8 trains two kinds of models from the Day 7 pace dataset:

- Fold models: one native `xgboost.Booster` per leave-one-race-out fold, used
  only for evaluation.
- Final model: one native `xgboost.Booster` trained on all usable rows and
  written to `models/xgb_pace_v1.json` with metadata in
  `models/xgb_pace_v1.meta.json`.

The model target is `lap_time_delta_ms`, not raw lap time. Categorical
features (`circuit_id`, `compound`, `driver_code`, `team_code`) are one-hot
encoded with `UNKNOWN` for missing/unseen values. Numeric missing values are
left as `NaN` for XGBoost. `session_id` remains a fold/split identifier and is
not a training feature. Pit loss is intentionally excluded from this lap-level
pace model; it belongs to Day 9 undercut/backtest decision features.

Runtime XGBoost prediction reconstructs the saved feature schema from
`models/xgb_pace_v1.meta.json`. Because the model predicts
`lap_time_delta_ms`, the metadata now carries runtime reference-pace maps used
to convert the predicted delta back into an absolute lap-time estimate for the
shared `PacePredictor` interface.

Current 3-race metrics are functional but weak. Day 8.1 diagnostics show
sub-second training error (MAE 294.7 ms, R² 0.943) but poor holdout error
(MAE 7,396.0 ms, R² -0.080). With only Bahrain, Monaco, and Hungary, LORO is
effectively leave-one-circuit-out, so target/reference shift dominates. The
model barely improves over the zero-delta baseline and is documented as a
serialized engineering baseline, not as an accurate pace model. V2 needs 8-10+
races, ideally repeated circuits across seasons or richer circuit/reference
descriptors.

| Recurso | Tamaño | Dónde |
|---------|--------|-------|
| FastF1 cache | 2-5 GB | `data/cache/` (gitignored) |
| DB inicial (3 carreras) | < 100 MB | volumen `pgdata` |
| DB con 1 temporada | ~500 MB | volumen `pgdata` |
| Modelo XGBoost serializado | ~5 MB | `models/xgb_pace_v1.json` |
| Imagen backend | ~800 MB (base + deps) | local |
| Imagen frontend (build) | ~30 MB (nginx + bundle) | local |

## 8. Performance budgets (V1)

- Latencia evento → alert publicada: < 100 ms p95
- Latencia alert → render UI: < 200 ms p95
- Inferencia XGBoost por par de pilotos: < 5 ms
- Replay overhead a factor 1×: < 10% CPU
- Memoria backend en steady state: < 500 MB

## 9. Deploy topology (V1)

Un solo host, todo en docker-compose:

```text
host (laptop / cualquier máquina con Docker)
  ├── service: db          (timescaledb:pg15)        :5432
  ├── service: migrate     (alembic, one-shot)
  ├── service: backend     (uvicorn)                  :8000
  └── service: frontend    (vite dev / nginx prod)    :5173
```

Sin replicación, sin orquestador, sin balanceador. V2 puede pasar a Fly.io con Postgres gestionada.

## 10. Observabilidad mínima (V1)

- Logs JSON con `structlog`.
- `/health` (proceso vivo) y `/ready` (DB conectada).
- WebSocket heartbeat ping/pong cada 15 s.
- `/metrics` endpoint expuesto (formato Prometheus) aunque V1 no tenga Prometheus desplegado — V1.5 lo enchufa sin tocar código.

## 11. Lo que NO está en este diseño

- Auth / users / multi-tenant.
- Mensajería externa (email, Slack, Discord).
- Streaming de telemetría high-frequency (DRS, throttle, brake).
- Predicción de lluvia / cambio de condiciones.
- Estrategia de pit window propia (cuándo parar tu propio piloto óptimamente).
- Análisis de aire sucio / dirty air.
- Modelo de tráfico al salir de pit lane.

Todo lo anterior es V2 o V3.
