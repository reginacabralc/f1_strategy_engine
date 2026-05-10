# Stream A — Datos & ML

> Owner: _por asignar_. Backup: Stream D.
> Cubre Etapas 2, 3, 4, 9 (parcial), **10** del [plan maestro](00-master-plan.md).

## Mantra

"Sin datos limpios, ML es teatro. Sin baseline, ML no es defendible."

## Responsabilidades

1. Ingesta histórica de FastF1 a TimescaleDB.
2. Reconstrucción de stints, normalización de vueltas.
3. Schema DB (acordado con Stream D).
4. Curva de degradación scipy por (circuito × compuesto).
5. Pit loss histórico por (circuito, equipo).
6. **XGBoost: dataset, features, entrenamiento, serialización.**
7. Backtest: lista curada de undercuts conocidos + métricas.
8. Skill offsets por piloto.

## Archivos owned

```
backend/src/pitwall/ingest/
backend/src/pitwall/degradation/
backend/src/pitwall/ml/
backend/src/pitwall/db/migrations/   # con review de D
notebooks/
scripts/ingest_*.py
scripts/fit_*.py
scripts/compute_pit_loss.py
scripts/train_xgb.py
scripts/load_known_undercuts.py
docs/quanta/02-degradacion-neumatico.md
docs/quanta/03-pit-loss.md
docs/quanta/06-curva-fit-vs-xgboost.md
docs/quanta/07-backtest-leakage.md
docs/adr/0009-xgboost-vs-scipy-resultados.md
```

## Tareas

### Day 1 — Kickoff ✅

- [x] Propose final `docs/interfaces/db_schema_v1.sql` (English, hypertable PK fixed, CHECK constraints).
- [x] Define the `PacePredictor` Protocol in `backend/src/pitwall/engine/projection.py` with `PaceContext` and `PacePrediction` (pending sign-off from Stream B).
- [x] Lock the contract with unit tests in `backend/tests/unit/engine/test_projection.py`.
- [x] **Verify FastF1 round numbers for the 2024 demo races.** Verified
  against the 2024 calendar:
  - **Bahrain GP = round 1** (2 March 2024)
  - **Monaco GP = round 8** (26 May 2024)
  - **Hungarian GP = round 13** (21 July 2024)

  Earlier drafts of the master plan and walkthrough had `ROUND=11` for
  Hungary (round 11 in 2024 is Austria) and `Mónaco=6`. README and
  walkthrough have been corrected; the master plan's "Primeras 15 tareas"
  section still lists the wrong placeholder (acceptable — the master plan
  is a snapshot, the per-stream plans take precedence).

### Día 2 — Ingesta (E2)

- [x] `scripts/ingest_season.py` funcional para 1 ronda.
  - Scope real de Day 2: una carrera/sesión FastF1, no temporada completa.
  - Default demo: Monaco 2024, round 8, session R (`monaco_2024_R`).
  - Soporta dry-run/file output bajo `data/processed/`.
- [x] Activar `fastf1.Cache.enable_cache(./data/cache)`.
  - Cache configurable con `FASTF1_CACHE_DIR`.
  - `data/cache` y `data/processed` quedan fuera de git.
- [x] Pin `fastf1==3.8.3` en `backend/pyproject.toml`.
- [x] Normalización defensiva de metadata, drivers, laps, stints, pit stops y weather.
  - Timedeltas a milisegundos enteros.
  - `NaN`/`NaT` a `None` antes de write boundaries.
  - Pit-in, pit-out y vueltas borradas preservadas como flags.
- [x] Tests unitarios de normalización en `backend/tests/unit/ingest/test_normalize.py`.
- [x] Notebook/markdown `notebooks/01_explore_fastf1.md` mostrando estructura y workflow.

### Día 3 — DB & Stints (E2/E4)
- [x] Soporte local TimescaleDB/Postgres reproducible.
  - `docker-compose.yaml` con TimescaleDB/Postgres 15, usuario/db `pitwall`, healthcheck y volumen `pgdata`.
  - `.env.example` con `DATABASE_URL`, `FASTF1_CACHE_DIR` y `PITWALL_PROCESSED_DIR`.
- [x] Alembic inicial reproducible.
  - `backend/src/pitwall/db/migrations/versions/0001_initial_schema.py`.
  - Crea extensiones `timescaledb`/`pgcrypto`, schema v1, hypertable `laps` por `ts`, y materialized view `clean_air_lap_times`.
- [x] DB connection utilities en `backend/src/pitwall/db/engine.py`.
- [x] Writer DB idempotente para ingesta.
  - Mantiene dry-run/file output.
  - Inserta en orden de FK y usa `ON CONFLICT`.
- [x] Cargar 3 carreras demo a DB local.
  - Bahrain 2024 R: `bahrain_2024_R`.
  - Monaco 2024 R: `monaco_2024_R`.
  - Hungary 2024 R: `hungarian_2024_R`.
- [x] Reconstruir stints desde lap data en la normalización Day 2/3.
  - Implementado dentro de `backend/src/pitwall/ingest/normalize.py`, no como `ingest/stints.py`.
- [x] Validar conteos de demo con `scripts/validate_demo_ingest.py` / `make validate-demo`.
  - Última validación local: Bahrain 1129 laps/63 stints, Monaco 1237 laps/43 stints, Hungary 1355 laps/60 stints.
  - Day 3 cargó 3 carreras demo, no la temporada completa (~30k laps).
- [x] Make targets reproducibles: `db-up`, `db-down`, `migrate`, `ingest-monaco`, `ingest-demo`, `validate-demo`, `test`, `lint`.

### Día 4 — Degradación scipy (E3)
- [x] Paquete `backend/src/pitwall/degradation/`.
  - `dataset.py`: extracción/diagnóstico de clean-air laps desde DB.
  - `fit.py`: ajuste cuadrático `quadratic_v1` con `scipy.optimize.curve_fit`.
  - `models.py`: resultados tipados de ajuste.
  - `writer.py`: persistencia idempotente de coeficientes.
- [x] `scripts/fit_degradation.py`.
  - Soporta `--session monaco_2024_R`.
  - Soporta `--all-demo`.
  - `make fit-degradation` corre las 3 carreras demo.
- [x] Refresh path de `clean_air_lap_times`.
  - Migración `0002_clean_air_lap_times.py` enriquece la materialized view con `fitting_eligible` y `exclusion_reason`.
  - La vista conserva filas excluidas para diagnóstico.
- [x] Persistir coefs en `degradation_coefficients`.
  - Migración 0002 agrega `model_type`, `rmse_ms`, `n_laps`, `min_tyre_age`, `max_tyre_age` y `source_sessions`.
  - Upsert idempotente por `(circuit_id, compound)`.
- [x] Reportar R² por (circuito × compuesto) con warning si < 0.6.
  - Última validación local: 8 coeficientes persistidos.
  - Todos los fits actuales quedan `fitted_warn`; mejor observado Monaco MEDIUM R²=0.362, RMSE=1701 ms.
- [x] `scripts/validate_degradation.py` / `make validate-degradation`.
- [x] Tests unitarios:
  - `backend/tests/unit/degradation/test_dataset.py`.
  - `backend/tests/unit/degradation/test_fit.py`.
  - `backend/tests/unit/degradation/test_degradation_writer.py`.
- [x] Notebook/markdown `notebooks/02_fit_degradation.md`.
- [x] Confirmar interfaz `PacePredictor` actual.
  - La interfaz real ya existe en `backend/src/pitwall/engine/projection.py`.
  - Firma vigente: `predict(ctx: PaceContext) -> PacePrediction` e
    `is_available(circuit_id, compound) -> bool`.
  - No se cambió la firma para no romper el contrato con Stream B; el sign-off
    formal con B sigue trackeado en Día 1.
- [x] Implementar `ScipyPredictor`.
  - `backend/src/pitwall/degradation/predictor.py`.
  - Carga coeficientes `quadratic_v1` desde `degradation_coefficients`.
  - Satisface `PacePredictor` en runtime.
  - Usa R² como `PacePrediction.confidence`.
  - `scripts/validate_degradation.py` ahora incluye un smoke de predicción
    Monaco MEDIUM age 10. Última validación Docker: 81,366 ms con confidence
    0.362.

### Día 5 — Skill offsets + integración (E3)
- [ ] Calcular `driver_skill_offsets` por (driver × circuito × compuesto).
- [ ] Test unitario con datos reales/fixtures: ScipyPredictor reproduce vueltas conocidas con MAE < 0.5s.
  - Ya existen tests sintéticos de contrato/cuadrática; falta fixture real o
    snapshot pequeño para medir MAE.
- [ ] Hito S1: motor B corre con `ScipyPredictor` real.

### Día 6 — Pit loss (E9 setup)
- [ ] `scripts/compute_pit_loss.py` con mediana por (circuito, equipo).
- [ ] Persistir en `pit_loss_estimates`.
- [ ] Notebook `03_pit_loss.ipynb`.
- [ ] Curaduría manual de ~15 undercuts conocidos en `data/known_undercuts.csv`.
- [ ] `scripts/load_known_undercuts.py` que carga el CSV a DB.

### Día 7 — Dataset XGBoost (E10 prep)
- [ ] `backend/src/pitwall/ml/dataset.py` con split LORO.
- [ ] `backend/src/pitwall/ml/features.py` con features documentadas en quanta 06.
- [ ] Cuidado leakage: leer quanta 07 antes de implementar.

### Día 8 — Entrenamiento XGBoost (E10) ⭐
- [ ] `backend/src/pitwall/ml/train_xgb.py`.
- [ ] Hiperparámetros fijos: `max_depth=5, n_estimators=400, lr=0.05, early_stopping=20`.
- [ ] Persistir modelo a `models/xgb_pace_v1.json`.
- [ ] Insertar metadata en `model_registry`.
- [ ] `XGBoostPredictor` que carga modelo al boot.
- [ ] Notebook `05_xgboost_train_eval.ipynb`.

### Día 9 — Backtest comparativo (E9 + E10) ⭐
- [ ] `backend/src/pitwall/engine/backtest.py` con métricas precision/recall/MAE@k.
- [ ] Notebook `04_backtest_v1.ipynb` corriendo replay determinista para 5 sesiones hold-out.
- [ ] Tabla comparativa: `B0 mediana | B1 scipy | B2 xgboost`.
- [ ] Métricas segmentadas por compuesto y bucket de stint.

### Día 10 — Documentación final
- [ ] Quanta `06-curva-fit-vs-xgboost.md` con números reales.
- [ ] ADR `0009-xgboost-vs-scipy-resultados.md` cerrado con la decisión.
- [ ] Default `PACE_PREDICTOR=` actualizado en `.env.example`.
- [ ] README sección ML actualizada.

## Definition of Done por tarea
- Código + test unitario en mismo PR.
- Si cambia schema: migración alembic + actualizar `docs/interfaces/db_schema_v1.sql`.
- Si cambia features: actualizar quanta 06.
- Si modelo cambia: actualizar `model_registry`.

## Riesgos del stream
1. **R²-Mónaco bajo**: planeado, fallback a lineal en circuitos con < 200 vueltas válidas.
2. **2022 datos rotos en Compound**: excluido del entrenamiento.
3. **XGBoost no mejora a scipy**: aceptable. Documentar honestamente en ADR 0009.
4. **Curaduría de undercuts atrasa**: 5-10 conocidos alcanza para V1, no necesitamos 20.

## Coordinación
- **Con B**: interfaz `PacePredictor`, formato de eventos del feed.
- **Con D**: schema DB, migraciones alembic.
- **Con C**: API `/api/v1/degradation` y `/api/v1/backtest/{id}` — formato de response acordado en OpenAPI.
