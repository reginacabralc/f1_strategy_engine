# ADR 0009 — Resultado del experimento XGBoost vs scipy

## Estado

**Aceptado** — 2026-05-16

Nota 2026-05-16: el runtime XGBoost ya está integrado vía `PacePredictor` y
el comparativo replay-backed se genera con `make compare-predictors`.

Enmienda 2026-05-16: después del hardening de tuning y confidence, el artifact
XGBoost entrenado supera el umbral de MAE@k=3. `.env.example` sigue en `scipy`
para que un clone limpio arranque sin artifact ML preentrenado, pero el
predictor recomendado cuando `models/xgb_pace_v1.json` existe es `xgboost`.

## Contexto

[ADR 0004](0004-baseline-scipy-antes-de-xgboost.md) decidió implementar dos predictores:

- `ScipyPredictor` (baseline cuadrático)
- `XGBoostPredictor` (entregable de ML)

Ambos detrás de la interfaz `PacePredictor`, con switch en runtime. Este ADR documenta los resultados reales del experimento al final del sprint.

## Decisión

**Default bootstrap `PACE_PREDICTOR` = `scipy`; recommended trained artifact =
`xgboost`.**

Criterio de elección:

- Si `XGBoostPredictor` mejora MAE@k=3 en al menos 10% sobre baseline en hold-out → artifact recomendado `xgb`.
- Si mejora marginalmente (< 5%) → default `scipy` (más simple).
- Si empeora → default `scipy`, documentamos honestamente que con el dataset disponible XGBoost no generaliza.

Resultado observado actualizado: XGBoost mejoró MAE@k=3 medio de 1619 ms a
1424 ms (~12.0%), superando el umbral de 10%. Ambos predictores tuvieron F1=0.0
en las tres sesiones demo porque no emitieron alertas que matchearan los
undercuts exitosos derivados de replay. Por eso XGBoost gana como simulador de
pace, pero todavía no resuelve la capa de decisión.

## Resultados

### Métricas

| Métrica | Baseline scipy | XGBoost | Δ | Mejora? |
|---------|---------------|---------|---|---------|
| MAE@k=1 | 1753 ms | 1324 ms | -430 ms | sí |
| MAE@k=3 | 1619 ms | 1424 ms | -195 ms | sí, >10% |
| MAE@k=5 | 1637 ms | 1482 ms | -155 ms | sí |
| Precision alertas | 0.0 | 0.0 | 0.0 | no |
| Recall alertas | 0.0 | 0.0 | 0.0 | no |
| F1 alertas | 0.0 | 0.0 | 0.0 | no |

Fuente: `reports/ml/scipy_xgboost_backtest_report.json`, generado con
`make compare-predictors` sobre Bahrain, Monaco y Hungary 2024 demo.

### Por sesión

| Sesión | Predictor | MAE@k=1 | MAE@k=3 | MAE@k=5 | TP | FP | FN |
|--------|-----------|---------|---------|---------|----|----|----|
| bahrain_2024_R | scipy | 1887 | 1900 | 1956 | 0 | 0 | 13 |
| bahrain_2024_R | xgboost | 1482 | 1550 | 1597 | 0 | 0 | 13 |
| monaco_2024_R | scipy | 1789 | 1373 | 1356 | 0 | 0 | 2 |
| monaco_2024_R | xgboost | 1150 | 1274 | 1376 | 0 | 0 | 2 |
| hungary_2024_R | scipy | 1584 | 1584 | 1599 | 0 | 0 | 10 |
| hungary_2024_R | xgboost | 1339 | 1448 | 1473 | 0 | 0 | 10 |

## Consecuencias

**Positivas:**

- XGBoost ya no es stub: se puede alternar en runtime, evaluar por API y
  reemplazar por un futuro `xgb_pace_v2.json` con el mismo contrato sidecar.
- XGBoost reduce MAE de pace en promedio frente a scipy en las tres sesiones demo.
- `scipy` se mantiene como bootstrap default simple mientras se mejora la calidad
  de alerta y para no requerir artifacts ML en clones limpios.

**Negativas:**

- La mejora de pace no produce por si sola alertas correctas.
- Ningún predictor emite alertas que matcheen los undercuts exitosos derivados
  del replay demo; el siguiente trabajo debe ajustar umbrales/contexto de alerta,
  no solo entrenar otro modelo.
- El runtime XGBoost depende de un artifact entrenado localmente; si no existe,
  el sistema debe caer a `scipy` o pedir `make train-xgb`.

## Acciones derivadas

- [x] Default en `.env.example` permanece `scipy` para bootstrap limpio.
- [x] Quanta `06-curva-fit-vs-xgboost.md` con números reales.
- [x] Si hay caminos claros de mejora (decision labels, tuning de score, otras
  features), documentar como issues post-MVP.

## Referencias

- [ADR 0004](0004-baseline-scipy-antes-de-xgboost.md) — la decisión que dio origen al experimento.
- [ADR 0011](0011-temporal-expanding-xgboost-validation.md) — validación temporal sin leakage.
- [`docs/quanta/06-curva-fit-vs-xgboost.md`](../quanta/06-curva-fit-vs-xgboost.md)
- `reports/ml/scipy_xgboost_backtest_report.json` — fuente local de los números.
