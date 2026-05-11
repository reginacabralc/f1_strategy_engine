"""Degradation curve route — ``GET /api/v1/degradation``."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from pitwall.api.dependencies import get_degradation_repository
from pitwall.api.schemas import DegradationCoefficients, DegradationCurve
from pitwall.repositories.degradation import DegradationRepository

router = APIRouter(prefix="/api/v1", tags=["degradation"])

DegradationRepositoryDep = Annotated[DegradationRepository, Depends(get_degradation_repository)]

_VALID_COMPOUNDS = frozenset(("SOFT", "MEDIUM", "HARD", "INTER", "WET"))


@router.get(
    "/degradation",
    operation_id="getDegradationCurve",
    summary="Fitted degradation curve for a circuit + compound",
    response_model=DegradationCurve,
    responses={
        400: {"description": "Unknown compound value."},
        404: {"description": "No fit available for this (circuit, compound)."},
    },
)
async def get_degradation_curve(
    circuit: Annotated[str, Query(description="Circuit slug, e.g. monaco")],
    compound: Annotated[
        str,
        Query(description="Tyre compound: SOFT, MEDIUM, HARD, INTER, or WET"),
    ],
    repo: DegradationRepositoryDep,
) -> DegradationCurve:
    """Return the quadratic coefficients ``a + b·t + c·t²`` fitted by Stream A.

    404 when the DB has not been seeded yet or no fit exists for the pair.
    """
    compound_upper = compound.upper()
    if compound_upper not in _VALID_COMPOUNDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Unknown compound {compound!r}. "
                f"Must be one of {sorted(_VALID_COMPOUNDS)}."
            ),
        )

    row = await repo.get_coefficient(circuit.lower(), compound_upper)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"No degradation fit for circuit={circuit!r} compound={compound!r}. "
                "Run `make fit-degradation` to populate the coefficients."
            ),
        )

    return DegradationCurve(
        circuit_id=row.circuit_id,
        compound=row.compound,
        coefficients=DegradationCoefficients(a=row.a, b=row.b, c=row.c),
        r_squared=row.r_squared,
        n_samples=row.n_laps or 0,
    )
