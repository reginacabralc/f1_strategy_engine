# Walkthrough — De clonar el repo a correr PitWall

> Tutorial paso a paso para alguien que llega al proyecto por primera vez. Refleja el estado actual del repo: DB + backend API + WebSocket + replay + dashboard React.

## 1. Pre-requisitos

- Docker Desktop >= 4.x (con Compose v2).
- GNU Make.
- Git.
- Python 3.12 recomendado.
- Internet para descargar datos de FastF1 la primera vez.
- (Opcional) `uv` para desarrollo local.
- (Opcional) `pnpm` para trabajar en `frontend/` fuera de Docker. Si no existe, el Makefile usa `npx -y pnpm@9.15.9`.

Verificación rápida:

```bash
docker compose version
make --version
git --version
```

## 2. Clonar y configurar

```bash
git clone https://github.com/<owner>/f1_strategy_engine.git
cd f1_strategy_engine
cp .env.example .env
```

El `.env` por defecto funciona para desarrollo local. Solo cámbialo si necesitas tunear puertos o credenciales.

## 3. Preparar DB y datos demo

```bash
make demo
```

Esto:

1. Levanta `db` (TimescaleDB) con Docker Compose.
2. Crea `.venv` si no existe e instala el backend en modo editable.
3. Corre migraciones (`alembic upgrade head`).
4. Ingiere las 3 carreras demo de 2024: Bahrain, Monaco y Hungary.
5. Ajusta coeficientes de degradación para las carreras demo.
6. Arranca `backend` y `frontend` en Docker Compose.
7. Espera a que `/health` responda y abre el dashboard React.

PostgreSQL se publica en `localhost:5433` para evitar conflictos con un
Postgres local en `5432`; dentro de Docker sigue siendo `db:5432`.

## 4. Verificar la API

Servicios disponibles:

- Backend: <http://localhost:8000>
- Frontend: <http://localhost:5173>
- API docs (Swagger): <http://localhost:8000/docs>
- Health: <http://localhost:8000/health>

Smoke test:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/sessions
```

## 5. Primer replay por API

Arranca un replay de Monaco 2024:

```bash
curl -X POST http://localhost:8000/api/v1/replay/start \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"monaco_2024_R","speed_factor":30}'
```

Conecta el cliente WebSocket demo para ver mensajes live:

```bash
.venv/bin/python scripts/ws_demo_client.py ws://localhost:8000/ws/v1/live
```

Detener replay:

```bash
curl -X POST http://localhost:8000/api/v1/replay/stop
```

También puedes iniciar y detener el replay desde el footer del dashboard en
<http://localhost:5173> después de seleccionar una sesión.

## 6. Cambiar de predictor (scipy <-> XGBoost)

PitWall integra dos predictores de pace. Para alternar sin redeploy:

```bash
# Opción 1: vía variable de entorno (requiere reiniciar backend)
export PACE_PREDICTOR=xgboost
docker compose restart backend

# Opción 2: vía endpoint
curl -X POST http://localhost:8000/api/v1/config/predictor \
  -H 'Content-Type: application/json' \
  -d '{"predictor": "xgboost"}'
```

`xgboost` responde 409 si no existe `models/xgb_pace_v1.json`. Genera el
artifact con `make train-xgb` después de construir el dataset.

## 7. Cargar otra carrera

```bash
# Load the 2024 Hungarian GP (round 13 of 2024)
make ingest YEAR=2024 ROUND=13

# Replay it through the API
curl -X POST http://localhost:8000/api/v1/replay/start \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"hungary_2024_R","speed_factor":30}'
```

The three demo races for 2024 are: **Bahrain (round 1)**, **Monaco (round 8)**,
**Hungary (round 13)**. To load all three at once:

```bash
make ingest-demo
```

Listas: ver [`docs/quanta/05-replay-engine.md`](quanta/05-replay-engine.md).

## 8. Reentrenar XGBoost

Smoke rápido con los datos ya cargados:

```bash
make build-xgb-dataset SPLIT_STRATEGY=temporal_expanding
make validate-xgb-dataset
make tune-xgb
make train-xgb
make validate-xgb-model
make plot-xgb-diagnostics
```

Para el run completo de Stream A, primero carga el manifiesto 2024/2025:

```bash
make validate-ml-races
make ingest-ml-races
```

La ingesta completa puede tardar horas la primera vez porque descarga datos de
FastF1 y llena `data/cache/`.

## 9. Correr tests

```bash
make test           # backend unit tests + frontend vitest
make test-backend   # pytest backend
make test-frontend  # vitest frontend
make lint           # ruff + mypy + eslint
```

Playwright e2e existe como target de frontend, pero requiere instalar los
browsers de Playwright antes de correrlo localmente o en CI.

## 10. Apagar

```bash
make down
# o
docker compose down -v   # también borra volúmenes (datos persistentes)
```

## 11. Cómo entender una alerta

Cuando ves `UNDERCUT_VIABLE` para `(attacker=NOR, defender=VER, lap=18)`:

| Campo | Significado |
|-------|-------------|
| `attacker` | Piloto que pararía en la próxima vuelta |
| `defender` | Piloto delante que se queda fuera |
| `gap_actual` | Gap defender → attacker en ms (positivo = defender delante) |
| `pit_loss_ms` | Tiempo perdido en pit lane (medido del histórico para este equipo y circuito) |
| `gain_acumulada_5` | Ganancia esperada en 5 vueltas si attacker pone neumáticos nuevos y defender se queda fuera |
| `score` | (gain - pit_loss - gap) / pit_loss, en [0, 1] |
| `confidence` | min(R²_defender, R²_attacker) × data_quality_factor |
| `recommended_action` | "PIT_NOW" si score > 0.4 y confidence > 0.5 |

Si `confidence < 0.5`, la alerta no se emite.
Si hay SC/VSC activo, no se emite.
Si llueve, se emite `UNDERCUT_DISABLED_RAIN` en su lugar.

## 12. Cómo extender

### Agregar un circuito

1. `make ingest YEAR=2024 ROUND=<N>`
2. `make fit-degradation CIRCUIT=<id>` — ajusta cuadrática.
3. La API lo descubre al refrescar `/api/v1/sessions`.

### Agregar un feed (live OpenF1, futuro)

1. Implementa `OpenF1Feed(RaceFeed)` en `backend/src/pitwall/feeds/openf1.py`.
2. Registrar en `backend/src/pitwall/api/routes/replay.py`.
3. La interfaz `RaceFeed` no cambia → motor no se toca.

### Agregar una métrica de backtest

El panel de backtest ya existe en el frontend y consume la API cuando hay
resultados disponibles. El comparativo final scipy vs XGBoost sigue pendiente
de cierre y debe documentarse en `docs/quanta/07-backtest-leakage.md`.

## 13. Troubleshooting

Ver [`infra/runbook.md`](../infra/runbook.md) para diagnóstico de problemas comunes:

- "Cannot connect to db" — espera healthcheck.
- "FastF1 cache permission denied" — chmod del volumen.
- "WebSocket disconnects" — prueba primero `.venv/bin/python scripts/ws_demo_client.py`.
- "XGBoost model not found" — usa `PACE_PREDICTOR=scipy` o genera el artifact con los targets `build-xgb-dataset`, `train-xgb` y `validate-xgb-model`.
- "Backtest sale precision = 0" — revisa que cargaste la lista curada de undercuts.
