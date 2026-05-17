# Quanta 06 — Curve fit (scipy) vs XGBoost

## Concepto

PitWall integra **dos predictores de pace** intercambiables. Esta quanta explica qué hace cada uno, en qué contextos uno gana, y cómo lo evaluamos.

## Por qué importa para el producto

El profesor exige un componente de ML real. Pero "usar ML" no es virtud por sí sola — la pregunta interesante es: **¿XGBoost mejora medible al baseline?** Si sí, ¿en qué casos? Si no, ¿por qué? Esta quanta es la respuesta.

## ScipyPredictor (baseline paramétrico)

### Modelo

```
lap_time(t) = a + b·t + c·t²
```

Por (circuito × compuesto). Parámetros ajustados con `scipy.optimize.curve_fit` sobre vueltas válidas.

### Pros

- Interpretable: 3 números por (circuito × compuesto), entendibles sin ML.
- Rápido: predicción es una multiplicación.
- Estable: poco riesgo de overfitting.
- Funciona con pocos datos.

### Cons

- Lineal-cuadrático no captura el cliff. Si la degradación es exponencial al final, el modelo se queda corto.
- Una sola curva por compuesto/circuito no captura diferencias de piloto, equipo, condiciones.
- `track_temp` no entra como feature.

## XGBoostPredictor (entregable de ML)

### Modelo

Native `xgboost.Booster` con:

- hiperparámetros conservadores o seleccionados por tuning,
- búsqueda estructurada reproducible con `make tune-xgb`,
- selección por MAE temporal de validación, después RMSE y gap train-validación.

### Features

| Feature | Tipo |
|---------|------|
| `tyre_age` | int |
| `compound` | one-hot (SOFT/MEDIUM/HARD/INTER/WET) |
| `circuit_id` | one-hot |
| `track_temp_c` | float |
| `air_temp_c` | float |
| `lap_in_stint_ratio` | float ∈ [0, 1+] |
| `lap_in_stint` / `stint_number` | int |
| `position` | int |
| `gap_to_ahead_ms` / `gap_to_leader_ms` | float |
| `is_in_traffic` / `dirty_air_proxy_ms` | traffic proxies |
| `driver_pace_offset_ms` | float (fold-safe) |
| `team_code` | one-hot |
| `fuel_proxy` | float ∈ [0, 1] |

### Target

```
session_normalized_delta = lap_time_ms - median(prior clean dry laps in same session+compound)
```

El valor se persiste en `lap_time_delta_ms` por compatibilidad con los scripts.
Si no hay referencia live-safe de sesión/compuesto, cae al reference pace del
fold de entrenamiento.

### Split

**Temporal expanding window** es ahora el split principal: ordenamos sesiones por
`(season, round_number)`, entrenamos solo con sesiones pasadas y validamos con
sesiones futuras. LORO se conserva como stress test, no como la métrica principal.

### Pros

- Captura interacciones (compuesto × circuito × temperatura).
- El cliff se modela sin programación explícita gracias a `lap_in_stint_ratio` y árboles no lineales.
- `driver_skill_offset` y `team_id` capturan diferencias por piloto/equipo.

### Cons

- Caja negra: no es trivial explicar por qué predijo X para una vuelta concreta.
- Necesita más datos para ser estable.
- Inferencia ligeramente más lenta (~1-5 ms vs ~µs scipy).
- Si reentrenamos con datos malos, el modelo hereda esos sesgos.

## Comparación

| Eje | scipy | XGBoost |
|-----|-------|---------|
| Interpretabilidad | Alta | Media (con SHAP) |
| Datos requeridos | Bajos (~50 vueltas/celda) | Medios (~500+ vueltas total) |
| Captura cliff | Pobre | Bueno (con `lap_in_stint_ratio`) |
| Velocidad inferencia | µs | ms |
| Generalización | Por (circ, comp) | Cross-circuit y cross-driver |
| Riesgo overfitting | Bajo | Medio |
| Mantenimiento | Refit por nuevos datos | Reentrenar |

## Resultado real (post-E10)

Day 8 mostró que el modelo de 3 carreras estaba bien armado pero no era una
evidencia de calidad suficiente:

- Train MAE/R²: 294.7 ms / 0.943.
- Holdout MAE/R²: 7,396.0 ms / -0.080.
- Mejora vs zero-delta: 36.6 ms.

La causa principal fue cobertura insuficiente: LORO con tres carreras es casi
leave-one-circuit-out. La decisión nueva está en
[ADR 0011](../adr/0011-temporal-expanding-xgboost-validation.md): usar 2024/2025
recientes, validación temporal y tuning pequeño antes de Day 9.

## Day 8.2 — antes de backtesting

La primera corrida temporal ampliada mostró que más datos no basta si el target
sigue mal normalizado. Los folds tempranos tuvieron medias del target de varios
segundos, señal de shift entre `lap_time_ms` y `reference_lap_time_ms`.

Para que XGBoost sea defendible antes de Day 9:

- `make diagnose-xgb-shift` debe explicar target/reference shift por fold y
  sesión.
- `make evaluate-xgb-baselines` define el ladder de baselines que XGBoost debe
  vencer.
- `make run-xgb-ablations` verifica si las features dominantes realmente ayudan
  o solo memorizan offsets de circuito.
- `TARGET_STRATEGY=... make build-xgb-dataset` permite probar targets
  alternativos sin mezclar backtesting.

El gate de calidad queda explícito: XGBoost debe vencer zero-delta y train-mean
en CV temporal agregado, idealmente por al menos 500 ms o 7% de MAE, y no puede
degradar más de 100 ms vs zero-delta en más de un fold.

Resultado Day 8.2 observado: el target `session_normalized_delta` corrigió el
shift principal; `lap_time_delta` mantenía folds con medias de -9.6 s y +12.0 s.
La mejor ablation fue `no_reference_lap_time_ms`, lo que confirma que
`reference_lap_time_ms` era parte del problema de estabilidad. Con 151,363 filas
usables, 47 sesiones y cinco folds temporales, XGBoost obtuvo MAE/RMSE/R² de
1,561.9 ms / 4,614.4 ms / 0.007. Ganó a zero-delta por 200.8 ms (11.4%) y a
train-mean por 51.0 ms. El gate queda aprobado para pasar a Day 9, con la
advertencia de que la ventaja sigue siendo moderada y debe validarse en
backtesting de estrategia.

Resultado Day 8.6 observado: el mismo target y feature set, con búsqueda
estructurada y `reg:absoluteerror`, mejoró el CV temporal a MAE/RMSE/R2 de
1,379.7 ms / 4,585.0 ms / 0.020. Gana a zero-delta por 383.0 ms (21.7%) y a
train-mean por 233.2 ms. La confidence runtime de XGBoost ahora viene de
validación temporal (`base_confidence=0.755`) más penalizaciones por soporte de
features, no del R2 agregado.

| Métrica | scipy | XGBoost | Δ |
|---------|-------|---------|---|
| MAE@k=1 medio (ms) | 1753 | 1324 | -430 |
| MAE@k=3 medio (ms) | 1619 | 1424 | -195 |
| MAE@k=5 medio (ms) | 1637 | 1482 | -155 |
| Precision alertas | 0.0 | 0.0 | 0.0 |
| Recall alertas | 0.0 | 0.0 | 0.0 |
| F1 alertas | 0.0 | 0.0 | 0.0 |

El reporte se genera con `make compare-predictors` y queda en
`reports/ml/scipy_xgboost_backtest_report.json`. XGBoost mejora el error de
pace, y la mejora de MAE@k=3 (~12.0%) supera el umbral de 10% definido en ADR
0009 para el artifact entrenado. Aun así, las alertas siguen con F1=0.0; el
problema restante está en la superficie score/labels de decisión, no en la
confianza XGBoost.

## Cuándo usar cuál

Recomendaciones (post-experimento):

- **Demo "al profesor"**: `.env.example` sigue en `scipy` para que un clone limpio
  arranque sin artifact ML preentrenado. Si ya corriste `make train-xgb`, usa
  `xgboost` para mostrar el mejor simulador de pace y explica que la capa de
  alerta todavía no tiene F1 positivo.
- **Debug de motor**: usa `scipy` (predicciones interpretables).
- **Carreras con datos pobres**: scipy es más estable.
- **Carreras con muchos datos recientes**: XGBoost ya pasó el gate temporal y el
  umbral de MAE@k=3 del backtest demo, pero todavía no reemplaza a una capa de
  decisión calibrada.

## Implementación

- ScipyPredictor: [`backend/src/pitwall/degradation/`](../../backend/src/pitwall/degradation/)
- XGBoostPredictor: [`backend/src/pitwall/ml/predictor.py`](../../backend/src/pitwall/ml/predictor.py)
- Dataset/training: [`backend/src/pitwall/ml/`](../../backend/src/pitwall/ml/)
- Manifest: [`data/reference/ml_race_manifest.yaml`](../../data/reference/ml_race_manifest.yaml)
- Reporte temporal: [`notebooks/07_augmented_temporal_model.md`](../../notebooks/07_augmented_temporal_model.md)

## Quanta relacionadas

- [02 — Degradación](02-degradacion-neumatico.md)
- [07 — Backtest sin leakage](07-backtest-leakage.md)
