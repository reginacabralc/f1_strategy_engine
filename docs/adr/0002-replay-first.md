# ADR 0002 — Replay-first en lugar de live polling de OpenF1 en V1

## Estado

**Aceptado** — 2026-05-09

## Contexto

El plan original proponía un poller asyncio que consumiera 5 endpoints de OpenF1 en paralelo (gaps cada 4s, compuesto cada 10s, pit stops live, temperatura cada 60s) como pieza central del sistema.

Problemas con esa aproximación para un sprint de 2 semanas:

1. **Dependencia del calendario F1**: si no hay GP durante el sprint, no podemos probar el sistema en condiciones reales.
2. **Reproducibilidad cero**: cada ejecución sobre live es única, imposible debuggear.
3. **Tests débiles**: no podemos correr CI sobre datos live.
4. **Rate limits no documentados**: OpenF1 ha mostrado 429s con polling agresivo.
5. **Lag variable**: algunos endpoints van con 2-5 s de retraso, complicando sincronización.

## Decisión

En V1 **no implementamos `OpenF1Feed` real**. En su lugar:

1. Definimos una interfaz abstracta `RaceFeed` que emite eventos al motor.
2. Implementamos `ReplayFeed(RaceFeed)` que lee de la DB histórica (FastF1 ya ingerido) y emite eventos al ritmo del factor de velocidad configurable.
3. Mantenemos un **stub** `OpenF1Feed(RaceFeed)` con la firma correcta pero sin implementación real.
4. El motor consume `RaceFeed`, no sabe si los eventos vienen de replay o live.

V2 implementará `OpenF1Feed` real reemplazando solo esa clase. Cero cambios al motor.

## Consecuencias

**Positivas:**

- Desarrollo y testing reproducibles en cualquier momento.
- CI puede correr el replay sobre Mónaco 2024 a 1000× y validar métricas.
- Independencia total del calendario F1.
- Migración a live en V2 es localizada.
- Backtest se vuelve trivial: el "replay" del backtest usa la misma maquinaria.

**Negativas:**

- En la demo no podemos decir "esto está corriendo sobre la carrera de mañana".
- El equipo puede subestimar problemas que solo aparecen en live (lag, jitter, datos faltantes).

**Neutras:**

- La interfaz `RaceFeed` es ligeramente más compleja de lo que sería un poller hardcodeado, pero el costo es mínimo.

## Alternativas consideradas

1. **Live OpenF1 en V1** — descartada por las 5 razones del contexto.
2. **Replay sin interfaz, hardcodeado al motor** — descartada: cero migración futura, cero testabilidad.
3. **Mock de OpenF1 servido por un servicio aparte (HTTP)** — descartada: complejidad innecesaria, tests más lentos.

## Referencias

- [OpenF1 API](https://openf1.org)
- [`docs/quanta/05-replay-engine.md`](../quanta/05-replay-engine.md)
- ADRs relacionados: [0007](0007-asyncio-sin-broker.md)
