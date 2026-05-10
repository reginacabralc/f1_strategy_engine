# Progreso

> Vivo. Se actualiza en cada PR. Alguien del stream que mergea actualiza la línea correspondiente.

## Hitos

| Hito | Estado | Fecha objetivo | Notas |
|------|--------|----------------|-------|
| Andamiaje docs creado | ✅ | Día 0 | Este commit |
| Setup repo + Docker + CI verde | ⏳ | Día 2 | Stream D |
| Kickoff e interfaces acordadas | ⏳ | Día 1 | Todos |
| 1 temporada (2024) ingerida en DB | ⏳ | Día 3 | Stream A |
| Replay engine funcional con fixture | ⏳ | Día 3 | Stream B |
| Dashboard mock conectado a `/sessions` | ⏳ | Día 3 | Stream C |
| Curva de degradación scipy ajustada | ⏳ | Día 5 | Stream A |
| Motor undercut V1 con `ScipyPredictor` | ⏳ | Día 5 | Stream B |
| Pipeline end-to-end con datos reales | ⏳ | Día 7 | Todos |
| **XGBoost entrenado y serializado** | ⏳ | Día 8 | Stream A |
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
- [ ] Stream B: OpenAPI v1 esqueleto + WebSocket messages.
- [ ] Stream B: Replay event format propuesto.
- [ ] Stream A+B: `PacePredictor` signature signed off (waiting on B).
- [ ] Stream D: branch `bootstrap` con `.gitignore`, pyproject.toml, package.json, docker-compose esqueleto.
- [ ] Stream D: ADRs 0001-0004 escritos.

### Día 2
- [ ] Stream D: docker-compose up funcional (3 servicios up sin errores).
- [ ] Stream D: GitHub Actions lint + test corriendo en PR.
- [x] Stream A: `scripts/ingest_season.py` funcional para 1 ronda.
      Day 2 scope narrowed to one FastF1 race/session: default Monaco 2024 round 8 session R,
      dry-run writer under `data/processed/`, DB mode deferred until Stream D DB/Alembic utilities land.
- [x] Stream A: Notebook 01_explore_fastf1.
      Implemented as `notebooks/01_explore_fastf1.md` to avoid noisy notebook JSON before exploratory plots exist.
- [ ] Stream B: `RaceFeed` interface + `ReplayFeed` con fixture sintético.
- [ ] Stream C: Vite app + TanStack Query consultando `/sessions`.

### Día 3
- [ ] Stream A: 2024 cargado a DB (3 carreras demo).
- [ ] Stream A: Alembic + migraciones reproducibles.
- [ ] Stream B: ReplayFeed leyendo de DB real (no fixture).
- [ ] Stream C: SessionPicker + RaceTable mock funcional.
- [ ] Stream D: Dockerfile multi-stage para backend.

### Día 4
- [ ] Stream A: `fit_degradation.py` funcional, R² reportado.
- [ ] Stream B: Motor undercut esqueleto + RaceState.
- [ ] Stream C: Cliente API + hook WS esqueleto.
- [ ] Stream D: Logs estructurados, /health endpoint.

### Día 5 — Hito S1
- [ ] Stream A: Coeficientes en DB + notebook 02 con R² ≥ 0.6.
- [ ] Stream B: Motor calculando undercut V1 con `ScipyPredictor`.
- [ ] Stream C: DegradationChart con datos mock.
- [ ] Stream D: CI verde con tests reales.
- [ ] **Demo interna**: replay → motor → primer alert llega a un cliente WS de prueba.

## Semana 2

### Día 6
- [ ] Stream A: pit loss por (circuito, equipo) calculado y persistido.
- [ ] Stream A: lista curada de ~15 undercuts conocidos.
- [ ] Stream B: endpoints REST conectados al estado real.
- [ ] Stream C: tabla y feed conectados a WS real.
- [ ] Stream D: pre-commit, badges, README mejorado.

### Día 7
- [ ] Stream A: dataset XGBoost preparado (features + split LORO).
- [ ] Stream B: OpenAPI exportado y validado en CI.
- [ ] Stream C: AlertFeed funcional + toggle predictor.
- [ ] Stream D: Dockerfile frontend + nginx prod.

### Día 8
- [ ] **Stream A: XGBoost entrenado, serializado, métricas reportadas.**
- [ ] Stream B: edge cases (SC/VSC/rain), `XGBoostPredictor` cargable.
- [ ] Stream C: pulido visual mínimo, responsive.
- [ ] Stream D: test suite verde, ADRs revisados.

### Día 9
- [ ] **Stream A+B: backtest comparativo scipy vs XGBoost completo.**
- [ ] Stream B: confidence final + flag `PACE_PREDICTOR`.
- [ ] Stream C: backtest view en UI.
- [ ] Stream D: `make demo` end-to-end probado en máquina limpia.

### Día 10 — Entrega
- [ ] Stream A: quanta `06-curva-fit-vs-xgboost.md` escrita con números reales.
- [ ] Stream A: ADR `0009-xgboost-vs-scipy-resultados.md` cerrado.
- [ ] Stream B: dry-run completo Mónaco con ambos predictores.
- [ ] Stream C: copy y branding mínimo, demo polish.
- [ ] Stream D: walkthrough actualizado, changelog v0.1.0, video demo enlazado.
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
