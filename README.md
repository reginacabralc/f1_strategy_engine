# PitWall — F1 Strategy Engine

> Motor en tiempo real que detecta oportunidades de **undercut** durante una carrera de F1, comparando un baseline heurístico (`scipy`) contra un modelo ML (`XGBoost`) detrás de la misma interfaz. El backend, WebSocket, replay histórico y dashboard React ya existen; Stream D mantiene la ruta reproducible de demo.

[![Lint](https://github.com/reginacabralc/f1_strategy_engine/actions/workflows/lint.yml/badge.svg)](.github/workflows/lint.yml)
[![Tests](https://github.com/reginacabralc/f1_strategy_engine/actions/workflows/test.yml/badge.svg)](.github/workflows/test.yml)
[![Build](https://github.com/reginacabralc/f1_strategy_engine/actions/workflows/build.yml/badge.svg)](.github/workflows/build.yml)
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
                                                  │ React UI   │
                                                  │ :5173      │
                                                  └────────────┘
```

Más detalle: [`docs/architecture.md`](docs/architecture.md).

## Quickstart

Pre-requisitos: Docker Desktop, GNU Make, Python 3.12 recomendado, ~10 GB libres, internet para descargar datos de FastF1 la primera vez.

```bash
git clone https://github.com/reginacabralc/f1_strategy_engine.git
cd f1_strategy_engine
cp .env.example .env
make demo
```

`make demo` levanta TimescaleDB, crea `.venv`, instala el backend, corre migraciones, carga las 3 carreras demo de 2024 (Bahrain, Monaco y Hungary), ajusta coeficientes de degradación demo, arranca backend + frontend con Docker Compose y abre el dashboard React en <http://localhost:5173>. Swagger queda disponible en <http://localhost:8000/docs>.

PostgreSQL se publica en `localhost:5433` para no chocar con instalaciones locales que suelen usar `5432`. Dentro de Docker los servicios siguen usando `db:5432`.

Para probar la API manualmente:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/sessions
```

Ver más en [`docs/walkthrough.md`](docs/walkthrough.md).

## Replay another race

```bash
make ingest YEAR=2024 ROUND=13   # Hungarian GP (round 13 of 2024)
curl -X POST http://localhost:8000/api/v1/replay/start \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"hungary_2024_R","speed_factor":30}'
```

Demo race round numbers for 2024: **Bahrain = 1**, **Monaco = 8**, **Hungary = 13**.

## Stack

- **Backend**: Python 3.12, FastAPI, asyncio, Polars, scipy, **XGBoost**
- **DB**: PostgreSQL 15 + TimescaleDB
- **Frontend**: React + Vite + TypeScript + TanStack Query + Tailwind + Recharts
- **Infra**: docker-compose
- **CI**: GitHub Actions (`lint`, `test`, `build`)
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
