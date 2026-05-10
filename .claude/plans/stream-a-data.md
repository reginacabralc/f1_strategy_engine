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

- [ ] `scripts/ingest_season.py --year 2024 --rounds 1,8,13` funcional.
- [ ] Activar `fastf1.Cache.enable_cache(./data/cache)`.
- [ ] Pin `fastf1==X.Y.Z` en pyproject.
- [ ] Notebook `notebooks/01_explore_fastf1.ipynb` mostrando estructura.

### Día 3 — DB & Stints (E2/E4)
- [ ] Cargar 3 carreras de demo a DB local.
- [ ] Reconstruir stints en `ingest/stints.py`.
- [ ] Validar conteos: ~30k vueltas/temporada, ~50 stints/carrera.
- [ ] Filtrar vueltas inválidas en `normalize.py`.

### Día 4 — Degradación scipy (E3)
- [ ] `scripts/fit_degradation.py` con `scipy.optimize.curve_fit`.
- [ ] Persistir coefs en `degradation_coefficients`.
- [ ] Reportar R² por (circuito × compuesto) con warning si < 0.6.
- [ ] Notebook `02_fit_degradation.ipynb`.
- [ ] Definir interfaz `PacePredictor` (con B):
  ```python
  class PacePredictor(Protocol):
      def predict(self, driver_code, compound, tyre_age, k=1) -> int: ...
      def confidence(self, driver_code, compound) -> float: ...
  ```
- [ ] Implementar `ScipyPredictor`.

### Día 5 — Skill offsets + integración (E3)
- [ ] Calcular `driver_skill_offsets` por (driver × circuito × compuesto).
- [ ] Test unitario: ScipyPredictor reproduce vueltas conocidas con MAE < 0.5s.
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
