# ADR 0005 — Monorepo backend + frontend en mismo repo

## Estado

**Aceptado** — 2026-05-09

## Contexto

Con un equipo de 4 personas y dos lenguajes (Python backend, TypeScript frontend), una decisión recurrente es: ¿un solo repo o dos?

## Decisión

**Un solo repo (monorepo)** con dos workspaces:

- `backend/` — Python, gestionado con `uv`.
- `frontend/` — TypeScript, gestionado con `pnpm`.
- Raíz: `docker-compose.yaml`, `Makefile`, `docs/`, `infra/`, `scripts/` compartidos, CI compartido.

## Consecuencias

**Positivas:**

- Un solo `git clone`, un solo `make demo`.
- PRs que tocan back + front se ven completos en un solo diff.
- CI corre todo en un workflow.
- Refactors transversales (renombrar campo del schema → endpoint → UI) son atómicos.

**Negativas:**

- El histórico de git mezcla cambios de back y front. Mitigamos con scopes en commits (`feat(api):`, `feat(frontend):`).
- Dependencias y tooling de dos lenguajes en mismo repo → CI más largo. Mitigamos con paths-filter en GitHub Actions.

**Neutras:**

- Mismas reglas de PR para ambos.

## Alternativas consideradas

1. **Dos repos separados** — descartada: el costo de mantener dos repos, dos CI, dos releases, no se justifica para un equipo de 4 en 2 semanas.
2. **Monorepo con Nx/Turborepo** — descartada: overhead de tooling para un proyecto de este tamaño.

## Referencias

- [`docs/architecture.md`](../architecture.md)
