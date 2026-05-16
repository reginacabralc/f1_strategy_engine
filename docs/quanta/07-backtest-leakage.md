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

1. Derivamos undercuts exitosos desde replay: un atacante entra a pits detrás
   de un defensor y termina delante después del intercambio.
2. Ignoramos pit stops de vuelta 1 y paradas que no invierten posición.
3. Replay determinista de cada sesión con `ScipyPredictor` y `XGBoostPredictor`.
4. Para cada alerta `UNDERCUT_VIABLE`:
   - **TP** si matchea atacante/defensor y cae dentro de la ventana `K_MAX`.
   - **FP** si no matchea ningún undercut exitoso.
5. Para cada undercut exitoso no alertado: **FN**.
6. Reportamos precision, recall, F1, lead time medio y MAE@k=1/3/5.

## Anti-pattern: "el modelo predice perfectamente Mónaco"

Si entrenamos con Mónaco 2023 y testeamos con Mónaco 2024, el modelo va a predecir bien (mismo circuito, mismas características). Pero generalizamos pobremente a Hungría.

**Reportamos métricas segmentadas** por circuito, compuesto, y bucket de `lap_in_stint_ratio`. Un solo número promedio oculta debilidades importantes.

## Reproducibilidad

- Random seed fijado: `random_state=42`.
- Versión exacta de xgboost en `pyproject.toml` con `==`.
- El sidecar `models/xgb_pace_v1.meta.json` guarda features usadas, fecha de
  entrenamiento, métricas y política de leakage. El reporte comparativo queda
  en `reports/ml/scipy_xgboost_backtest_report.json`.

## Implementación

- Dataset y features sin leakage: [`backend/src/pitwall/ml/dataset.py`](../../backend/src/pitwall/ml/dataset.py)
- Runtime XGBoost: [`backend/src/pitwall/ml/predictor.py`](../../backend/src/pitwall/ml/predictor.py)
- Backtest motor: [`backend/src/pitwall/engine/backtest.py`](../../backend/src/pitwall/engine/backtest.py)
- Script de comparación: [`scripts/compare_predictors.py`](../../scripts/compare_predictors.py)

## Quanta relacionadas

- [06 — Curve fit vs XGBoost](06-curva-fit-vs-xgboost.md)
