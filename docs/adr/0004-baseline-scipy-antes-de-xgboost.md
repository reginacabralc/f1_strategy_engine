# ADR 0004 — Baseline scipy antes de XGBoost (y LSTM fuera de V1)

## Estado

**Aceptado** — 2026-05-09

## Contexto

El profesor exige un componente de ML real en la entrega. La tentación obvia es pegarse directamente a XGBoost o incluso a una LSTM porque "es más sofisticado". El plan original mencionaba LSTM como pieza central.

Realidad de un sprint de 2 semanas con 4 personas:

- ~40 person-days totales.
- LSTM exige cuidado en split temporal, regularización, debugging interpretativo. 3 días no alcanzan para un modelo defendible.
- XGBoost es entrenamiento de minutos, métricas claras, integración simple.
- Sin baseline, no podemos saber si ML mejora algo.
- El bottleneck del producto es la **lógica de decisión y la calidad de los datos**, no la sofisticación del modelo.

## Decisión

Estrategia de ML en tres niveles:

1. **`ScipyPredictor` (baseline)** — V1, Días 4-5. Cuadrática `lap_time(t) = a + b·t + c·t²` por (circuito × compuesto), ajustada con `scipy.optimize.curve_fit`. Persistida en tabla `degradation_coefficients`.

2. **`XGBoostPredictor` (entregable de ML del MVP)** — V1, Días 8-10. `xgboost.XGBRegressor` con features categóricas y numéricas. Hiperparámetros fijos (`max_depth=5`, `n_estimators=400`, `learning_rate=0.05`, early stopping). Sin tuning extenso.

3. **LSTM** — **fuera de V1.** Solo en V2 si XGBoost deja MAE > 0.3s en cliff y hay tiempo dedicado.

Ambos predictores implementan la misma interfaz `PacePredictor`:

```python
class PacePredictor(Protocol):
    def predict(self, driver: str, compound: str, tyre_age: int, k: int) -> int: ...
    def confidence(self, driver: str, compound: str) -> float: ...
```

Switch en runtime con env var `PACE_PREDICTOR=scipy|xgb`.

## Consecuencias

**Positivas:**

- Cumplimos requisito del profesor (ML real entregado).
- Tenemos baseline contra el cual comparar honestamente.
- Si XGBoost no gana, **es información válida**, no fracaso. Lo documentamos.
- LSTM como V2 deja la puerta abierta sin comprometer el sprint.

**Negativas:**

- Mantenemos dos predictores en paralelo → doble código, doble test.
- Riesgo de que el equipo se obsesione con XGBoost y descuide el motor.

**Neutras:**

- La interfaz `PacePredictor` es trabajo extra el Día 4, pero permite el A/B desde Día 1.

## Alternativas consideradas

1. **Solo scipy** — descartada: el profesor exige ML.
2. **LSTM directo, sin baseline** — descartada: alta probabilidad de no llegar a tiempo, sin punto de comparación.
3. **XGBoost sin baseline scipy** — descartada: si XGBoost falla, no tenemos red. Y el baseline scipy es trivial de mantener.
4. **AutoML (FLAML, AutoGluon)** — descartada: no hay tiempo de explorar tooling nuevo, la interpretabilidad sufre.

## Resultado del experimento

Resultados reales del XGBoost vs scipy se cierran en [ADR 0009](0009-xgboost-vs-scipy-resultados.md) tras la Etapa 10 (Días 8-10 del sprint).

## Referencias

- [`docs/quanta/06-curva-fit-vs-xgboost.md`](../quanta/06-curva-fit-vs-xgboost.md)
- [Plan maestro § 9](../../.claude/plans/00-master-plan.md)
- ADRs relacionados: [0009](0009-xgboost-vs-scipy-resultados.md)
