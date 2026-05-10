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

### Pendiente para v0.1.0 (entrega MVP)

- [ ] Ingestor histórico FastF1 → TimescaleDB para 2024 (3 carreras demo).
- [ ] Modelo de degradación scipy ajustado por (circuito × compuesto).
- [ ] Replay Engine reproduciendo Mónaco 2024.
- [ ] Motor de undercut con `ScipyPredictor`.
- [ ] FastAPI REST + WebSocket emitiendo alertas.
- [ ] Dashboard React con tabla, charts y feed.
- [ ] **XGBoost entrenado e integrado vía `PacePredictor`.**
- [ ] **Backtest comparativo scipy vs XGBoost.**
- [ ] docker-compose con `make demo` funcional.
- [ ] CI verde (lint + tests + build de imágenes).
- [ ] ADR 0009 cerrado con resultados reales.

## [0.1.0] — Por publicar (objetivo: ~2026-05-22)

Primera entrega del MVP del sprint de 2 semanas. Demo end-to-end con replay de carrera + alertas + comparación de predictores.
