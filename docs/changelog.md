# Changelog

Todos los cambios notables de este proyecto se documentan aquí.

Formato basado en [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), versionado [SemVer](https://semver.org/lang/es/).

## [Unreleased]

### Added

- Andamiaje inicial del repo: CLAUDE.md, AGENTS.md, README expandido.
- Plan maestro completo en `.claude/plans/00-master-plan.md`.
- ADRs 0001-0008 esqueleto.
- Quanta 01-08 esqueleto.
- Interfaces compartidas esqueleto en `docs/interfaces/`.
- Documentación de infra en `infra/`.
- Planes por stream en `.claude/plans/stream-{a,b,c,d}.md`.
- Docker Compose con `db`, `migrate`, `backend` y `frontend`.
- `make demo` full-stack: migraciones, seed demo, coeficientes de degradación,
  backend, frontend y Swagger.
- FastAPI REST + WebSocket con `/health`, `/ready`, sesiones, replay,
  degradación, backtest y configuración de predictor.
- Dashboard React/Vite con selector de sesión, tabla, feed WebSocket,
  controles de replay, degradación y panel de backtest.
- Pipeline scipy de degradación persistido en DB y targets XGBoost en Makefile.
- CI `lint`, `test` y `build` en GitHub Actions.

### Pendiente para v0.1.0 (entrega MVP)

- [x] Ingestor histórico FastF1 → TimescaleDB para 2024 (3 carreras demo).
- [x] Modelo de degradación scipy ajustado por (circuito × compuesto).
- [x] Replay Engine reproduciendo Mónaco 2024 desde DB.
- [x] FastAPI REST + WebSocket base.
- [x] Dashboard React con tabla, charts, feed y controles de replay.
- [x] docker-compose con `make demo` funcional para backend + frontend.
- [x] CI local y workflows para lint, tests y build de imágenes.
- [ ] Motor de undercut V1 emitiendo alertas demo con `ScipyPredictor`.
- [ ] **XGBoost integrado en runtime vía `PacePredictor`.**
- [ ] **Backtest comparativo scipy vs XGBoost.**
- [ ] ADR 0009 cerrado con resultados reales.

## [0.1.0] — Por publicar (objetivo: ~2026-05-22)

Primera entrega del MVP del sprint de 2 semanas. Demo end-to-end con replay de carrera + alertas + comparación de predictores.
