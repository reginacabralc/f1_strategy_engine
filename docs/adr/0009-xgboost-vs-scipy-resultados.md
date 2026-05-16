# ADR 0009 — Resultado del experimento XGBoost vs scipy

## Estado

**Propuesto** — _queda abierto hasta Day 9 backtesting_

Nota 2026-05-13: Day 8 diagnostics showed the 3-race XGBoost model is
engineering-complete but too weak to decide the runtime default. ADR 0011 now
defines the required temporal validation path before this ADR can be closed.

## Contexto

[ADR 0004](0004-baseline-scipy-antes-de-xgboost.md) decidió implementar dos predictores:

- `ScipyPredictor` (baseline cuadrático)
- `XGBoostPredictor` (entregable de ML)

Ambos detrás de la interfaz `PacePredictor`, con switch en runtime. Este ADR documenta los resultados reales del experimento al final del sprint.

## Decisión

_(Se cierra después de la E10 con datos reales. Esqueleto de la decisión:)_

**Default `PACE_PREDICTOR` =** _`scipy` | `xgb`_ — basado en métricas medibles.

Criterio de elección:

- Si `XGBoostPredictor` mejora MAE@k=3 en al menos 10% sobre baseline en hold-out → default `xgb`.
- Si mejora marginalmente (< 5%) → default `scipy` (más simple).
- Si empeora → default `scipy`, documentamos honestamente que con el dataset disponible XGBoost no generaliza.

## Resultados

_(Se llenan al final del sprint.)_

### Métricas

| Métrica | Baseline scipy | XGBoost | Δ | Mejora? |
|---------|---------------|---------|---|---------|
| MAE@k=1 | _ms_ | _ms_ | _ms_ | _sí/no_ |
| MAE@k=3 | _ms_ | _ms_ | _ms_ | _sí/no_ |
| MAE@k=5 | _ms_ | _ms_ | _ms_ | _sí/no_ |
| MAE en cliff (último 20% stint) | _ms_ | _ms_ | _ms_ | _sí/no_ |
| Precision alertas | _0.X_ | _0.X_ | _Δ_ | _sí/no_ |
| Recall alertas | _0.X_ | _0.X_ | _Δ_ | _sí/no_ |
| Inferencia/par (ms) | _<1_ | _<5_ | _+Y_ | _aceptable/no_ |

### Por compuesto

_(Tabla por SOFT/MEDIUM/HARD)_

### Por bucket de `lap_in_stint_ratio`

_(Tabla por bucket 0-25%, 25-50%, 50-75%, 75-100%)_

## Consecuencias

_(Se llenan al cerrar.)_

**Positivas:**

- _e.g._ XGBoost captura mejor el cliff de degradación.
- _e.g._ scipy es más predecible y rápido.

**Negativas:**

- _e.g._ XGBoost tiene MAE peor en early-stint, posiblemente por overfitting.
- _e.g._ regenerar el modelo es un paso extra cuando se cargan nuevas carreras.

## Acciones derivadas

- [ ] Default en `.env.example` actualizado.
- [ ] README sección "ML" actualizada.
- [ ] Quanta `06-curva-fit-vs-xgboost.md` con números reales.
- [ ] Si hay caminos claros de mejora (más datos, tuning, otras features), documentar como issues post-MVP.

## Referencias

- [ADR 0004](0004-baseline-scipy-antes-de-xgboost.md) — la decisión que dio origen al experimento.
- [ADR 0011](0011-temporal-expanding-xgboost-validation.md) — validación temporal sin leakage.
- [`docs/quanta/06-curva-fit-vs-xgboost.md`](../quanta/06-curva-fit-vs-xgboost.md)
- [`notebooks/04_backtest_v1.ipynb`](../../notebooks/04_backtest_v1.ipynb) — fuente de los números.
