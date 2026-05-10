# Quanta 02 — Degradación de neumáticos

## Concepto

La **degradación** es la pérdida de pace de un neumático conforme acumula vueltas. Tres factores principales:

1. **Desgaste mecánico** del compuesto (los SOFT degradan más rápido que HARD).
2. **Térmico**: el neumático se sobrecalienta o se enfría fuera del rango óptimo.
3. **Granulado / blistering**: superficie pierde adherencia.

En F1 moderna, la degradación dominante es la mecánica + térmica. El cliff (caída brusca al final de la vida útil) ocurre cuando se cruza un umbral térmico o de desgaste.

## Por qué importa para el producto

La proyección de pace de los pilotos N vueltas hacia adelante depende **enteramente** de qué tan bien modelemos la degradación. Si nuestro modelo dice "VER pierde 0.1s/vuelta" pero realmente pierde 0.4s/vuelta, el cálculo del undercut es inservible.

## Cómo se modela en PitWall

### Baseline V1 (`ScipyPredictor`)

Por cada par (circuito × compuesto) ajustamos:

```
lap_time(t) = a + b·t + c·t²
```

Donde `t` = tyre_age (vueltas en este compuesto). Coeficientes vía `scipy.optimize.curve_fit` sobre vueltas válidas (clean air, no SC, no pit-in/out, no deleted).

Persistido en tabla `degradation_coefficients` con R² del ajuste y `n_samples`.

### V1 ML (`XGBoostPredictor`)

XGBoost predice `delta_to_reference = lap_time - p20_of(compound, circuit)` con features:

- `tyre_age`, `compound_one_hot`, `circuit_id_one_hot`
- `track_temp`, `air_temp`, `humidity`
- `lap_in_stint_ratio`, `stint_position`
- `driver_skill_offset`, `team_id_one_hot`
- `fuel_proxy = 1 - laps_done / total_laps`

El cliff se captura sin programación explícita gracias a `lap_in_stint_ratio` y la no-linealidad de los árboles.

## Ejemplo numérico

Mónaco 2024, compuesto MEDIUM. Coeficientes ajustados:

```
a = 74_500    # ms en vuelta 0
b = 120        # ms degradación lineal por vuelta
c = 5          # ms² aceleración cuadrática
```

Predicción para `tyre_age=15`:

```
74_500 + 120·15 + 5·15² = 74_500 + 1_800 + 1_125 = 77_425 ms = 1:17.425
```

Si la vuelta real fue 1:17.6, error = 175 ms. MAE típico ~300-500 ms en cliff, ~150-300 ms en early-stint.

## Filtros antes de ajustar

Críticos para no contaminar el modelo:

- **`is_pit_in == False`** y **`is_pit_out == False`**: las out/in laps son drásticamente distintas.
- **`is_valid == True`**: vueltas eliminadas por la FIA (track limits) se descartan.
- **`track_status == 'GREEN'`**: SC y VSC alteran el lap_time.
- **lap_time razonable**: 60_000 < lap_time_ms < 180_000 (entre 1:00 y 3:00).
- **outliers a 3σ**: descartados.

## Riesgos / variantes

- **Mónaco** y **Singapur** tienen muchas SC y stints cortos → R² bajo. Caemos a degradación lineal en circuitos con < N vueltas válidas.
- **Lluvia**: INTER y WET tienen degradación muy distinta y dependen del nivel de agua. V1 emite `UNDERCUT_DISABLED_RAIN` y no proyecta.
- **2022 datos**: huecos en `Compound`. Excluido del entrenamiento por ahora.

## Implementación

- Fit scipy: [`backend/src/pitwall/degradation/fit.py`](../../backend/src/pitwall/degradation/fit.py)
- XGBoost: [`backend/src/pitwall/ml/`](../../backend/src/pitwall/ml/)
- Filtros: [`backend/src/pitwall/ingest/normalize.py`](../../backend/src/pitwall/ingest/normalize.py)

## Quanta relacionadas

- [06 — Curve fit vs XGBoost](06-curva-fit-vs-xgboost.md)
- [07 — Backtest sin leakage](07-backtest-leakage.md)
