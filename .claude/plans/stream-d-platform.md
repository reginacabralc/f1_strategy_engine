# Stream D — Plataforma

> Owner: _por asignar_. Backup: Stream B.
> Cubre Etapas 1, 11, 12 + soporte transversal.

## Mantra

"Si la demo no se reproduce en máquina limpia en < 10 min, no hay demo."

## Responsabilidades

1. Setup del repo (pyproject.toml, package.json).
2. Docker: backend, frontend, postgres init.
3. docker-compose.yaml con healthchecks reales.
4. CI: GitHub Actions (lint, test, build).
5. Tests: scaffolding pytest + vitest + Playwright.
6. ADRs (escritura, no decisiones técnicas — esas son de los streams).
7. Observabilidad mínima: structlog, /health, /ready.
8. Documentación operativa (`infra/`, walkthrough).

## Archivos owned

```
docker-compose.yaml
docker/backend.Dockerfile, frontend.Dockerfile, postgres-init.sql
.github/workflows/lint.yml, test.yml, build.yml
Makefile
backend/pyproject.toml
backend/tests/conftest.py
.env.example
.gitignore
.pre-commit-config.yaml
infra/
docs/adr/  # escribir junto con stream que decidió
docs/walkthrough.md (mantenimiento)
```

## Tareas

### Día 1 — Kickoff + bootstrap (E1)
- [x] Branch `bootstrap`.
      Implementado sobre la rama activa `causal2`; no se creó/renombró rama
      para evitar mover trabajo existente.
- [x] `.gitignore` Python+Node+Docker.
- [x] `backend/pyproject.toml` con `uv` (Python 3.12, FastAPI, asyncio, polars, scipy, xgboost, pytest, ruff, mypy).
- [x] `frontend/package.json` con Vite + React + TS + Tailwind.
- [x] Esqueleto `docker-compose.yaml` (servicios placeholder).
- [x] `Makefile` con targets vacíos: `up`, `down`, `test`, `lint`, `seed`, `migrate`, `replay`, `demo`.
- [x] ADRs 0001-0004 escritos (stack, replay-first, timescale, baseline-scipy).

### Día 2 — Docker funcional (E1, E11) ⭐
- [x] `docker/backend.Dockerfile` multi-stage (builder + dev + prod).
- [x] `docker/frontend.Dockerfile` (vite dev / nginx prod).
- [x] `docker/postgres-init.sql` con `CREATE EXTENSION timescaledb`.
- [x] `docker compose up` levanta los 3 servicios sin errores.
- [x] Healthchecks reales (no `sleep 5`).
- [x] `.github/workflows/lint.yml` con ruff + eslint.
- [x] `.github/workflows/test.yml` con pytest + vitest.

### Día 3 — Migraciones (E4)
- [x] Setup alembic en `backend/src/pitwall/db/migrations/`.
- [x] Primera migración: schema base (acordado con A en `docs/interfaces/db_schema_v1.sql`).
- [x] `make migrate` corre alembic.
- [x] Servicio `migrate` en docker-compose como one-shot.
- [x] Recuperación Stream D: providers FastAPI usan repositorios SQL cuando
      `DATABASE_URL` está configurado, preservando fallback in-memory para tests.

### Día 4 — Backend Dockerfile multi-stage
- [x] Builder image con `uv` y deps.
- [x] Dev image con bind mount + reload.
- [x] Prod image solo con código + deps necesarias.
- [x] CI: build de imágenes en `.github/workflows/build.yml`.
- [x] Recuperación Stream D: `make demo` arranca backend + frontend; `demo-api`
      mantiene el flujo solo Swagger.

### Día 5 — Logs y health (E12)
- [x] `core/logging.py` con structlog → JSON.
- [x] Endpoints `/health` y `/ready`; `/ready` valida conectividad DB.
- [x] Manejo global de excepciones FastAPI.
- [x] WebSocket heartbeat ping/pong cada 15 s.
- [x] **Hito S1 contribución**: `make demo` arranca todo el stack local.

### Día 6 — Pre-commit + badges + README polish
- [ ] `.pre-commit-config.yaml` con ruff, prettier, eslint.
- [x] Badges de CI en README.
- [ ] `.env.example` documentado.
- [ ] Issue templates en `.github/ISSUE_TEMPLATE/`.
- [ ] PR template `.github/pull_request_template.md`.

### Día 7 — Frontend prod + nginx
- [x] `docker/frontend.Dockerfile` con stage `prod` que sirve `dist/` por nginx.
- [x] Build prod validado en CI vía `.github/workflows/build.yml`.
- [x] Cache de layers optimizado (deps separadas de código).
- [ ] Agregar/validar un profile compose `prod` si la demo necesita servir nginx localmente.

### Día 8 — Test suite verde + ADRs revisados
- [ ] `backend/tests/conftest.py` con fixtures de DB (testcontainers).
- [x] CI corre tests en cada PR.
- [ ] ADRs 0005-0008 escritos.
- [ ] Validador `openapi-spec-validator` en CI.

### Día 9 — `make demo` end-to-end probado
- [ ] Probar `make demo` en máquina limpia (segundo dev sin cache local).
- [ ] Time-to-demo < 10 min (incluye build de imágenes y descarga de FastF1).
- [ ] Pre-cargar dump de DB con 1 carrera para que demo arranque rápido.
- [ ] Documentar en `infra/runbook.md` los problemas que aparezcan.

### Día 10 — Cierre documental
- [ ] Walkthrough actualizado.
- [ ] Changelog v0.1.0 escrito.
- [ ] Release `v0.1.0` con tag git.
- [ ] Video de demo de 3 min enlazado en README (puede ser quien tenga mejor mic).
- [ ] Issues en GitHub para los TODOs pendientes (V1.5, V2).

## Definition of Done por tarea
- CI verde es bloqueante.
- Si introduce dependencia nueva: ADR mínimo (1 párrafo).
- Si cambia comando: actualizar Makefile + walkthrough.
- Si afecta a otro stream: avisar antes del merge.

## Riesgos del stream
1. **Macos vs Linux Docker**: testear CI en `ubuntu-latest`, validar manualmente en macOS.
2. **Bind mounts lentos**: usar `cached` en macOS, no montar `node_modules` o `.venv`.
3. **Healthchecks falsos positivos**: probar levantando con DB ya levantada y con DB caída.
4. **Tests E2E en CI**: Playwright en CI puede ser flaky. Mantener 1 happy path solo, retries 2.

## Coordinación
- **Con A**: schema DB y migraciones.
- **Con B**: env vars, /health endpoint, integración tests.
- **Con C**: Vite proxy, frontend Dockerfile.

## Cosas explícitamente fuera de V1
- Cloud deploy (Fly.io, Railway).
- Prometheus + Grafana real (solo `/metrics` endpoint).
- HTTPS / TLS.
- Reverse proxy.
- Load testing.
- IaC (Terraform).
