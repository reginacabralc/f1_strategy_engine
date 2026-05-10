# AGENTS.md

Guía operativa para agentes (Claude Code, Codex, Cursor, etc.) y para humanos que trabajan en este repo. Más compacto que [CLAUDE.md](CLAUDE.md), enfocado en cómo se entrega una tarea.

## Roles (4 streams)

| Stream | Responsabilidad principal | Owns |
|--------|---------------------------|------|
| **A — Datos & ML** | Ingesta FastF1, schema DB, degradación scipy, XGBoost, backtest | `backend/src/pitwall/ingest/`, `backend/src/pitwall/degradation/`, `backend/src/pitwall/ml/`, `notebooks/`, `scripts/ingest_*.py`, `scripts/fit_*.py`, `scripts/train_xgb.py` |
| **B — Motor & API** | Replay engine, motor de undercut, FastAPI, WebSocket | `backend/src/pitwall/feeds/`, `backend/src/pitwall/engine/`, `backend/src/pitwall/api/` |
| **C — Frontend** | Dashboard React, charts, hooks | `frontend/` |
| **D — Plataforma** | Docker, CI, tests, docs, ADRs, observabilidad | `docker/`, `.github/workflows/`, `Makefile`, `docker-compose.yaml`, `docs/`, `infra/` |

Detalles por stream: [`.claude/plans/stream-a-data.md`](.claude/plans/stream-a-data.md), [`stream-b-engine.md`](.claude/plans/stream-b-engine.md), [`stream-c-frontend.md`](.claude/plans/stream-c-frontend.md), [`stream-d-platform.md`](.claude/plans/stream-d-platform.md).

## Cómo arrancar una tarea

1. Leer el plan del stream correspondiente y la entrada en [`docs/progress.md`](docs/progress.md).
2. Si la tarea no está, abrir issue (o agregar al plan del stream).
3. `git pull main && git checkout -b feat/<stream>-<short-name>` (ej. `feat/b-undercut-edge-cases`).
4. Trabajar, commits pequeños, conventional commits.
5. PR contra `main`, ≤ 400 líneas idealmente, descripción con qué/por qué/cómo testeé.
6. CI verde es bloqueante. Mínimo 1 reviewer (idealmente del stream que consume tu output).
7. Squash merge, eliminar branch.

## Convenciones de commits

[Conventional Commits](https://www.conventionalcommits.org/):

```
feat(engine): add cold-tyre penalty to attacker projection
fix(api): handle missing track_status in lap_update
refactor(ingest): use Polars LazyFrame for stints reconstruction
docs(quanta): explain pit loss derivation
test(undercut): cover SC suspension path
chore(docker): pin timescaledb image to pg15
```

Tipos: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `perf`, `ci`.

Scopes comunes: `engine`, `api`, `ws`, `feeds`, `ingest`, `degradation`, `ml`, `db`, `frontend`, `docker`, `ci`, `quanta`, `adr`.

## Definition of Done

Una tarea está hecha cuando:

- [ ] Código + tests + docs en el mismo PR.
- [ ] CI verde.
- [ ] Si tocó interfaz compartida: documentación actualizada en [`docs/interfaces/`](docs/interfaces/) y avisado al equipo.
- [ ] Si introdujo decisión arquitectónica: ADR escrito en [`docs/adr/`](docs/adr/).
- [ ] Si afectó cómo correr el sistema: [`docs/walkthrough.md`](docs/walkthrough.md) actualizado.
- [ ] Sin TODOs nuevos sin issue asignado.
- [ ] Mergeado y branch eliminado.

## Interfaces compartidas — qué tocas con cuidado

Estos archivos los consumen múltiples streams. **No están prohibidos de tocar**, pero si los tocas:

1. Avisas en el daily o en el canal del equipo antes del merge.
2. Mencionas el cambio en el PR description.
3. Actualizas a los consumers afectados en el mismo PR (o los abres como issues con prioridad alta).

Lista:

- [`docs/interfaces/db_schema_v1.sql`](docs/interfaces/db_schema_v1.sql)
- [`docs/interfaces/openapi_v1.yaml`](docs/interfaces/openapi_v1.yaml)
- [`docs/interfaces/websocket_messages.md`](docs/interfaces/websocket_messages.md)
- [`docs/interfaces/replay_event_format.md`](docs/interfaces/replay_event_format.md)
- La interfaz `PacePredictor` en `backend/src/pitwall/engine/projection.py` (cuando exista).

## Cómo correr tests localmente
- If running a python file or downloading a pip library, always activate the local .venv if not created, make one.

```bash
make lint       # ruff + eslint + prettier
make test       # pytest backend + vitest frontend

# Backend solo:
cd backend && uv run pytest tests/unit -v
cd backend && uv run pytest tests/integration -v   # requiere docker

# Frontend solo:
cd frontend && pnpm test
cd frontend && pnpm test:e2e   # Playwright
```

## Qué hacer cuando el dato real contradice una asunción

Pasa: el plan asume X, pero al ingerir FastF1 ves que X no se cumple (ej. compuesto vacío en 2022, vuelta inválida marcada distinto, etc.).

1. **No lo silencies con un `try/except: pass`.** Esto es lo peor.
2. Documentas el caso real en una **quanta nueva** o en una existente.
3. Si la solución cambia una decisión, **abres ADR** que explique antes/después.
4. Si afecta a otro stream (lo más común), avisas.

Ejemplos:

- "FastF1 no reporta `Compound` en algunos GP de 2022" → quanta sobre limpieza de datos + filtro en ingestor + ADR si decidimos excluir 2022 del entrenamiento.
- "El R² del fit en Mónaco × MEDIUM es 0.4, no 0.7" → quanta explicando por qué (pocas vueltas, pocas paradas, mucho SC) + ajustar target en plan.

## Reglas para agentes generativos

Si un agente (incluido tú, Claude Code) está trabajando autónomamente:

- **Antes de escribir código**: lee `CLAUDE.md`, el plan del stream relevante, y el archivo más cercano que vas a tocar.
- **No inventes endpoints** ni mensajes WS sin actualizar `docs/interfaces/`.
- **No introduzcas dependencias nuevas** sin escribir un ADR mínimo (1 párrafo).
- **No hagas commits grandes** que mezclen dominios (front + back en un PR es señal de mal scope).
- **Reporta progreso** actualizando `docs/progress.md` antes de cerrar la sesión.
- **Si no sabes**, dilo. No inventes.

## Plan de contingencia (resumen)

- Si tu stream se atrasa, lo dices en el daily y rebalanceamos.
- Lo único innegociable: el componente de ML (XGBoost integrado vía `PacePredictor`). El profesor pidió ML — sin eso, no hay entrega.
- Si XGBoost no gana al baseline, documentamos el resultado honesto en ADR 0009 y entregamos igual.

## Referencias rápidas

- Plan maestro completo: [`.claude/plans/00-master-plan.md`](.claude/plans/00-master-plan.md)
- Arquitectura: [`docs/architecture.md`](docs/architecture.md)
- Walkthrough: [`docs/walkthrough.md`](docs/walkthrough.md)
- Gameplan 4 personas: [`docs/gameplan_4people.md`](docs/gameplan_4people.md)
