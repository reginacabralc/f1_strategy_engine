# Quanta 01 — ¿Qué es un undercut?

## Concepto

Un **undercut** es una maniobra estratégica en F1 donde un piloto entra a boxes **antes** que su rival inmediato delante, con el objetivo de salir delante después de que ambos hayan parado. Funciona porque los neumáticos nuevos son significativamente más rápidos que los desgastados, y esa diferencia de pace puede acumular más tiempo del que se pierde en el pit stop.

## Por qué importa para el producto

PitWall **detecta automáticamente** cuándo un undercut es viable. Esto es lo que un muro de estrategia profesional calcula constantemente con datos privados; nosotros lo hacemos con datos abiertos. Es la señal central que el sistema entrega al usuario.

## Cómo se calcula

Para que un undercut sea viable, en una ventana de N vueltas (típicamente 3-5):

```
Ganancia_acumulada(N) > Pit_loss + Gap_actual + Threshold
```

Donde:

- **Ganancia_acumulada(N)**: suma de la diferencia de pace entre el rival con neumáticos viejos y nosotros con nuevos.
- **Pit_loss**: tiempo perdido al entrar a boxes (~21 segundos típicamente, pero varía).
- **Gap_actual**: distancia actual al rival (negativo si estamos detrás).
- **Threshold**: margen de seguridad (~0.5 s) para evitar undercuts marginales.

## Ejemplo numérico

Vuelta 18 del GP de Mónaco 2024. NOR está 2.5 s detrás de VER.

- Pace VER (MEDIUM, 18 vueltas) según curva: ~1:14.5
- Pace NOR si pone HARD nuevo: ~1:13.8 (con cold-tyre penalty primera vuelta de +0.8s = 1:14.6)
- Diferencia por vuelta a partir de vuelta 2: ~0.7 s/vuelta
- En 4 vueltas: 0.7 × 3 vueltas (descontando primera) ≈ 2.1 s acumulados

Pit loss en Mónaco para McLaren: ~22 s.

```
Ganancia_acumulada(4) = 2.1 s
Necesario = pit_loss + gap = 22 + 2.5 = 24.5 s
```

→ No conviene en este escenario salvo SC. PitWall **no** alertaría aquí.

Vs. el mismo caso pero con NOR a 0.5 s detrás:

```
Necesario = 22 + 0.5 = 22.5 s
Ganancia_acumulada(4) ≈ 2.1 s
```

Tampoco. Pero en circuitos de mayor degradación (Bahrein, Hungría) los números cambian dramáticamente.

## Riesgos / variantes

- **Overcut**: lo opuesto — quedarse fuera más tiempo cuando los neumáticos del rival se caen primero. PitWall **no detecta overcuts en V1**.
- **Tráfico al salir**: si después del pit stop sales con un piloto lento delante, el undercut "calculado" no se materializa. V1 ignora esto.
- **Cold-tyre penalty**: la primera vuelta con neumático nuevo es típicamente +0.8 s más lenta. V1 lo modela como constante.
- **Cliff de degradación**: si el rival está cerca del cliff (caída brusca de pace), el undercut puede ser **menos** efectivo de lo calculado, no más, porque el rival va a parar de todos modos.

## Implementación

- Cálculo: [`backend/src/pitwall/engine/undercut.py`](../../backend/src/pitwall/engine/undercut.py)
- Modelo de pace: [`backend/src/pitwall/engine/projection.py`](../../backend/src/pitwall/engine/projection.py)
- Pit loss: [`backend/src/pitwall/engine/pit_loss.py`](../../backend/src/pitwall/engine/pit_loss.py)

## Quanta relacionadas

- [02 — Degradación de neumáticos](02-degradacion-neumatico.md)
- [03 — Pit loss](03-pit-loss.md)
- [04 — Ventana de undercut](04-ventana-undercut.md)
