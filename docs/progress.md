# Progreso

> Vivo. Se actualiza en cada PR. Alguien del stream que mergea actualiza la línea correspondiente.

## Hitos

| Hito | Estado | Fecha objetivo | Notas |
|------|--------|----------------|-------|
| Andamiaje docs creado | ✅ | Día 0 | Este commit |
| Setup repo + Docker + CI verde | ⏳ | Día 2 | Stream D |
| Kickoff e interfaces acordadas | ⏳ | Día 1 | Todos |
| 1 temporada (2024) ingerida en DB | ⏳ | Día 3 | Stream A — 3 demo races loaded; full season pending |
| Replay engine funcional con fixture | ⏳ | Día 3 | Stream B |
| Dashboard mock conectado a `/sessions` | ✅ | Día 3 | Stream C — Day 2+3 catch-up done |
| Curva de degradación scipy ajustada | ✅ | Día 5 | Stream A — functional baseline persisted and reported; R² remains below target |
| Motor undercut V1 con `ScipyPredictor` | ⏳ | Día 5 | Stream B |
| Pipeline end-to-end con datos reales | ⏳ | Día 7 | Todos |
| **XGBoost entrenado y serializado** | ✅ | Día 8 | Stream A — native Booster trained, serialized, and validated; weak 3-race holdout metrics documented |
| **Backtest comparativo scipy vs XGBoost** | ⏳ | Día 9 | Stream A+B |
| Demo end-to-end probada en limpio | ⏳ | Día 10 | Todos |

## Semana 1

### Día 0 — Pre-arranque
- [x] Plan maestro escrito y aprobado.
- [x] Andamiaje de docs creado (CLAUDE.md, AGENTS.md, README, ADRs esqueleto, quanta esqueleto, interfaces esqueleto).
- [x] `.claude/plans/00-master-plan.md` commiteado al repo.

### Día 1 — Kickoff
- [x] **Stream A**: schema DB v1 proposed in `docs/interfaces/db_schema_v1.sql`
      (English, hypertable PK fixed to include `ts`, CHECK constraints added).
- [x] **Stream A**: `PacePredictor` Protocol + `PaceContext` + `PacePrediction`
      defined in `backend/src/pitwall/engine/projection.py`
      (pending sign-off from Stream B).
- [x] **Stream A**: contract tests in `backend/tests/unit/engine/test_projection.py`.
- [x] **Stream A**: 2024 demo round numbers verified — Bahrain=1, Monaco=8, Hungary=13.
      README and walkthrough corrected (the previous `ROUND=11` for Hungary was
      Austria 2024).
- [x] **Stream B**: OpenAPI v1 finalised in `docs/interfaces/openapi_v1.yaml`
      (9 paths, 17 schemas, error responses, examples, validated with
      `openapi-spec-validator`).
- [x] **Stream B**: WebSocket message spec finalised in
      `docs/interfaces/websocket_messages.md` (8 server→client types,
      reconnect / heartbeat / backpressure semantics).
- [x] **Stream C**: dashboard wireframe captured in
      `docs/frontend_dashboard_wireframe.md`; Day 1 frontend contract checked
      against Stream B OpenAPI + WebSocket specs.
- [x] **Stream B**: Replay event format finalised in
      `docs/interfaces/replay_event_format.md` (8 event types,
      ordering guarantees, pacing algorithm).
- [x] **Stream A+B**: `PacePredictor` signed off. Cross-stream contract
      test in `backend/tests/contract/test_pace_predictor_contract.py`
      proves the engine's projection-loop call pattern works against
      Stream A's surface.
- [x] **Stream D**: platform audit complete (`chore/d-platform-audit-bootstrap`).
      Critical fix: `backend/pyproject.toml` had duplicate `dependencies = [` TOML error (Streams A+B
      appended without closing the array) — merged into one valid block and added `xgboost>=2.0`.
      Fixed 11 ruff errors + 5 mypy errors (import sorts, type annotations, missing `types-PyYAML`).
      Added `.github/workflows/lint.yml` + `test.yml`. Expanded `Makefile` with `up`, `down`,
      `down-v`, `logs`, `ps`, `seed`, `replay`, `demo`. Expanded `.env.example` with all 9 vars
      from `infra/README.md`. Added `models/.gitkeep`. All commands verified:
      `make install` ✅ · `make db-up` ✅ · `make migrate` ✅ · `make test` (67 passed) ✅ · `make lint` ✅.
      ADRs 0001-0009 already existed — no duplicate work needed.
      Next: Stream D Day 2 — `docker/backend.Dockerfile` multi-stage + `docker compose up` all 4 services.

### Día 2
- [x] **Stream D**: `docker compose up` funcional — `db` + `migrate` + `backend` (3 of 4 services; frontend pending Stream C).
      `docker/backend.Dockerfile` (python:3.12-slim, single-stage), `docker/postgres-init.sql`
      (timescaledb + pgcrypto), `.dockerignore`. `docker-compose.yaml` updated with `migrate`
      (one-shot, depends_on db healthy) and `backend` (depends_on migrate completed_successfully,
      `/health` healthcheck, port 8000). Smoke test: `/health`, `/ready`, `/api/v1/sessions` all
      respond 200 from container. `make test` (280 passed) and `make lint` remain green.
- [x] **Stream D**: GitHub Actions `lint.yml` + `test.yml` added (Day 1 carry-over, landed with audit PR).
- [x] **Stream B**: `RaceFeed` Protocol + event payload `TypedDict`s
      in `backend/src/pitwall/feeds/base.py`; `ReplayFeed` skeleton in
      `backend/src/pitwall/feeds/replay.py` with `t0`-anchored pacing
      and cancellable `stop()`; `OpenF1Feed` stub raises on
      instantiation per ADR 0002.
- [x] **Stream B**: FastAPI app at `backend/src/pitwall/api/main.py`
      with `/health`, `/ready`, and `/api/v1/sessions`. Sessions route
      reads from a `SessionRepository` Protocol injected via
      `app.dependency_overrides` — Stream A drops in a SQL
      implementation on Day 3 by editing one function. V1 default is
      `InMemorySessionRepository` with the three demo races.
- [x] **Stream B**: OpenAPI export script at
      `scripts/export_openapi.py` (JSON or YAML output). Contract test
      at `backend/tests/contract/test_openapi_export.py` enforces that
      every implemented route's `operationId` and tags match the
      static `docs/interfaces/openapi_v1.yaml`.
- [x] **Stream B**: 60 tests passing (10 replay + 8 API + 11 OpenAPI
      contract + 4 PacePredictor contract + 27 projection unit).
      `backend/pyproject.toml` extended with FastAPI/uvicorn/pydantic/
      pydantic-settings/structlog runtime deps and httpx/pyyaml/
      openapi-spec-validator dev deps; the additions are clearly
      labelled so Stream D's Day 1 becomes verify-and-extend.
- [x] Stream A: `scripts/ingest_season.py` funcional para 1 ronda.
      Day 2 scope narrowed to one FastF1 race/session: default Monaco 2024 round 8 session R,
      dry-run writer under `data/processed/`, DB mode deferred until Stream D DB/Alembic utilities land.
      Implemented FastF1 cache setup (`FASTF1_CACHE_DIR`, default `data/cache`),
      defensive normalization for metadata/drivers/laps/stints/pit stops/weather,
      timedelta-to-ms conversion, and null cleanup at write boundaries.
- [x] Stream A: Notebook 01_explore_fastf1.
      Implemented as `notebooks/01_explore_fastf1.md` to avoid noisy notebook JSON before exploratory plots exist.
- [x] Stream C: Vite app + TanStack Query consultando `/sessions`.
      `frontend/` bootstrapped from scratch: Vite 5 + React 18 + TypeScript 5 (strict),
      TanStack Query v5, Tailwind CSS 3 dark-theme, Recharts installed for later use.
      `src/api/types.ts` — hand-typed `SessionSummary`, `DriverState`, `RaceSnapshot`,
      `PredictorName`, `Compound`, `TrackStatus` from `openapi_v1.yaml` (TODO: codegen).
      `src/api/client.ts` — typed fetch helper, empty base URL (Vite proxy → `:8000`).
      `src/hooks/useSessions.ts` — TanStack Query hook, `staleTime: 60s`.
      `src/components/SessionPicker.tsx` — real sessions dropdown with loading/error/empty states.
      `src/components/RaceTable.tsx` — 7-column mock table with compound colour, undercut score bar.
      `src/App.tsx` — header + picker + table + WS-coming-soon panel.
      `pnpm build` ✅ · ESLint clean ✅ · Vitest 2 passed ✅ · `tsc` strict ✅.

### Día 3
- [x] Stream A: 2024 cargado a DB (3 carreras demo).
      Loaded Bahrain 2024 R (`bahrain_2024_R`), Monaco 2024 R (`monaco_2024_R`),
      and Hungary 2024 R (`hungary_2024_R`) through idempotent DB upserts.
      **Note**: a post-merge slug fix corrected `"hungarian_2024_R"` →
      `"hungary_2024_R"` in code. Alembic migrations
      `0003_canonical_hungary_slug.py` and
      `0004_canonical_hungary_coefficient_sources.py` repair existing local
      DBs without wiping the Docker volume.
      `make validate-demo` checks laps, stints, pit stops, weather, and clean lap availability.
      Latest local validation: Bahrain 1129 laps/63 stints/86 pit stops/157 weather rows;
      Monaco 1237/43/46/200; Hungary 1355/60/82/155.
- [x] Stream A: Alembic + migraciones reproducibles.
      Initial migration lives under `backend/src/pitwall/db/migrations/`, creates
      TimescaleDB/pgcrypto extensions, schema v1 tables, `laps` hypertable, and
      `clean_air_lap_times` materialized view. Repro path: `make db-up && make migrate`.
      DB utilities live in `backend/src/pitwall/db/engine.py`; Make targets cover
      DB lifecycle, migration, ingestion, validation, tests, and lint.
- [x] Stream A+B: ReplayFeed leyendo de DB real (no fixture).
      Added `SqlSessionRepository` and `SqlSessionEventLoader`, wired through
      `backend/src/pitwall/api/dependencies.py` when `DATABASE_URL` is
      configured. Local API smoke with Docker DB: `/api/v1/sessions` returned
      `bahrain_2024_R`, `monaco_2024_R`, `hungary_2024_R`; replay start/stop
      for `monaco_2024_R` returned 202/200 using DB events.
- [x] Stream C: SessionPicker + RaceTable mock funcional.
- [ ] Stream D: Dockerfile multi-stage para backend.

### Día 4
- [x] Stream A: `fit_degradation.py` funcional, R² reportado.
      Added clean-air diagnostic materialized view refresh, quadratic
      `quadratic_v1` fits by `(circuit_id, compound)`, idempotent persistence
      into `degradation_coefficients`, `make fit-degradation`, and
      `make validate-degradation`. Local DB validation on 2026-05-10 loaded
      8 coefficient rows from 3 demo races; all groups currently warn below
      R² 0.60 (best observed: Monaco MEDIUM R²=0.362, RMSE=1701 ms), so Day 5
      should improve filtering/normalization or document the limitation.
      Added Alembic `0002_clean_air_lap_times.py`, degradation unit tests, and
      `notebooks/02_fit_degradation.md`.
- [x] Stream A: `ScipyPredictor` implementado contra `PacePredictor`.
      `backend/src/pitwall/degradation/predictor.py` loads `quadratic_v1`
      coefficients, predicts from `PaceContext`, returns `PacePrediction`, and
      reports R² as confidence. Unit tests confirm protocol compatibility,
      missing-coefficient errors, and coefficient loading. Docker-backed smoke
      passed after fresh `make db-up && make migrate && make ingest-demo &&
      make fit-degradation`: Monaco MEDIUM tyre age 10 predicts 81,366 ms with
      confidence 0.362.
- [ ] Stream B: Motor undercut esqueleto + RaceState.
- [x] Stream C: Cliente API + hook WS esqueleto.
      `openapi-typescript` added as dev dep; `pnpm generate:api` generates `src/api/openapi.ts`
      from `docs/interfaces/openapi_v1.yaml`. `src/api/types.ts` replaced with re-export layer
      (stable import surface, no hand-written types). `src/api/client.ts` rewritten with `ApiError`,
      `buildUrl`, and 7 typed endpoint helpers (`getSessions`, `getSessionSnapshot`, `getDegradation`,
      `startReplay`, `stopReplay`, `setPredictor`, `getBacktestResult`). `src/api/ws.ts` added —
      hand-written WS envelope/payload types matching `websocket_messages.md`. `src/hooks/useRaceFeed.ts`
      added — reconnectable WS hook with 1→2→4→8→16 s backoff, StrictMode-safe `cancelled` flag,
      pong heartbeat response, and `snapshot`/`alerts`/`replayState`/`lastMessage`/`error`/`status` state.
      `useSessions` updated to use typed `getSessions()`. `RaceTable` optional-field types widened.
      All existing visual components preserved. `pnpm lint` ✅ · `pnpm test` 4/4 ✅ · `pnpm build` ✅.
- [ ] Stream D: Logs estructurados, /health endpoint.

### Día 5 — Hito S1
- [x] Stream A: Coeficientes en DB + notebook/reporte 02 con R²/RMSE reales.
      Clean DB verification on 2026-05-10 passed:
      `make test`, `make lint`, `make down-v`, `make migrate`,
      `make ingest-demo`, `make validate-demo`, `make fit-degradation`,
      and `make validate-degradation`. Persisted 8 `quadratic_v1`
      coefficient rows from 3 demo races. Best current fit remains Monaco
      MEDIUM (R²=0.362, RMSE=1701 ms); no group reaches the original R² ≥ 0.6
      target. This is documented as a functional low-R² MVP baseline, not as
      a tuned/high-quality degradation model. Added `make report-degradation`
      and explicit tests for `ScipyPredictor` DB-row loading, confidence clamp,
      missing coefficients, and Stream B `evaluate_undercut()` compatibility.
- [ ] Stream B: Motor calculando undercut V1 con `ScipyPredictor`.
- [x] Stream C: DegradationChart con Recharts y datos reales de la API.
      `src/hooks/useDegradation.ts` added — TanStack Query hook calling `getDegradation()`,
      stable key `["degradation", circuit, compound]`, `retry: false`. `src/components/DegradationChart.tsx`
      added — Recharts `LineChart` with fitted curve (computed from coefficients, tyre_age 0–40),
      optional scatter-style dots for `sample_points` (aggregated per lap), compound selector
      (SOFT/MEDIUM/HARD), R²/n display, and loading/error/empty states. `App.tsx` updated to
      derive `circuit` from selected session via `useSessions()` (falls back to "monaco"), then
      pass it to `DegradationChart` replacing `DegradationPlaceholder`. 4 new Vitest tests
      (loading, error, R² display, compound buttons). Day 4 API/WebSocket foundation preserved.
      `pnpm lint` ✅ · `pnpm test` 8/8 ✅ · `pnpm build` ✅ · `tsc --noEmit` ✅.
- [ ] Stream D: CI verde con tests reales.
- [ ] **Demo interna**: replay → motor → primer alert llega a un cliente WS de prueba.

## Semana 2

### Día 6.5
- [x] Stream A: driver/team pace offsets calculados y persistidos.
      Added `backend/src/pitwall/pace_offsets/` package (`models.py`, `estimation.py`,
      `writer.py`), `scripts/fit_driver_offsets.py`, `scripts/validate_driver_offsets.py`,
      `make fit-driver-offsets`, and `make validate-driver-offsets`.
      Method: group fitting-eligible clean-air laps by (circuit_id, compound); compute
      reference pace as median(all laps); driver offset = median(driver_lap_time_ms −
      reference_ms); persist only if n_samples ≥ 5; idempotent upsert.
      Local result on 3 demo races: 3503 clean-air laps → 103 offsets persisted, 4 skipped
      (insufficient data). Notable: VER monaco HARD −3782 ms, HAM monaco HARD −3685 ms,
      SAR monaco HARD +1852 ms. 25 unit tests added, all passing. No schema change needed —
      `driver_skill_offsets` table already existed. Added `notebooks/04_driver_team_offsets.md`.
      Next: Day 7 XGBoost dataset builder joins this table as attacker/defender pace features.

### Día 6
- [x] Stream A: pit loss por (circuito, equipo) calculado y persistido.
      Added `scripts/fit_pit_loss.py`, `scripts/validate_pit_loss.py`,
      `make fit-pit-loss`, `make validate-pit-loss`, Alembic
      `0005_pit_loss_circuit_fallback.py`, and runtime loading into the
      Stream B `EngineLoop` pit-loss table. Current clean DB fit uses 87
      realistic samples from the 3 demo races and writes 28 rows to
      `pit_loss_estimates`: Bahrain circuit median 25,071 ms, Monaco
      20,414 ms, Hungary 20,393 ms. Monaco has 6 usable samples after one
      extreme plausible outlier is quarantined, so its
      estimate is functional but still noisy. Follow-up refinement keeps
      runtime estimates median-based, adds outlier quarantine diagnostics,
      IQR/std/min/max reporting, quality labels, source labels, diagnostic
      trimmed/winsorized means, and a `__global__` conservative fallback for
      unseen tracks (23,274 ms on the demo set) without changing the DB schema.
- [ ] Stream A: lista curada de ~15 undercuts conocidos.
- [x] **Stream B**: endpoints REST conectados al estado real.
  `GET /api/v1/sessions/{session_id}/snapshot` returns live `RaceState` (404 when
  no active replay for that session). `GET /api/v1/degradation?circuit=&compound=`
  returns fitted quadratic coefficients (404 until `make fit-degradation` runs,
  400 on unknown compound). `DegradationRepository` seam added (same pattern as
  `SessionRepository`). `scripts/ws_demo_client.py` WebSocket demo client added.
  Contract test extended to 7 implemented paths — all `operationId`s match static spec.
  **198 tests, ruff clean, mypy clean.**
- [x] Stream C: tabla y feed conectados a WS real.
      `useRaceFeed` upgraded with `applyLapUpdate` / `applyPitStop` / `applyTrackStatus`
      pure helpers (exported for unit tests) and three new WS message handlers.
      `MAX_ALERTS` reduced 50 → 20. `AlertPanel` rewritten to accept real `AlertPayload[]`,
      shows attacker→defender, estimated gain, score/confidence, empty state, and CSS-only
      flash animation on newest alert entry. `RaceTable` gains `isLive?` / `connectionStatus?`
      props and an empty-state row. `TopBar` drives StatusDot colour from `ConnectionStatus`
      (green/yellow/red/white). `App.tsx` calls `useRaceFeed()` and threads `snapshot.drivers`,
      `alerts`, and `status` to all three components. 6 new Vitest tests (pure helpers) + 8
      AlertPanel tests + 2 new RaceTable tests; total 24 tests passing.
      `pnpm lint` ✅ · `pnpm typecheck` ✅ · `pnpm test` 24/24 ✅ · `pnpm build` ✅.
- [ ] Stream D: pre-commit, badges, README mejorado.

### Día 7
- [x] Stream A: dataset XGBoost preparado (features + split LORO).
      Added `backend/src/pitwall/ml/dataset.py`, `scripts/build_xgb_dataset.py`,
      `scripts/validate_xgb_dataset.py`, `make build-xgb-dataset`, and
      `make validate-xgb-dataset`. Target is `lap_time_delta_ms`, not raw
      `lap_time_ms`. Split is leave-one-race-out by `session_id`; reference
      pace and driver offsets are computed from fold training sessions only.
      Pit loss is explicitly excluded from the lap-level pace dataset and
      reserved for Day 9 undercut/backtest decision features. Artifacts are
      written under gitignored `data/ml/`. Notebook/report:
      `notebooks/05_xgb_dataset.md`.
- [x] **Stream B**: OpenAPI exportado y validado en CI.
  `POST /api/v1/config/predictor` (`setActivePredictor`) implemented — switches
  `scipy`/`xgboost` at runtime; 409 when XGBoost model missing; 422 on unknown name.
  Startup structlog events (`pitwall_startup` with `pace_predictor` field,
  `pitwall_shutdown`). `test_live_spec_is_valid_openapi` added to contract suite.
  "Validate live OpenAPI spec" step added to `ruff-mypy` CI job.
  `ignore_missing_imports = true` added to `[tool.mypy]` — no flag divergence.
  `xgb_model_path` setting added to `Settings`.
  **210 tests, ruff clean, mypy clean (80 files).**
- [x] Stream C: AlertFeed funcional + toggle predictor.
      `usePredictor.ts` hook wraps `setPredictor` API call, tracks `pendingTarget` and `error`.
      `PredictorToggle.tsx` renders scipy/xgboost radio buttons, shows optimistic pending state,
      "Switching…" label, 409-specific error ("XGBoost model not available. Staying on scipy."),
      and generic network error. `RaceTable` gains `activePredictor?` prop rendering a compact
      badge (`data-testid="predictor-badge"`). `TopBar` predictor chip now shows live
      `snapshot.active_predictor` instead of hardcoded "scipy". `App.tsx` threads
      `snapshot?.active_predictor` to TopBar, RaceTable, and PredictorToggle; PredictorToggle
      placed in right column between AlertPanel and Track Conditions. Day 6 live WS, Day 9
      BacktestView, and backend untouched. 10 new PredictorToggle tests + 3 new RaceTable tests;
      total 37 tests passing.
      `pnpm lint` ✅ · `pnpm typecheck` ✅ · `pnpm test` 37/37 ✅ · `pnpm build` ✅.
- [ ] Stream D: Dockerfile frontend + nginx prod.

### Día 8
- [x] Stream C: pulido visual mínimo completado.
      All four Day 8 tasks were addressed. Responsive horizontal scroll (`overflow-x-auto` +
      `min-w-[760px]`) and CSS-only alert flash animation (`@keyframes alert-flash`) were
      already in place from Days 3 and 6 respectively. New work this session: `ScoreBar` in
      `RaceTable.tsx` now clamps score to [0,1] and uses threshold 0.65 (was 0.6) for
      red/accent; palette consistency pass replaced `text-red-400` in `SessionPicker` error
      state with `text-pitwall-accent`; stale dev-day copy strings removed from
      `ReplayControls` and `TrackMapPanel`. Six new Vitest tests cover low/mid/high score
      colour classes, null score dash, and over-1 clamping; total 43 tests passing.
      `pnpm lint` ✅ · `pnpm typecheck` ✅ · `pnpm test` 43/43 ✅ · `pnpm build` ✅.
      Day 9 BacktestView not started.
- [x] **Stream A: XGBoost entrenado, serializado, métricas reportadas.**
  Added `backend/src/pitwall/ml/train.py`, `scripts/train_xgb.py`,
  `scripts/validate_xgb_model.py`, `make train-xgb`, and
  `make validate-xgb-model`. The trainer uses native `xgboost.Booster`,
  one-hot encoding for categorical features, explicit UNKNOWN handling,
  leave-one-race-out fold models for evaluation, and one final all-data
  runtime/demo model. Artifacts are gitignored:
  `models/xgb_pace_v1.json` and `models/xgb_pace_v1.meta.json`.
  Day 8.1 diagnostic refinement adds train-vs-holdout metrics, holdout target
  distributions, train-mean baseline, feature-gain importances, and explicit
  metadata diagnosis. Latest run on the 3 demo races: 10,509 dataset rows,
  3,503 unique holdout rows across folds, 57 encoded features. Aggregate train
  MAE/R²: 294.7 ms / 0.943. Aggregate holdout MAE/R²: 7,396.0 ms / -0.080.
  Zero-delta holdout MAE: 7,432.5 ms; train-mean holdout MAE: 7,423.2 ms.
  The model only improves aggregate MAE by 36.6 ms and Monaco remains worse
  than zero. Diagnosis: engineering-complete training pipeline, but weak
  holdout generalization on a 3-race split that is effectively
  leave-one-circuit-out. No evidence of a training/serialization bug; the
  limitation is data/reference coverage. Scipy comparison is deferred to Day 9.
- [x] **Stream B**: edge cases (SC/VSC/rain), `XGBoostPredictor` cargable.
  SC/VSC: `_on_lap_complete()` checks `track_status` — SC/VSC broadcasts
  `SUSPENDED_SC`/`SUSPENDED_VSC` and skips pair evaluation; GREEN evaluates normally.
  Rain: `evaluate_undercut()` returns `UNDERCUT_DISABLED_RAIN` when attacker or
  defender is on INTER/WET (case-insensitive). Recent pit: `defender.laps_in_stint < 2`
  returns `INSUFFICIENT_DATA`. `XGBoostPredictor` in `pitwall.ml.predictor`:
  `from_file()` loads `xgb.Booster` (no sklearn), `predict()` raises
  `UnsupportedContextError` (E10), `is_available()` returns `False`,
  satisfies `PacePredictor` Protocol. Optional `.meta.json` sidecar support.
  **234 tests, ruff clean, mypy clean (85 files).** 3 smoke tests pass.
- [ ] Stream C: pulido visual mínimo, responsive.
- [ ] Stream D: test suite verde, ADRs revisados.

### Día 9
- [x] **Stream C: BacktestView frontend completado.**
  `src/hooks/useBacktest.ts` — TanStack Query hook wrapping `getBacktestResult()`, disabled when
  `sessionId` is falsy, `predictor` included in query key, `retry: false`, `staleTime: 5 min`.
  `src/components/BacktestView.tsx` — two-column panel (scipy | xgboost) inside `App.tsx`
  center column, below DegradationChart + TrackMapPanel grid. Each panel shows precision/recall/f1
  as percentages, optional lead-time and MAE k1/k3/k5 metrics, and TP/FP/FN match tables
  (attacker, defender, lap alerted, lap actual). Empty state when no session selected; per-predictor
  loading/unavailable states; one erroring predictor does not hide the other.
  15 new Vitest tests — all passing. Total: 58 tests.
  `pnpm lint` ✅ · `pnpm typecheck` ✅ · `pnpm test` 58/58 ✅ · `pnpm build` ✅.
  Day 6 WS, Day 7 PredictorToggle, Day 8 visual polish untouched.
  **Frontend view complete; actual backtest data depends on backend/Stream A+B data availability.**
- [ ] **Stream A+B: backtest comparativo scipy vs XGBoost completo.**
- [x] **Stream B**: confidence final, `data_quality_factor`, calibratable cold-tyre penalties,
  hypothesis property tests, and `/api/v1/backtest/{session_id}` endpoint.
  `_data_quality_factor(atk)` reduces confidence for short stints (< 8 laps → linear ramp)
  and traffic (gap < 1500 ms → −0.2). `project_pace()` accepts optional `cold_tyre_penalties`
  tuple (defaults to `COLD_TYRE_PENALTIES_MS`). New `engine/calibration.py` with
  `calibrate_cold_tyre_penalties()`. 5 hypothesis invariant tests (1700 total examples).
  Backtest endpoint returns 404 until Stream A populates curated list (E9-E10).
  **265 tests (231 unit + 34 contract), ruff clean, mypy clean (89 files).**
- [ ] Stream C: backtest view en UI.
- [ ] Stream D: `make demo` end-to-end probado en máquina limpia.

### Día 10 — Entrega
- [ ] Stream A: quanta `06-curva-fit-vs-xgboost.md` escrita con números reales.
- [ ] Stream A: ADR `0009-xgboost-vs-scipy-resultados.md` cerrado.
- [x] **Stream B**: dry-run con ambos predictores, WS reconnect, `replay_state` broadcasts.
  `EngineLoop.get_snapshot()` method added. WS handler sends current snapshot on (re)connect.
  `POST /api/v1/replay/start` and `POST /api/v1/replay/stop` broadcast `replay_state`
  to all WS clients. 13 end-to-end in-process pipeline tests: full pipeline with
  ScipyPredictor, predictor switching, XGBoostPredictor stub graceful handling, alert
  payload shape, replay_state integration (HTTP + WS). 2 new WS reconnect tests.
  **280 tests (246 unit + 34 contract), ruff clean, mypy clean (90 files).**
- [x] **Stream B**: causal undercut Phase 1-2 verificada y pre-Phase 3 prep ejecutada.
  Added `make reconstruct-race-gaps` and `scripts/reconstruct_race_gaps.py` to populate
  `laps.gap_to_leader_ms` / `gap_to_ahead_ms` from FastF1 lap-end timestamps without a
  schema change. Local DB volume prep result: gaps populated at 99.9% leader / 94.4% ahead
  coverage, degradation coefficients=8, pit-loss estimates=28, driver offsets=103.
  Added `make derive-known-undercuts` to populate observed pit-cycle outcomes without
  waiting for manual curation. Final local DB volume prep result: `known_undercuts=35`
  (`13` successful, `22` unsuccessful). Phase 3 is unblocked for `undercut_viable`
  label construction and initial success/backtest evaluation; labels must still carry
  source/confidence flags.
- [x] **Stream B**: causal undercut Phase 3-4 implemented independently from XGBoost.
  Added `pitwall.causal.dataset_builder`, `pitwall.causal.labels`, and
  `make build-causal-dataset`. Latest local output:
  `data/causal/undercut_driver_rival_lap.parquet` with 3,512 driver-rival-lap rows,
  3,512 usable rows, 1,026 `undercut_viable=true` rows, and 14 observed
  `undercut_success` labels. Metadata records `pace_source=causal_scipy` and states
  XGBoost features/predictions/importances are not used.
- [x] **Stream B**: causal undercut Phase 5-6 implemented.
  Added `pitwall.causal.graph` with the domain-authored DAG, DOT/GML exports,
  treatment/outcome/confounder lists, and acyclic validation tests. Added ADR 0010
  and persisted `dowhy>=0.12,<0.14` in `backend/pyproject.toml`. Added
  `pitwall.causal.estimators` and `make run-causal-dowhy` for the first DoWhy
  prototype over the causal driver-rival-lap dataset. XGBoost remains untouched.
- [x] **Stream B**: causal undercut Phase 7-10 implemented.
  Added DoWhy refuters (`random_common_cause`, `placebo_treatment_refuter`,
  `data_subset_refuter`) to `make run-causal-dowhy`, plus stability reporting for
  unsupported effects. Added `pitwall.causal.live_inference` and
  `pitwall.causal.explain` for current-lap `undercut_viable`, support level,
  counterfactual scenarios (`base_case`, `pit_now`, `pit_next_lap`,
  traffic high/low, pit-loss ±1000 ms), top factors, and human-readable
  explanations. No API/WS shape changed; interface docs do not need updates yet.
  Latest refuter read on the original demo dataset: `fresh_tyre_advantage_ms`
  and `gap_to_rival_ms` are stable; `tyre_age_delta` is unstable under placebo
  and should not be treated as robust causal evidence yet.
- [x] **Stream B**: causal undercut corrections implemented after Phase 10.
  Added `make prepare-causal-extended-data` for multi-race ingestion and causal
  artifact rebuilds, plus `fit_degradation.py --all-sessions` so new races
  actually contribute degradation coefficients. Added `make
  import-curated-known-undercuts` and `data/curation/known_undercuts_curated.csv`
  for human-reviewed labels without overwriting auto-derived rows. Improved
  `traffic_after_pit` with projected pit-exit gap/position, nearby-car count,
  and nearest-traffic gap. Added `make compare-causal-engines` producing
  `data/causal/engine_disagreements.csv`. Local verified run added
  `mexico_city_2024_R`: causal dataset now has 4,654 rows, 4,586 usable rows,
  1,022 viable rows, and 19 observed success rows. DoWhy refuters are stable for
  all three default treatments on this four-race dataset. XGBoost comparison is
  reported as `unavailable_feature_pipeline` until Stream A wires runtime XGB
  prediction.
- [ ] Stream C: copy y branding mínimo, demo polish.
- [x] **Stream D**: quickstart/runbook corrected to match current implementation.
  README, walkthrough, infra README, runbook, and docker-compose architecture now state
  the current truth: `make demo` is DB + local migration + 3-race ingest, backend can be
  started with `docker compose up -d backend`, and frontend/browser demo remains pending.
  Added Makefile targets `ingest`, `test-backend`, and `serve-api` so documented commands exist.
- [ ] Stream D: changelog v0.1.0, video demo enlazado.
- [ ] **Tag `v0.1.0` y release notes.**

## Bloqueos activos

_(ninguno por ahora)_

## Decisiones tomadas

| Fecha | Decisión | ADR |
|-------|----------|-----|
| 2026-05-09 | Stack base: Python+FastAPI+React+TimescaleDB | 0001 |
| 2026-05-09 | Replay-first en V1, no live OpenF1 | 0002 |
| 2026-05-09 | TimescaleDB sí, Redis no en V1 | 0003 |
| 2026-05-09 | Baseline scipy → XGBoost (LSTM fuera) | 0004 |
| 2026-05-09 | Monorepo backend + frontend | 0005 |
| 2026-05-09 | Polars sobre pandas | 0006 |
| 2026-05-09 | asyncio in-process, sin broker | 0007 |
| 2026-05-09 | OpenAPI auto-generado como fuente de verdad | 0008 |
| 2026-05-?? | Resultado XGBoost vs scipy | 0009 (post-E10) |
| 2026-05-14 | DoWhy para causal undercut offline/refuters | 0010 |
