# Quanta 07 — Backtest sin leakage

## Concepto

**Data leakage** ocurre cuando información del futuro (o del set de evaluación) se filtra al modelo durante el entrenamiento. El resultado: métricas espectaculares en evaluación, fracaso en producción.

En PitWall hay 4 fuentes de leakage que **debemos evitar**:

1. Mezclar vueltas de la misma carrera entre train y test.
2. Usar features que son consecuencia de lo que queremos predecir.
3. Calcular agregados (medias, percentiles) sobre todo el dataset y luego splitear.
4. Usar información post-fact que no estaría disponible en runtime.

## Por qué importa para el producto

Si reportamos "MAE = 50 ms" pero secretamente entrenamos con la misma vuelta que evaluamos, mentimos al profesor y, peor, al equipo. El sistema parecerá funcionar y fallará en cuanto vea una carrera nueva.

## Estrategia de split: Leave-One-Race-Out (LORO)

```python
def loro_splits(sessions: list[str]) -> Iterator[tuple[list[str], str]]:
    """Para cada sesión, train = todas las demás, test = esta."""
    for held_out in sessions:
        train = [s for s in sessions if s != held_out]
        yield train, held_out
```

Reportamos métricas promediadas sobre todos los folds. Esto simula "una carrera nueva que el modelo no vio".

### ¿Por qué no random split sobre vueltas?

Si dividimos al azar, el modelo ve vueltas 1-50 de Mónaco 2024 en train y vueltas 51-78 en test. Pero esas vueltas están **fuertemente correlacionadas** (mismos pilotos, mismas condiciones, misma estrategia). El modelo "memoriza" la carrera. MAE en test será irrealmente bajo.

LORO rompe esa correlación.

### ¿Por qué no temporal split (2022 train, 2023 test, 2024 holdout)?

Es válido pero pierde datos: si solo tenemos 2024 ingerido, no podemos. LORO funciona dentro de un solo año.

## Features que NO usamos

| Feature | Por qué es leakage |
|---------|---------------------|
| `position` | Es consecuencia de la decisión de undercut, no causa |
| `gap_to_leader` | Igual |
| `pit_stop_lap` (sí o no) | Lo que queremos predecir indirectamente |
| `compound_next` | Información post-decisión |
| `final_classification` | Por supuesto |
| `was_undercut_successful` | Variable target del backtest, no feature |

## Features que SÍ usamos (sin leakage)

- `tyre_age`, `compound`, `circuit_id`
- `track_temp_c`, `air_temp_c`, `humidity` (disponibles en el momento)
- `lap_in_stint_ratio` (calculable en runtime con info histórica)
- `stint_position` (cuál stint es: 1°, 2°, 3°)
- `driver_skill_offset` (precomputado en train fold)
- `team_id`
- `fuel_proxy = 1 - laps_done / total_laps`

## Cuidado con agregados

Si calculamos `p20_of(compound, circuit)` sobre **todo** el dataset y luego usamos ese valor como referencia en train y test, es leakage: el p20 de test influyó en el p20 que vimos en train.

Solución:

```python
for train_sessions, test_session in loro_splits(all_sessions):
    p20_table = compute_p20_per_compound_circuit(train_sessions)  # solo train
    train_data = build_dataset(train_sessions, p20_table)
    test_data = build_dataset([test_session], p20_table)
    model = train(train_data)
    metrics = evaluate(model, test_data)
```

`p20_table` se computa por fold. **Nunca** sobre todo el dataset.

## Cuidado con `tyre_age` post-fact

FastF1 incluye `tyre_age` ya parseado. Pero ese parseo asume que conocemos la carrera completa. En runtime nosotros tenemos solo lo que pasó hasta ahora.

Solución: en el training set, usamos `tyre_age` calculado online (acumulando lap por lap desde el último `pit_out`). No usamos el `tyre_age` ya computado por FastF1 si no podemos replicarlo en runtime.

## Backtest del motor (no solo del modelo)

Además del backtest de la **predicción de pace** (MAE@k), evaluamos la **señal del motor**:

1. Curamos lista de ~15 undercuts conocidos: `(session, attacker, defender, lap, was_successful)`.
2. Replay determinista de cada sesión.
3. Para cada alerta `UNDERCUT_VIABLE` que emite el motor, marcamos:
   - **TP** si correspondió a un undercut real exitoso ≥ 1 vuelta antes.
   - **FP** si no.
4. Para cada undercut real conocido que NO fue alertado: **FN**.
5. Reportamos precision, recall, F1, lead time medio.

## Anti-pattern: "el modelo predice perfectamente Mónaco"

Si entrenamos con Mónaco 2023 y testeamos con Mónaco 2024, el modelo va a predecir bien (mismo circuito, mismas características). Pero generalizamos pobremente a Hungría.

**Reportamos métricas segmentadas** por circuito, compuesto, y bucket de `lap_in_stint_ratio`. Un solo número promedio oculta debilidades importantes.

## Reproducibilidad

- Random seed fijado: `random_state=42`.
- Versión exacta de xgboost en `pyproject.toml` con `==`.
- `model_registry` guarda metadatos: features usadas, fecha de entrenamiento, métricas obtenidas, hash de los datos de train.

## Implementación

- Split LORO: [`backend/src/pitwall/ml/dataset.py`](../../backend/src/pitwall/ml/dataset.py)
- Features (sin leakage): [`backend/src/pitwall/ml/features.py`](../../backend/src/pitwall/ml/features.py)
- Backtest motor: [`backend/src/pitwall/engine/backtest.py`](../../backend/src/pitwall/engine/backtest.py)
- Notebook: [`notebooks/04_backtest_v1.ipynb`](../../notebooks/04_backtest_v1.ipynb)

## Quanta relacionadas

- [06 — Curve fit vs XGBoost](06-curva-fit-vs-xgboost.md)
