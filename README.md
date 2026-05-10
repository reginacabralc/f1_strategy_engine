# PitWall — F1 Strategy Engine

> Motor en tiempo real que detecta oportunidades de **undercut** durante una carrera de F1, comparando un baseline heurístico (`scipy`) contra un modelo ML (`XGBoost`) detrás de la misma interfaz, con dashboard React, WebSocket y replay reproducible de carreras históricas.

[![Lint](https://img.shields.io/badge/lint-pending-lightgrey)](.github/workflows/lint.yml)
[![Tests](https://img.shields.io/badge/tests-pending-lightgrey)](.github/workflows/test.yml)
[![Build](https://img.shields.io/badge/build-pending-lightgrey)](.github/workflows/build.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

## ¿Qué hace?

Cuando un piloto entra a boxes pierde ~21 segundos. Para que un *undercut* (parar antes que el rival) sea viable, hay que recuperar ese tiempo siendo más rápido con neumáticos nuevos antes de que el rival también pare. PitWall calcula esa ventana en vivo para cada par de pilotos consecutivos en pista, y emite alertas con score y ganancia estimada.

```
┌─────────────────┐      ┌────────────────┐      ┌──────────────┐
│  Replay Engine  │─────▶│ Undercut Engine│─────▶│  WebSocket   │
│  (FastF1 hist.) │      │ scipy | xgb    │      │  + REST API  │
└─────────────────┘      └────────────────┘      └──────┬───────┘
                                                         │
                                                  ┌──────▼─────┐
                                                  │  React UI  │
                                                  └────────────┘
```

Más detalle: [`docs/architecture.md`](docs/architecture.md).

## Quickstart

Pre-requisitos: Docker Desktop, GNU Make, ~10 GB libres.

```bash
git clone https://github.com/<owner>/f1_strategy_engine.git
cd f1_strategy_engine
cp .env.example .env
make demo
```

Esto levanta la base de datos, corre migraciones, carga 1 carrera de demo (Mónaco 2024), arranca backend en `http://localhost:8000` y frontend en `http://localhost:5173`. Ver más en [`docs/walkthrough.md`](docs/walkthrough.md).

## Replay another race

```bash
make ingest YEAR=2024 ROUND=13   # Hungarian GP (round 13 of 2024)
make replay SESSION=hungary_2024_R SPEED=30
```

Demo race round numbers for 2024: **Bahrain = 1**, **Monaco = 8**, **Hungary = 13**.

## Stack

- **Backend**: Python 3.12, FastAPI, asyncio, Polars, scipy, **XGBoost**
- **DB**: PostgreSQL 15 + TimescaleDB
- **Frontend**: React + Vite + TypeScript + TanStack Query + Tailwind + Recharts
- **Infra**: docker-compose
- **CI**: GitHub Actions
- **Datos abiertos**: [FastF1](https://docs.fastf1.dev/), [OpenF1](https://openf1.org), [Jolpica](https://github.com/jolpica/jolpica-f1) (sucesor de Ergast)

## ML

PitWall integra dos predictores de pace intercambiables detrás de la interfaz `PacePredictor`:

1. **`ScipyPredictor`** — baseline paramétrico (cuadrática por circuito × compuesto).
2. **`XGBoostPredictor`** — modelo entrenado con features: tyre_age, compound, circuit, track_temp, lap_in_stint_ratio, driver/team, fuel_proxy.

Switch en runtime con `PACE_PREDICTOR=scipy|xgb`. Resultados del experimento en [`docs/adr/0009-xgboost-vs-scipy-resultados.md`](docs/adr/0009-xgboost-vs-scipy-resultados.md) y [`docs/quanta/06-curva-fit-vs-xgboost.md`](docs/quanta/06-curva-fit-vs-xgboost.md).

## Estado actual

Proyecto en construcción activa (sprint 2 semanas, equipo de 4). Ver [`docs/progress.md`](docs/progress.md) para el avance día a día.

## Documentación

- 📐 **Arquitectura**: [`docs/architecture.md`](docs/architecture.md)
- 🚶 **Walkthrough end-to-end**: [`docs/walkthrough.md`](docs/walkthrough.md)
- 🧠 **Quanta** (conceptos clave explicados): [`docs/quanta/`](docs/quanta/)
- 🏗️ **ADRs** (decisiones arquitectónicas): [`docs/adr/`](docs/adr/)
- 🔌 **Interfaces compartidas**: [`docs/interfaces/`](docs/interfaces/)
- 🛠️ **Infra & runbook**: [`infra/`](infra/)
- 📋 **Plan maestro**: [`.claude/plans/00-master-plan.md`](.claude/plans/00-master-plan.md)
- 🎯 **Gameplan 4 personas**: [`docs/gameplan_4people.md`](docs/gameplan_4people.md)
- 📓 **Bitácora**: [`docs/blog.md`](docs/blog.md)
- 📜 **Changelog**: [`docs/changelog.md`](docs/changelog.md)

## Equipo

| Rol (Stream) | Nombre | Owns |
|--------------|--------|------|
| A — Datos & ML | _por asignar_ | ingest, degradation, ML |
| B — Motor & API | _por asignar_ | engine, replay, FastAPI, WS |
| C — Frontend | _por asignar_ | React dashboard |
| D — Plataforma | _por asignar_ | Docker, CI, docs, infra |

## Contribuir

Lee [`AGENTS.md`](AGENTS.md) (humanos también — mismo flujo). Conventional Commits, PRs ≤ 400 líneas, CI verde antes de merge.

## Licencia

MIT — ver [`LICENSE`](LICENSE).

## Referencias

- [FastF1 docs](https://docs.fastf1.dev/)
- [OpenF1 API](https://openf1.org)
- [Jolpica F1 API](https://github.com/jolpica/jolpica-f1)
- [TimescaleDB](https://www.timescale.com/)
