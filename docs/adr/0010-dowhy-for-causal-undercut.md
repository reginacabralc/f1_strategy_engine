# ADR 0010 — DoWhy For Causal Undercut Analysis

## Estado

Aceptado

## Contexto

Stream B is adding an independent causal undercut viability module. The existing
XGBoost pace model remains the ML deliverable and must not define the causal
graph, treatments, outcomes, or confounders. We need a small, auditable causal
inference layer that can encode the DAG, identify estimands, estimate simple
effects, and later run refuters.

The project runs locally and in Docker from `backend/pyproject.toml`, so any new
runtime dependency must be declared there rather than installed only in a local
virtualenv.

## Decisión

Add `dowhy>=0.12,<0.14` as a backend dependency and use it only inside the
`pitwall.causal` package and causal scripts.

DoWhy will be used for offline causal analysis over the
`driver-rival-lap` dataset. It is not a live classifier, not a replacement for
XGBoost, and not a source of DAG structure. The DAG remains domain-authored in
`pitwall.causal.graph`.

## Consecuencias

- **Positivas**: We can identify estimands, estimate simple backdoor effects,
  and add refuters in Phase 7 using a standard causal inference library.
- **Negativas**: Docker/backend installs become heavier because DoWhy brings
  scientific Python dependencies such as graph/statistical tooling.
- **Neutras**: Causal scripts should fail with clear errors if the dependency is
  missing in an old local environment, and developers should rerun
  `make install` after this ADR lands.

## Alternativas consideradas

1. **Hand-roll causal estimators only** — rejected because identification and
   refutation would become ad hoc and harder to explain.
2. **Use XGBoost feature importance as causal evidence** — rejected because
   predictive attribution is not causal inference.
3. **Keep DoWhy notebook-only** — rejected because Docker and CI need a
   reproducible dependency path.

## Referencias

- `docs/CAUSAL_MODEL.md`
- `.claude/plans/stream-b-causal-undercut.md`
- ADR 0004 — Baseline scipy before XGBoost
