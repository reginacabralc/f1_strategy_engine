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

- hiperparámetros por defecto conservadores,
- búsqueda pequeña opcional con `make tune-xgb`,
- selección por MAE temporal de validación, después RMSE y gap train-validación.

### Features

| Feature | Tipo |
|---------|------|
| `tyre_age` | int |
| `compound` | one-hot (SOFT/MEDIUM/HARD/INTER/WET) |
| `circuit_id` | one-hot |
| `track_temp_c` | float |
| `air_temp_c` | float |
| `humidity` | float |
| `lap_in_stint_ratio` | float ∈ [0, 1+] |
| `stint_position` | int (1, 2, 3, ...) |
| `driver_skill_offset` | float (precomputado) |
| `team_id` | one-hot |
| `fuel_proxy` | float ∈ [0, 1] |

### Target

```
delta_to_reference = lap_time_ms - p20_of(compound, circuit)
```

Donde `p20` es el percentil 20 (vueltas más rápidas) de ese (compuesto, circuito) en train fold.

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
[ADR 0010](../adr/0010-temporal-expanding-xgboost-validation.md): usar 2024/2025
recientes, validación temporal y tuning pequeño antes de Day 9.

| Métrica | scipy | XGBoost | Δ |
|---------|-------|---------|---|
| MAE@k=3 (ms) | _TBD_ | _TBD_ | _TBD_ |
| MAE en cliff (ms) | _TBD_ | _TBD_ | _TBD_ |
| Precision alertas | _TBD_ | _TBD_ | _TBD_ |
| Recall alertas | _TBD_ | _TBD_ | _TBD_ |

## Cuándo usar cuál

Recomendaciones (post-experimento):

- **Demo "al profesor"**: usa `xgb` para mostrar el componente de ML, pero
  explica si el modelo fue entrenado solo con las tres demos o con el manifiesto completo.
- **Debug de motor**: usa `scipy` (predicciones interpretables).
- **Carreras con datos pobres**: scipy es más estable.
- **Carreras con muchos datos recientes**: XGBoost es el candidato principal,
  pero debe ganar en CV temporal antes de hacerlo default de calidad.

## Implementación

- ScipyPredictor: [`backend/src/pitwall/degradation/`](../../backend/src/pitwall/degradation/)
- XGBoostPredictor: [`backend/src/pitwall/ml/predictor.py`](../../backend/src/pitwall/ml/predictor.py)
- Dataset/training: [`backend/src/pitwall/ml/`](../../backend/src/pitwall/ml/)
- Manifest: [`data/reference/ml_race_manifest.yaml`](../../data/reference/ml_race_manifest.yaml)
- Reporte temporal: [`notebooks/07_augmented_temporal_model.md`](../../notebooks/07_augmented_temporal_model.md)

## Quanta relacionadas

- [02 — Degradación](02-degradacion-neumatico.md)
- [07 — Backtest sin leakage](07-backtest-leakage.md)
