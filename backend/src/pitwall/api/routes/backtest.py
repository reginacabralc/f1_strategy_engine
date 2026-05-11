"""Backtest route — ``GET /api/v1/backtest/{session_id}``.

Compares the alerts emitted by the engine during a replay against the
curated list of known historical undercuts (Stream A, E9-E10).

V1 status: returns 404 until Stream A populates the curated undercut table
in the DB and implements the backtest runner.  The route and schema are
wired now so the contract test tracks the ``operationId`` and Stream C can
render a placeholder backtest view.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from pitwall.api.schemas import BacktestResult, PredictorName

router = APIRouter(prefix="/api/v1", tags=["backtest"])


@router.get(
    "/backtest/{session_id}",
    operation_id="getBacktestResult",
    summary="Engine alerts vs known undercuts for a session",
    response_model=BacktestResult,
    responses={
        404: {"description": "Session not found, or no curated known-undercut list yet."},
    },
)
async def get_backtest_result(
    session_id: str,
    predictor: Annotated[
        PredictorName | None,
        Query(description="Predictor to evaluate. Defaults to the server-side active predictor."),
    ] = None,
) -> BacktestResult:
    """Return precision/recall/F1 for engine alerts vs curated undercuts.

    **Stream A (E9-E10) wires the implementation.**  Until then this
    endpoint returns 404 — the curated known-undercut table has not been
    populated yet.  Frontend should show a "results pending" placeholder.
    """
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=(
            f"No curated undercut list available for session {session_id!r}. "
            "Run 'make backtest' once Stream A has populated the known-undercut "
            "table (E9-E10)."
        ),
    )
