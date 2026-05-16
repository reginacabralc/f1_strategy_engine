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
scripts/fit_pit_loss.py
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
  - Hungary 2024 R: `hungary_2024_R`.
  - Migraciones `0003_canonical_hungary_slug.py` y
    `0004_canonical_hungary_coefficient_sources.py` reparan DBs locales
    cargadas antes del override `hungarian` -> `hungary`.
- [x] Reconstruir stints desde lap data en la normalización Day 2/3.
  - Implementado dentro de `backend/src/pitwall/ingest/normalize.py`, no como `ingest/stints.py`.
- [x] Validar conteos de demo con `scripts/validate_demo_ingest.py` / `make validate-demo`.
  - Última validación local: Bahrain 1129 laps/63 stints, Monaco 1237 laps/43 stints, Hungary 1355 laps/60 stints.
  - Day 3 cargó 3 carreras demo, no la temporada completa (~30k laps).
- [x] Integración SQL con Stream B.
  - `backend/src/pitwall/repositories/sql.py` implementa
    `SqlSessionRepository` y `SqlSessionEventLoader`.
  - `backend/src/pitwall/api/dependencies.py` usa repos SQL cuando
    `DATABASE_URL` está configurado y conserva fallback in-memory sin DB.
  - Smoke local con DB: `GET /api/v1/sessions` lista las 3 demos y
    `POST /api/v1/replay/start` acepta `monaco_2024_R` con eventos desde DB.
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

### Día 5 — Baseline scipy estable + reporte (E3)
- [x] Coeficientes persistidos en DB y reporte `notebooks/02_fit_degradation.md`
  con métricas reales.
  - Última corrida limpia: 8 coeficientes `quadratic_v1`, 3,503 vueltas
    elegibles, mejor ajuste Monaco MEDIUM R²=0.362/RMSE=1701 ms.
  - El objetivo R² ≥ 0.6 no se alcanzó; queda documentado como limitación
    del baseline, no se maquilló.
- [x] Comando de reporte reproducible.
  - `make report-degradation` reutiliza `scripts/validate_degradation.py`
    para imprimir tabla de coeficientes y smoke de `ScipyPredictor`.
- [x] Validación de compatibilidad con Stream B.
  - Tests unitarios cubren carga desde filas estilo DB, contrato
    `PacePredictor`, `UnsupportedContextError`, clamp de confianza y llamada
    de `engine.undercut.evaluate_undercut()` usando `ScipyPredictor`.
- [ ] Calcular `driver_skill_offsets` por (driver × circuito × compuesto).
  - Diferido: requiere acordar estrategia de normalización/split antes de
    convertirlo en input de entrenamiento.
- [ ] Test unitario con datos reales/fixtures: ScipyPredictor reproduce vueltas conocidas con MAE < 0.5s.
  - Diferido: el baseline actual es funcional, pero la MAE real debe medirse
    con fixture/snapshot curado para no mezclar entrenamiento y evaluación.

### Día 6 — Pit loss (E9 setup)
- [x] `scripts/fit_pit_loss.py` con mediana por (circuito, equipo).
  - Usa `pit_stops.pit_loss_ms` si existe; si no, estima de forma conservadora
    con vueltas pit-in/pit-out y mediana de vueltas limpias cercanas.
  - Última corrida demo: 87 samples realistas, 28 filas persistidas.
- [x] Persistir en `pit_loss_estimates`.
  - Se agregó fallback de circuito con `team_code IS NULL` vía migración
    `0005_pit_loss_circuit_fallback.py`.
  - El loader `load_pit_loss_table()` devuelve la forma de Stream B:
    `{circuit_id: {team_code: pit_loss_ms, None: circuit_median_ms}}`.
  - `api/main.py` carga la tabla al iniciar y la inyecta en `EngineLoop`.
- [x] Notebook/markdown `notebooks/03_pit_loss_estimation.md`.
- [ ] Curaduría manual de ~15 undercuts conocidos en `data/known_undercuts.csv`.
  - Fuera del scope solicitado para Day 6 actual; queda para E9/backtest.
- [ ] `scripts/load_known_undercuts.py` que carga el CSV a DB.

### Día 7 — Dataset XGBoost (E10 prep)
- [x] `backend/src/pitwall/ml/dataset.py` con split LORO.
  - Dataset lap-level exportado a `data/ml/xgb_pace_dataset.parquet`.
  - Metadata exportada a `data/ml/xgb_pace_dataset.meta.json`.
  - Split leave-one-race-out por `session_id`.
- [x] Features documentadas en `notebooks/05_xgb_dataset.md`.
  - Se mantuvo en `dataset.py` para no separar prematuramente `features.py`.
  - Target: `lap_time_delta_ms = lap_time_ms - reference_lap_time_ms`.
  - Incluye proxies de tráfico y offsets de piloto fold-safe.
- [x] Cuidado leakage aplicado.
  - Reference pace y driver offsets se calculan solo con sesiones de training
    para cada fold.
  - Pit loss queda fuera del dataset de pace; se reserva para Day 9.

### Día 8 — Entrenamiento XGBoost (E10) ⭐
- [x] `backend/src/pitwall/ml/train.py`.
  - Usa `xgboost.Booster` nativo, no `XGBRegressor`, para mantener
    compatibilidad con `XGBoostPredictor.from_file()`.
  - Entrena modelos fold leave-one-race-out para evaluación y un modelo final
    entrenado con todas las filas usables.
- [x] Hiperparámetros conservadores iniciales.
  - `objective=reg:squarederror`, `max_depth=4`, `eta=0.08`,
    `subsample=0.9`, `colsample_bytree=0.9`, `num_boost_round=250`.
  - No hay tuning agresivo todavía.
- [x] Persistir modelo a `models/xgb_pace_v1.json`.
  - Metadata sidecar: `models/xgb_pace_v1.meta.json`.
  - Ambos artifacts quedan fuera de git.
- [x] Validación reproducible.
  - `scripts/train_xgb.py` / `make train-xgb`.
  - `scripts/validate_xgb_model.py` / `make validate-xgb-model`.
  - La validación carga el Booster, carga `XGBoostPredictor.from_file()`,
    predice valores finitos sobre una muestra y rechaza features de pit loss.
- [x] Reporte `notebooks/06_xgb_training.md`.
  - Última métrica real con 3 demos: XGB MAE 7,396.0 ms, RMSE 9,209.6 ms,
    R² -0.080 vs zero-delta MAE 7,432.5 ms.
  - Day 8.1 agrega diagnóstico train-vs-holdout, distribución del target,
    baseline de media del training fold, importancias por gain y campo
    `diagnosis` en metadata. Resultado: pipeline de entrenamiento funcional,
    pero señal débil por generalización a circuito no visto con solo 3
    carreras. No hay evidencia de bug de training/serialization; hace falta
    más cobertura de datos antes de tunear. Comparación scipy queda para Day 9.
- [ ] Insertar metadata en `model_registry`.
  - Diferido: Day 8 usa sidecar JSON porque el runtime actual carga desde
    filesystem; registrar el modelo en DB puede agregarse en Day 9/10 sin
    cambiar el artifact.

### Día 8.5 — Augmented temporal XGBoost
- [x] Manifest-based race coverage.
  - `data/reference/ml_race_manifest.yaml` enables full 2024 and 2025 race
    sessions.
  - 2026 candidates are disabled by default and must be enabled only after
    FastF1 availability is confirmed and `race_date <= as_of_date`.
  - `scripts/validate_race_manifest.py` / `make validate-ml-races`.
  - `scripts/ingest_race_manifest.py` / `make ingest-ml-races`.
  - Ingestion reports write to `data/ml/ingestion_report.json`.
- [x] Temporal dataset strategies.
  - `loro` remains available as stress-test mode.
  - `temporal_expanding` is now the default build strategy.
  - `temporal_year` supports explicit train/validation/test year boundaries.
  - Dataset rows include `season`, `round_number`, `event_order`,
    `split_strategy`, `fold_id`, and `split`.
  - Reference pace and driver offsets are still computed from fold training
    sessions only.
- [x] Training, tuning, and plots.
  - `train.py` evaluates generic folds, then trains the final runtime model.
  - `scripts/tune_xgb.py` runs a curated 12-candidate XGBoost search.
  - `scripts/plot_xgb_diagnostics.py` writes matplotlib plots under
    `reports/figures/`.
  - XGBoost remains the only implemented model family; CatBoost/LightGBM are
    deferred in code/docs.
- [x] Documentation.
  - Added ADR 0011 and `docs/ml_temporal_modeling_plan.md`.
  - Added `notebooks/07_augmented_temporal_model.md`.
  - Updated architecture, quanta 06, training report, and progress.

### Día 8.2 — Temporal model diagnostics before backtest
- [x] Target/reference shift diagnostics.
  - `backend/src/pitwall/ml/diagnostics.py`.
  - `scripts/diagnose_xgb_dataset_shift.py` / `make diagnose-xgb-shift`.
  - Reports fold/session target distributions, reference-source counts,
    driver-offset source counts, failed ingestions, and zero-usable sessions.
- [x] Leakage-safe baseline ladder.
  - `backend/src/pitwall/ml/baselines.py`.
  - `scripts/evaluate_xgb_baselines.py` / `make evaluate-xgb-baselines`.
  - Baselines: zero, train mean, circuit+compound median,
    circuit+compound+tyre-age curve, and driver/team-adjusted median.
- [x] Feature ablations and target variants.
  - `backend/src/pitwall/ml/ablation.py`.
  - `scripts/run_xgb_ablation.py` / `make run-xgb-ablations`.
  - `TARGET_STRATEGY` supports current delta, session-normalized,
    stint-relative, absolute lap time, and season+circuit+compound delta.
- [x] Data-quality cleanup.
  - Dataset metadata records requested sessions that produce zero usable rows.
  - Wet/mixed or missing-compound sessions are explicit instead of silently
    absent.
  - `scripts/fit_degradation.py --manifest` supports full manifest fitting.
- [x] Day 8.2 quality gate.
  - Selected `TARGET_STRATEGY=session_normalized_delta` and
    `FEATURE_SET=no_reference_lap_time_ms`.
  - Aggregate temporal CV: XGBoost MAE 1,561.9 ms vs zero-delta 1,762.7 ms
    and train-mean 1,612.9 ms.
  - Gate passed by 200.8 ms vs zero-delta (11.4%) and all five folds improved
    over zero-delta.

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
