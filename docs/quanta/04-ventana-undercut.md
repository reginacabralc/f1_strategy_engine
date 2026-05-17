# Quanta 04 — Ventana de undercut

## Concepto

La **ventana de undercut** es el rango de vueltas en el que un undercut sería viable para un par dado de pilotos. Conceptualmente, es la respuesta a:

> "Si NOR para AHORA, ¿en qué vuelta saldrá delante de VER?"

Si esa vuelta cae **antes** del momento en que VER planeaba parar, el undercut funciona.

## Por qué importa para el producto

PitWall convierte la matemática del undercut en una **señal binaria + score**: alerta vs no alerta, con confianza. La ventana es el cálculo intermedio.

## Cómo se calcula en PitWall

Para un par `(attacker, defender)` en vuelta `t`:

```python
def evaluate_undercut(state, attacker, defender, predictor):
    pit_loss = pit_loss_for(circuit, attacker.team)
    gap_actual = gap(defender, attacker)  # positivo si defender está delante

    # Proyección de pace por k vueltas hacia adelante
    fresh_compound = next_likely_compound(attacker.compound, race_progress)
    
    gain_acumulada = 0
    ventana = None
    for k in range(1, 6):  # k = 1..5
        defender_lap = predictor.predict(defender, defender.compound, defender.tyre_age + k, k)
        attacker_lap = predictor.predict(attacker, fresh_compound, k, k) + cold_tyre_penalty(k)
        gain_acumulada += (defender_lap - attacker_lap)
        
        if gain_acumulada >= pit_loss + gap_actual + 500:  # threshold 0.5s
            ventana = k
            break
    
    score = clamp((gain_acumulada - pit_loss - gap_actual) / pit_loss, 0, 1)
    confidence = min(predictor.confidence(defender), predictor.confidence(attacker)) * data_quality_factor(state)
    
    return Decision(
        ventana=ventana,
        score=score,
        confidence=confidence,
        should_alert=(score > 0.4 and confidence > 0.5),
    )
```

## Cold tyre penalty

Los neumáticos nuevos no rinden óptimamente la primera vuelta. Modelo simple V1:

```python
def cold_tyre_penalty(k):
    return {1: 800, 2: 300, 3: 0}.get(k, 0)  # ms
```

Calibrado de comparar out-laps históricas con vueltas óptimas en el mismo stint.

## Filtros para "par relevante"

No calculamos undercut para todos los pares, solo:

```python
def compute_relevant_pairs(state):
    pairs = []
    for i in range(len(state.drivers) - 1):
        d1, d2 = drivers_in_position[i], drivers_in_position[i+1]
        if not (d1.is_in_pit or d2.is_in_pit):
            if not (d1.is_lapped or d2.is_lapped):
                if abs(gap(d1, d2)) < 30_000:  # < 30s
                    if d2.tyre_age >= 3:  # stint suficientemente largo
                        if d2.last_pit_lap is None or (state.current_lap - d2.last_pit_lap) > 2:
                            pairs.append((d2, d1))  # attacker = atrás, defender = adelante
    return pairs
```

## Score y confidence

- **score ∈ [0, 1]**: 0 = no viable, 1 = ganancia >> pit_loss + gap.
- **confidence ∈ [0, 1]**: soporte validado del predictor para el contexto
  runtime. En scipy sigue dependiendo de la calidad del ajuste y del dato vivo;
  en XGBoost se calibra desde validación temporal (`confidence_calibration`) y
  se penaliza por categorías desconocidas o features live faltantes. Ya no se
  interpreta como "R2 > 0.5".

Alerta solo si **score > 0.4 AND confidence > 0.5**.

## Ejemplo numérico

Hungría 2024, vuelta 22, par (HAM=attacker, RUS=defender):

```
gap_actual = +1.8 s (RUS delante)
pit_loss(hungary, mercedes) = 21_500 ms

Predicciones:
  k=1: RUS=1:18.5 (HARD, age=22), HAM=1:18.2 (MEDIUM nuevo, +0.8 cold)  → gain = 0.3 s
  k=2: RUS=1:18.7,                 HAM=1:17.5 (+0.3 cold)                → gain += 1.2 → 1.5 s
  k=3: RUS=1:18.9,                 HAM=1:17.4                           → gain += 1.5 → 3.0 s
  k=4: RUS=1:19.2,                 HAM=1:17.4                           → gain += 1.8 → 4.8 s
  k=5: RUS=1:19.5,                 HAM=1:17.5                           → gain += 2.0 → 6.8 s

¿gain >= pit_loss + gap + threshold?
  21.5 + 1.8 + 0.5 = 23.8 s
  6.8 < 23.8 → NO viable en 5 vueltas.

→ No alerta. Score = clamp((6.8 - 21.5 - 1.8) / 21.5, 0, 1) = 0.
```

(Ejemplo construido para mostrar el flujo. Los números reales dependen de los coeficientes ajustados.)

## Riesgos / variantes

- **Ventana > 5 vueltas**: típicamente significa que el rival va a parar antes que se materialice el undercut. V1 no alerta más allá de k=5.
- **Cambio de compuesto al pit**: V1 asume HARD si el progreso de carrera es > 50%, sino SOFT. Heurística simple, mejorable.
- **Doble stop estratégico**: V1 no contempla "undercut con doble stop". Solo undercut clásico.

## Implementación

- Función principal: [`backend/src/pitwall/engine/undercut.py::evaluate_undercut`](../../backend/src/pitwall/engine/undercut.py)
- Pares relevantes: [`backend/src/pitwall/engine/undercut.py::compute_relevant_pairs`](../../backend/src/pitwall/engine/undercut.py)

## Quanta relacionadas

- [01 — Undercut](01-undercut.md)
- [02 — Degradación](02-degradacion-neumatico.md)
- [03 — Pit loss](03-pit-loss.md)
