# Runbook — diagnóstico de fallos comunes

> Si te topas con un problema no listado aquí, **agrégalo** después de resolverlo.

## Smoke test

Después de `make demo`:

```bash
curl http://localhost:8000/health
# {"status":"ok","version":"0.1.0"}

curl http://localhost:8000/api/v1/sessions
# [{"session_id":"monaco_2024_R", ...}]
```

También verifica el dashboard en <http://localhost:5173>. Si `/health`,
`/ready`, `/api/v1/sessions` y el frontend cargan, el demo base está sano.

---

## Problema: `make demo` falla en el paso de migrate

**Síntoma:** `migrate` exit con error, backend no levanta.

**Diagnóstico:**

```bash
docker compose logs migrate
```

**Causas comunes:**

1. **DB no estaba lista**: el healthcheck no esperó suficiente.
   - Solución: `docker compose down && make demo` reintenta.
2. **Schema cambió y migración no idempotente**.
   - Solución: ver alembic history, `alembic downgrade -1` y `alembic upgrade head`.
3. **TimescaleDB extension no se creó**.
   - Solución: revisa `docker/postgres-init.sql` y que el volumen esté limpio (`docker compose down -v`).

---

## Problema: backend responde 503 en `/ready`

**Diagnóstico:**

```bash
curl http://localhost:8000/ready -v
docker compose logs backend | tail -50
```

**Causas:**

1. **DB no conectable**: `psycopg2.OperationalError`.
   - Verifica `DATABASE_URL`.
   - `docker compose ps db` debe mostrar `(healthy)`.
2. **Modelo XGBoost no cargado** y `PACE_PREDICTOR=xgb`.
   - Cambiar a `PACE_PREDICTOR=scipy` temporalmente o regenerar el artifact con los targets `build-xgb-dataset`, `train-xgb` y `validate-xgb-model`.
3. **Migraciones no aplicadas**.
   - `docker compose run migrate alembic current`.

---

## Problema: WebSocket cierra inmediatamente

**Síntoma:** En el navegador, "WebSocket connection to ws://... closed".

**Diagnóstico:**

```bash
.venv/bin/python scripts/ws_demo_client.py ws://localhost:8000/ws/v1/live
```

**Causas:**

1. **CORS / origin policy**: si el frontend está en un origin distinto.
   - Verifica `cors_allowed_origins` en `backend/src/pitwall/api/main.py`.
2. **Backend no terminó de arrancar**.
   - Espera healthcheck.
3. **Proxy / reverse proxy** strippeando upgrade headers.
   - V1 no usa proxy.

---

## Problema: la UI muestra "No active replay"

El frontend está conectado por WebSocket, pero no emite datos de carrera hasta
que arranca un replay. Usa el selector de sesión y el botón de play del footer,
o arráncalo por API:

```bash
curl -X POST http://localhost:8000/api/v1/replay/start \
  -H 'Content-Type: application/json' \
  -d '{"session_id": "monaco_2024_R", "speed_factor": 30}'
```

---

<!-- Future frontend note kept here so it can be re-enabled when Stream C lands. -->

**Síntoma:** Tabla vacía, sin alertas.

**Causa:** No has iniciado un replay.

**Solución:**

```bash
curl -X POST http://localhost:8000/api/v1/replay/start \
  -H 'Content-Type: application/json' \
  -d '{"session_id": "monaco_2024_R", "speed_factor": 30}'
```

El botón "Play" del dashboard llama al mismo endpoint.

---

## Problema: `make ingest` falla con HTTP 403 / FastF1 timeout

**Síntoma:** FastF1 no puede descargar datos.

**Causas:**

1. **F1 site rate limiting**.
   - Esperar unos minutos. FastF1 cachea localmente, los próximos intentos van rápido.
2. **Cache sin permisos**.
   - `chmod -R u+rwX data/cache` (en el host).
3. **FastF1 versión incompatible**.
   - Actualizar pin en `backend/pyproject.toml`.

---

## Problema: precision = 0 en backtest

**Causa probable:** No has cargado la lista curada de undercuts conocidos.

**Solución:**

```bash
# Pendiente: este script/flujo todavía no existe.
```

Nota: este flujo de backtest todavía está pendiente de implementación.

---

## Problema: el motor no emite alertas durante un replay

**Diagnóstico:**

```bash
docker compose logs -f backend | grep -i "alert\|undercut\|engine"
```

**Causas comunes:**

1. **Motor no arrancó**: revisa los logs del startup.
2. **`confidence` siempre < 0.5**: probablemente faltan coeficientes de degradación. `make fit-degradation`.
3. **Track status SC/VSC todo el tiempo**: alertas se suspenden por diseño. Revisa eventos `track_status_change`.
4. **Datos de la sesión ingerida con `is_valid=false` masivo**: revisa la ingesta.
5. **`gap_to_ahead_ms` es NULL en los laps demo**: FastF1 no proporciona este campo
   nativo. Sin el gap reconstruido, el motor descarta los pares por datos insuficientes
   y nunca emite `UNDERCUT_VIABLE`.

   **Solución:** corre `make reconstruct-race-gaps` con la DB activa y reinicia el
   replay. Desde Phase 5B, `make demo` y `make demo-api` incluyen este paso
   automáticamente; solo es necesario correrlo a mano si se ingirió una sesión
   nueva directamente vía `make ingest`.

   ```bash
   make reconstruct-race-gaps
   # Verifica cobertura
   docker compose exec -T db psql -U pitwall -d pitwall -c \
     "SELECT session_id, COUNT(*) total, COUNT(gap_to_ahead_ms) with_gap \
      FROM laps GROUP BY session_id;"
   ```

---

## Problema: `docker compose up` muy lento en macOS

**Causa:** Bind mounts en macOS son notoriamente lentos.

**Mitigaciones:**

1. Usar mount `cached` o `delegated`:
   ```yaml
   volumes:
     - ./backend/src:/app/src:cached
   ```
2. Solo montar lo necesario; **no** montar `node_modules` o `.venv`.
3. Si es muy doloroso, usar Docker Desktop con VirtioFS habilitado.

---

## Problema: `PACE_PREDICTOR=xgb` no carga en runtime

`make train-xgb` existe, pero el demo reproducible no depende de XGBoost. Para
la demo usa `PACE_PREDICTOR=scipy`. Para validar XGBoost localmente:

```bash
make build-xgb-dataset SPLIT_STRATEGY=temporal_expanding
make validate-xgb-dataset
make train-xgb
make validate-xgb-model
```

---

## Cómo apagar todo

```bash
make down       # mantiene volúmenes (datos)
make down-v     # borra todo (incluye DB)
```

Para empezar limpio:

```bash
make down-v
rm -rf data/cache models/*.json
make demo
```

---

## Logs útiles

```bash
# Todo
docker compose logs -f

# Solo backend, últimas 100 líneas
docker compose logs --tail=100 backend

# Errores en JSON
docker compose logs backend | jq 'select(.level=="ERROR")'

# Filtrar por componente
docker compose logs backend | jq 'select(.component=="engine")'
```

## Playwright e2e

```bash
make test-e2e-install
make test-e2e
```

Problemas comunes:

- `pnpm: command not found`: usa `make test-e2e`, que cae a `npx -y pnpm@9.15.9`
  cuando `pnpm` no está instalado globalmente.
- `Executable doesn't exist ... firefox`: falta el browser de Playwright; corre
  `make test-e2e-install`.
- `Host system is missing dependencies`: en Linux/CI instala con
  `pnpm exec playwright install --with-deps firefox`.
- `listen EPERM` o `connect EPERM` en el sandbox de Codex: limitación local de
  permisos de red del sandbox. Verifica fuera del sandbox o deja que CI ejecute
  el job Playwright.

## Python local incorrecto

`make demo` crea `.venv` con `python3.12` cuando existe. Si una máquina solo
tiene `python3` apuntando a 3.9/3.10, el Makefile falla antes de instalar
dependencias:

```text
Python 3.12+ is required. Install python3.12 or run make with PYTHON_BOOTSTRAP=/path/to/python3.12
```

Soluciones:

- Instalar Python 3.12 y repetir `make demo`.
- O ejecutar `make demo PYTHON_BOOTSTRAP=/ruta/a/python3.12`.

## Validación Day 9 de `make demo`

La validación Stream D Day 9 se corrió desde un clon limpio con volumen DB
fresco:

```bash
cp .env.example .env
/usr/bin/time -p make demo
```

Resultado medido: `real 481.10`, `user 29.32`, `sys 6.11`. Ese tiempo incluyó
migraciones, ingesta FastF1 fría de Bahrain/Monaco/Hungary 2024, fit de
degradación demo y arranque Docker de backend/frontend. No se podó manualmente
la cache de layers Docker del host.

Checks posteriores que deben pasar:

```bash
curl -fsS http://localhost:8000/health
curl -fsS http://localhost:8000/ready
curl -fsS http://localhost:8000/api/v1/sessions
curl -fsS http://localhost:5173
```

WebSocket smoke:

```bash
curl -fsS -X POST http://localhost:8000/api/v1/replay/start \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"monaco_2024_R","speed_factor":1000}'
.venv/bin/python scripts/ws_demo_client.py ws://localhost:8000/ws/v1/live
curl -fsS -X POST http://localhost:8000/api/v1/replay/stop
```

Si `make demo` supera 10 minutos, revisar primero red/FastF1 y el build de la
imagen backend. En rebuilds de la capa Python, XGBoost y `nvidia-nccl-cu12`
dominan el tiempo de descarga. La ruta medida cumple el objetivo sin dump de
DB; mantener un dump pre-cargado solo como fallback si una prueba futura con
cache Docker podada rompe el objetivo.

---

## Cuándo escalar a un humano

- El test suite pasa local pero falla en CI con error críptico → revisar diferencias de versiones de Docker / OS.
- Replay funciona pero los timestamps están en orden incorrecto → revisar timezone (`TZ=UTC` en docker-compose).
- Backtest reporta números que no tienen sentido (ej. recall > 1) → leakage en split.
