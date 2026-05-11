"""Degradation-coefficient repository — cross-stream seam for the degradation API.

Stream B's ``GET /api/v1/degradation`` reads from :class:`DegradationRepository`.
Stream A populates the DB with coefficients via ``scripts/fit_degradation.py``;
the SQL-backed implementation in :mod:`pitwall.repositories.sql` queries that
table directly.  Until the DB is seeded the in-memory fallback returns ``None``
(→ 404) for every query.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class CoefficientRow:
    """One row from ``degradation_coefficients``.

    Field names match the DB table defined in ``docs/interfaces/db_schema_v1.sql``
    and the ``DegradationCurve`` schema in ``docs/interfaces/openapi_v1.yaml``.
    """

    circuit_id: str
    compound: str
    a: float
    b: float
    c: float
    r_squared: float | None
    n_laps: int | None


class DegradationRepository(Protocol):
    """Read quadratic degradation coefficients for a (circuit, compound) pair."""

    async def get_coefficient(
        self, circuit_id: str, compound: str
    ) -> CoefficientRow | None: ...


# ---------------------------------------------------------------------------
# In-memory fallback — used until the DB is seeded
# ---------------------------------------------------------------------------


class InMemoryDegradationRepository:
    """In-memory coefficient store.  Empty by default → 404 on every query.

    Pass a pre-populated ``rows`` dict to seed coefficients in tests.
    """

    def __init__(
        self,
        rows: dict[tuple[str, str], CoefficientRow] | None = None,
    ) -> None:
        self._rows = rows or {}

    async def get_coefficient(
        self, circuit_id: str, compound: str
    ) -> CoefficientRow | None:
        return self._rows.get((circuit_id.lower(), compound.upper()))
