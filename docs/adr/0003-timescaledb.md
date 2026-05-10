# ADR 0003 — TimescaleDB sí, Redis no en V1

## Estado

**Aceptado** — 2026-05-09

## Contexto

Tenemos datos time-series (vueltas por carrera, alertas con timestamp) y necesitamos una capa de persistencia. La conversación tradicional ofrece varios candidatos:

- Postgres puro
- Postgres + TimescaleDB
- InfluxDB / TimescaleDB Cloud
- Redis para snapshot in-memory + Postgres para persistencia
- Kafka + cualquiera de los anteriores

El volumen real es trivial: 1 temporada ≈ 30k vueltas + algunos miles de eventos. Cualquier DB lo aguanta.

## Decisión

**TimescaleDB encima de Postgres 15** para las tablas time-series (`laps`, `alerts`, `live_lap_events`). Postgres normal para catálogos (`circuits`, `drivers`, `sessions`, etc.).

**No usamos Redis** ni ningún broker. Estado in-memory del motor vive en el proceso del backend (`RaceState` reconstruible desde el feed).

## Consecuencias

**Positivas:**

- Queries de degradación se simplifican con `time_bucket()` y vistas continuas de Timescale.
- Misma DB para todo → un solo backup, una sola conexión, una sola migración.
- Sin Redis = un servicio menos en docker-compose, menos memoria.
- Si el estado in-memory se pierde, lo reconstruimos del feed (replay determinista).

**Negativas:**

- Dependencia de la imagen `timescale/timescaledb:latest-pg15` en lugar de Postgres oficial.
- Un nuevo desarrollador tiene que aprender 2-3 funciones de Timescale (`create_hypertable`, `time_bucket`).

**Neutras:**

- En V2 si crece el volumen, Timescale escala mejor que Postgres puro.

## Alternativas consideradas

1. **Postgres puro** — descartado: las queries de buckets temporales son más verbosas. Por el costo cero de añadir Timescale, ganamos.
2. **Redis para estado in-memory** — descartado: el estado del motor cabe en RAM y es reconstruible. Redis añade complejidad sin beneficio en V1.
3. **InfluxDB** — descartado: no SQL, dos lenguajes de query, pelea con FastAPI/SQLModel.
4. **Kafka + Postgres** — descartado: overkill total para volumen actual y para 2 semanas.

## Referencias

- [TimescaleDB documentation](https://docs.timescale.com/)
- [`docs/architecture.md` § 5](../architecture.md)
