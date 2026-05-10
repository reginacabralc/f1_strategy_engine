# ADR 0001 — Stack base

## Estado

**Aceptado** — 2026-05-09

## Contexto

PitWall es un sistema de tiempo real con 4 cargas distintas: ingesta histórica, motor de cálculo async, API + WebSocket, dashboard interactivo. Necesita correr en `docker compose up` en cualquier máquina con Docker. Equipo de 4 personas, sprint de 2 semanas, requisito de ML.

Restricciones:

- Datos abiertos solamente (FastF1, OpenF1, Jolpica).
- Bibliotecas con buen soporte para series temporales y ML.
- Frontend que tolere updates frecuentes vía WebSocket.
- Stack que un equipo pequeño domine sin curva de aprendizaje pesada.

## Decisión

| Capa | Tecnología | Razón breve |
|------|------------|-------------|
| Lenguaje backend | **Python 3.12** | Ecosistema F1/ML/data |
| API framework | **FastAPI** | Async nativo, OpenAPI gratis, simple |
| ASGI server | **uvicorn** | Estándar con FastAPI |
| Datos | **Polars** + **scipy** + **xgboost** | Polars rápido y declarativo; scipy para curve fit; xgboost para ML |
| WebSockets | **`fastapi.WebSocket`** | No introducir librería extra |
| ORM/Migrations | **SQLModel** + **Alembic** | SQLModel = Pydantic + SQLAlchemy; Alembic estándar |
| DB | **PostgreSQL 15** + **TimescaleDB** | Time-series con queries SQL, sin nuevo paradigma |
| Lenguaje frontend | **TypeScript 5.x** | Tipado obligatorio para tabla con muchos campos |
| Build frontend | **Vite** | Build rápido, dev server con HMR |
| Framework UI | **React** | Curva conocida; equipo confortable |
| Estado servidor | **TanStack Query** | Cache + reintentos + invalidación sin Redux |
| Estilos | **Tailwind CSS** | Velocidad de iteración para UI no pulida |
| Charts | **Recharts** | React-native, no D3 raw |
| Tests backend | **pytest** + **hypothesis** + **testcontainers** | Estándar |
| Tests frontend | **vitest** + **React Testing Library** + **Playwright** | RTL para componentes, Playwright para 1 e2e |
| Lint | **ruff** + **mypy** + **eslint** + **prettier** | ruff por velocidad, mypy por type safety |
| Package manager Python | **uv** | Más rápido que pip/poetry, lockfile reproducible |
| Package manager Node | **pnpm** | Más rápido que npm, mejor caching |
| Infra local | **docker-compose** | Único requisito del profesor |
| CI | **GitHub Actions** | Repo en GitHub, sin costo |

## Consecuencias

**Positivas:**

- Stack mainstream, fácil contratar tutoriales y resolver dudas.
- FastAPI da OpenAPI sin esfuerzo → cumple requisito del profesor.
- Polars + xgboost cubre la línea ETL → ML sin saltar a Spark.
- Tailwind acelera UI; el equipo no pierde tiempo eligiendo paleta.

**Negativas:**

- Vamos a tener Python en backend y TypeScript en frontend → dos pipelines de tooling.
- TimescaleDB añade capa sobre Postgres; no todos los desarrolladores la conocen (mitigado: queremos básico, ver [ADR 0003](0003-timescaledb.md)).
- `uv` y `pnpm` son relativamente nuevos; algunos en el equipo pueden tener que aprender.

**Neutras:**

- Monorepo con dos lenguajes (ver [ADR 0005](0005-monorepo-vs-polirepo.md)).

## Alternativas consideradas

1. **Node.js (NestJS) en backend** — descartado: el ecosistema de datos y ML es mucho más débil.
2. **Django + Channels** — descartado: pesado para un sprint de 2 semanas; FastAPI es más liviano.
3. **Pandas en lugar de Polars** — descartado: Polars 5-10× más rápido para los pipelines de ingesta, ver [ADR 0006](0006-polars-vs-pandas.md).
4. **Vue / Svelte en lugar de React** — descartado: el equipo conoce mejor React.

## Referencias

- [FastAPI docs](https://fastapi.tiangolo.com/)
- [Polars docs](https://pola.rs/)
- [TimescaleDB](https://www.timescale.com/)
- [ADR 0005](0005-monorepo-vs-polirepo.md), [ADR 0006](0006-polars-vs-pandas.md)
