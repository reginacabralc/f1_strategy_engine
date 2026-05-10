# Walkthrough — De clonar el repo a ver una alerta de undercut

> Tutorial paso a paso para alguien que llega al proyecto por primera vez. Asume Docker Desktop instalado y ~10 GB libres.

## 1. Pre-requisitos

- Docker Desktop ≥ 4.x (con Compose v2).
- GNU Make.
- Git.
- (Opcional) `uv` y `pnpm` para correr backend/frontend fuera de Docker.

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

El `.env` por defecto funciona. Solo cámbialo si te toca tunear puertos o credenciales.

## 3. Levantar el sistema completo

```bash
make demo
```

Esto:

1. Construye las imágenes Docker (primera vez ~5 min).
2. Levanta `db` (TimescaleDB), `backend`, `frontend`.
3. Corre migraciones (`alembic upgrade head`).
4. Ejecuta `scripts/seed_demo.py` que carga la carrera de demo (Mónaco 2024).
5. Abre el navegador en `http://localhost:5173`.

Servicios disponibles:

- Frontend: <http://localhost:5173>
- Backend: <http://localhost:8000>
- API docs (Swagger): <http://localhost:8000/docs>
- Health: <http://localhost:8000/health>

## 4. Primer replay end-to-end

En la UI:

1. Selecciona la sesión "Mónaco 2024 R" en el dropdown.
2. Pulsa **Play** con velocidad 30×.
3. Observa la tabla actualizarse vuelta a vuelta.
4. Cuando aparezca una alerta `UNDERCUT_VIABLE`, verás un flash en el feed lateral con piloto atacante, defensor y ganancia estimada.

Por terminal puedes ver los mismos eventos:

```bash
docker compose logs -f backend | grep alert
```

## 5. Cambiar de predictor (scipy ↔ XGBoost)

PitWall integra dos predictores de pace. Para alternar sin redeploy:

```bash
# Opción 1: vía variable de entorno (requiere reiniciar backend)
export PACE_PREDICTOR=xgb
docker compose restart backend

# Opción 2: vía endpoint (no requiere reinicio en V1.5+)
curl -X POST http://localhost:8000/api/v1/config/predictor \
  -H 'Content-Type: application/json' \
  -d '{"predictor": "xgb"}'
```

Compara las alertas que produce cada predictor. La quanta [`06-curva-fit-vs-xgboost.md`](quanta/06-curva-fit-vs-xgboost.md) explica las diferencias esperadas.

## 6. Cargar otra carrera

```bash
# Load the 2024 Hungarian GP (round 13 of 2024)
make ingest YEAR=2024 ROUND=13

# Replay it
make replay SESSION=hungary_2024_R SPEED=30
```

The three demo races for 2024 are: **Bahrain (round 1)**, **Monaco (round 8)**,
**Hungary (round 13)**. To load all three at once:

```bash
make ingest-demo
```

Listas: ver [`docs/quanta/05-replay-engine.md`](quanta/05-replay-engine.md).

## 7. Reentrenar XGBoost

Después de cargar más carreras, conviene reentrenar:

```bash
make train-xgb
```

Esto:

1. Construye dataset desde DB con split leave-one-race-out.
2. Entrena `XGBRegressor` con hiperparámetros fijos.
3. Serializa modelo a `models/xgb_pace_v1.json`.
4. Registra metadatos en tabla `model_registry`.
5. Imprime tabla con métricas (MAE@k, segmentado por compuesto y bucket).

Para que el backend cargue el modelo nuevo, reinicia:

```bash
docker compose restart backend
```

## 8. Correr tests

```bash
make test          # todo
make test-backend  # solo pytest
make test-frontend # solo vitest
make test-e2e      # Playwright
```

## 9. Backtest

```bash
# Notebook
docker compose exec backend jupyter nbconvert --execute \
  notebooks/04_backtest_v1.ipynb --to html

# CLI
docker compose exec backend python -m pitwall.scripts.backtest \
  --sessions monaco_2024_R hungary_2024_R --predictor xgb
```

Reporta:

- Precision / recall de alertas vs lista curada de undercuts conocidos.
- MAE de proyección de pace por k=1..5.
- Comparación scipy vs xgb.

## 10. Apagar todo

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
3. (Opcional) `make train-xgb` — reentrenar con datos nuevos.
4. La UI lo descubre automáticamente al refrescar `/api/v1/sessions`.

### Agregar un feed (live OpenF1, futuro)

1. Implementa `OpenF1Feed(RaceFeed)` en `backend/src/pitwall/feeds/openf1.py`.
2. Registrar en `backend/src/pitwall/api/routes/replay.py`.
3. La interfaz `RaceFeed` no cambia → motor no se toca.

### Agregar una métrica de backtest

1. Edita `backend/src/pitwall/engine/backtest.py`.
2. Agregar al notebook `notebooks/04_backtest_v1.ipynb`.
3. Documentar en `docs/quanta/07-backtest-leakage.md`.

## 13. Troubleshooting

Ver [`infra/runbook.md`](../infra/runbook.md) para diagnóstico de problemas comunes:

- "Cannot connect to db" — espera healthcheck.
- "FastF1 cache permission denied" — chmod del volumen.
- "WebSocket disconnects" — frontend reconecta automáticamente; si persiste, ver logs.
- "XGBoost model not found" — corre `make train-xgb` antes de arrancar.
- "Backtest sale precision = 0" — revisa que cargaste la lista curada de undercuts.
