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

Por (circuito × compuesto). Parámetros ajustados con `scipy.optimize.curve_fit`
sobre vueltas válidas; si SciPy no puede importarse en el entorno local, el
script usa un fallback cuadrático equivalente con NumPy para mantener la
reproducibilidad.

Antes del ajuste, la vuelta se normaliza con proxies disponibles pre-pit:
offset mediano de piloto dentro del grupo, combustible por vuelta de carrera y
penalización de tráfico por `gap_to_ahead_ms`.

### Pros

- Interpretable: 3 números por (circuito × compuesto), entendibles sin ML.
- Rápido: predicción es una multiplicación.
- Estable: poco riesgo de overfitting.
- Funciona con pocos datos.

### Cons

- Lineal-cuadrático no captura el cliff. Si la degradación es exponencial al final, el modelo se queda corto.
- Una sola curva por compuesto/circuito solo neutraliza diferencias de piloto,
  combustible y tráfico mediante proxies; no mide esas variables directamente.
- `track_temp` no entra como feature.

## XGBoostPredictor (entregable de ML)

### Modelo

`xgboost.Booster` nativo con:

- `max_depth=4`, `eta=0.08`, `subsample=0.9`, `colsample_bytree=0.9`
- `num_boost_round=250`
- Sin tuning extenso (timebox).

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

La referencia actual es la mediana fold-safe de vueltas limpias por
`(compound, circuit)` con fallback por compuesto. En runtime, el metadata del
modelo guarda mapas de referencia para convertir el delta predicho de vuelta a
lap time absoluto.

### Split

**Leave-one-race-out (LORO)**: para cada hold-out race, entrenamos con el resto. Esto evita leakage temporal y permite reportar honestamente cómo generalizaría a una carrera nueva.

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

_(Llenar al cerrar [ADR 0009](../adr/0009-xgboost-vs-scipy-resultados.md))_

| Métrica | scipy | XGBoost | Δ |
|---------|-------|---------|---|
| MAE@k=3 (ms) | _TBD_ | _TBD_ | _TBD_ |
| MAE en cliff (ms) | _TBD_ | _TBD_ | _TBD_ |
| Precision alertas | _TBD_ | _TBD_ | _TBD_ |
| Recall alertas | _TBD_ | _TBD_ | _TBD_ |

## Cuándo usar cuál

Recomendaciones (post-experimento):

- **Demo "al profesor"**: usa `xgb` para mostrar el componente de ML.
- **Debug de motor**: usa `scipy` (predicciones interpretables).
- **Carreras con datos pobres**: scipy es más estable.
- **Carreras con muchos datos**: XGBoost generalmente gana.

## Implementación

- ScipyPredictor: [`backend/src/pitwall/degradation/`](../../backend/src/pitwall/degradation/)
- XGBoostPredictor: [`backend/src/pitwall/ml/predictor.py`](../../backend/src/pitwall/ml/predictor.py)
- Entrenamiento: [`backend/src/pitwall/ml/train_xgb.py`](../../backend/src/pitwall/ml/train_xgb.py)
- Notebook: [`notebooks/05_xgboost_train_eval.ipynb`](../../notebooks/05_xgboost_train_eval.ipynb)

## Quanta relacionadas

- [02 — Degradación](02-degradacion-neumatico.md)
- [07 — Backtest sin leakage](07-backtest-leakage.md)
