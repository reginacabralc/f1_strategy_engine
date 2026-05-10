# Bitácora — PitWall

> Posts cortos (~150 palabras) en orden cronológico inverso. Aprendizajes honestos, decisiones difíciles, sorpresas. No marketing.

---

## 2026-05-09 — Por qué este proyecto y por qué replay-first

**Autor:** equipo

Arrancamos PitWall con un objetivo claro: detectar undercuts en F1 con datos abiertos, en vivo. La primera tentación fue armar un poller asíncrono que consumiera OpenF1 cada 4 segundos y emitiera eventos al motor. La descartamos.

Razón: el calendario F1 no espera. Un sprint de 2 semanas no puede depender de "ojalá haya GP el viernes". Y peor, debuggear un sistema en vivo es exponencialmente más difícil que debuggear con datos reproducibles.

La solución: un **Replay Engine** que lee FastF1 histórico y emite eventos al mismo formato que tendría OpenF1. La interfaz `RaceFeed` deja la puerta abierta para `OpenF1Feed` en V2, sin tocar el motor.

Beneficio adicional: los tests pueden correr el replay a 1000× sobre Mónaco 2024 y validar que el motor genera las alertas correctas. Eso es CI con sentido.

Costo: cero, porque era lo que tendríamos que hacer de todos modos para tests.

---

_(siguiente post irá arriba al cerrarlo)_
