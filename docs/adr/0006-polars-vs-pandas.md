# ADR 0006 — Polars en lugar de pandas para pipelines

## Estado

**Aceptado** — 2026-05-09

## Contexto

FastF1 devuelve `pandas.DataFrame` por defecto. Es el estándar del ecosistema Python de datos. Pero los pipelines de PitWall hacen joins, agrupaciones y filtros sobre miles de stints × decenas de carreras × varios años. Pandas funciona pero:

- Es single-threaded en operaciones costosas.
- API imperativa hace que pipelines largos sean difíciles de leer.
- Pierde tipos al guardar/cargar Parquet/CSV.

Polars es 5-10× más rápido en estas operaciones, tiene API declarativa (LazyFrame), y se integra bien con `read_database`/`write_database` para Postgres.

## Decisión

**Polars** para todos los pipelines de ingesta y análisis batch.

**Pandas** se permite solo en el límite con FastF1 (entrada) y en notebooks de exploración rápida. La conversión `pl.from_pandas(df)` se hace lo antes posible.

## Consecuencias

**Positivas:**

- Pipelines más rápidos → ingesta de 1 temporada en minutos, no horas.
- API declarativa hace que el código sea legible sin comentarios.
- LazyFrame permite optimización automática del plan.
- Tipos preservados al persistir.

**Negativas:**

- Curva de aprendizaje (aunque pequeña — quien sabe pandas aprende Polars en 1 día).
- Algunos snippets de Stack Overflow son pandas y hay que traducir.
- En notebooks exploratorios es tentador volver a pandas; lo permitimos pero pedimos justificación.

**Neutras:**

- `xgboost` acepta Polars (vía `to_numpy()` o `to_pandas()` en el límite).

## Alternativas consideradas

1. **Solo pandas** — descartada: lentitud en pipelines críticos.
2. **DuckDB en lugar de Polars** — descartada: SQL no es el modelo mental natural para feature engineering iterativo. DuckDB sí podría aparecer en el backend para queries complejas, pero para ETL es overkill.
3. **PySpark** — descartada: el volumen no justifica JVM overhead.

## Referencias

- [Polars docs](https://pola.rs/)
- [Polars vs pandas benchmarks](https://pola.rs/posts/benchmarks/)
