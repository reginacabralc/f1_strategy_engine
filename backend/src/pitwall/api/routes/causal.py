"""Causal undercut prediction route — ``GET /api/v1/causal/prediction``.

Read-only.  Does not alter alert semantics or the live engine loop.
Prediction is produced by ``evaluate_causal_live()`` using the same
ScipyPredictor that the engine loop uses.  The endpoint reconstructs
DriverState/RaceState from the query parameters and returns a
``CausalPredictionOut`` response.

This endpoint satisfies Day 2 of the Stream B causal plan: a human-callable
path that exercises the full causal structural-equation chain without a DB or
live replay session.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from pitwall.api.dependencies import get_predictor
from pitwall.causal.live_inference import CausalLiveResult, evaluate_causal_live
from pitwall.engine.pit_loss import DEFAULT_PIT_LOSS_MS
from pitwall.engine.projection import PacePredictor
from pitwall.engine.state import DriverState, RaceState

router = APIRouter(prefix="/api/v1/causal", tags=["causal"])

PredictorDep = Annotated[PacePredictor, Depends(get_predictor)]


# ---------------------------------------------------------------------------
# Response schema
# ---------------------------------------------------------------------------


class CausalCounterfactualOut(BaseModel):
    scenario_name: str
    undercut_viable: bool
    required_gain_ms: int | None = None
    projected_gain_ms: int | None = None
    projected_gap_after_pit_ms: int | None = None
    main_limiting_factor: str
    explanation: str


class CausalPredictionOut(BaseModel):
    session_id: str
    circuit_id: str
    lap_number: int
    attacker_code: str
    defender_code: str
    undercut_viable: bool
    support_level: str = Field(
        ...,
        description="One of: 'strong', 'weak', 'insufficient'.",
    )
    confidence: float = Field(..., ge=0.0, le=1.0)
    required_gain_ms: int | None = None
    projected_gain_ms: int | None = None
    projected_gap_after_pit_ms: int | None = None
    traffic_after_pit: str
    top_factors: list[str]
    explanations: list[str]
    counterfactuals: list[CausalCounterfactualOut]


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


@router.get(
    "/prediction",
    operation_id="getCausalPrediction",
    summary="Causal undercut viability prediction for one driver pair at one lap",
    response_model=CausalPredictionOut,
    responses={
        200: {"description": "Prediction produced successfully."},
    },
)
async def get_causal_prediction(
    predictor: PredictorDep,
    session_id: Annotated[
        str,
        Query(description="Session identifier, e.g. bahrain_2024_R", examples=["bahrain_2024_R"]),
    ] = "bahrain_2024_R",
    circuit_id: Annotated[
        str,
        Query(description="Circuit slug, e.g. bahrain", examples=["bahrain"]),
    ] = "bahrain",
    lap_number: Annotated[
        int,
        Query(ge=1, description="Current race lap number"),
    ] = 30,
    total_laps: Annotated[
        int | None,
        Query(ge=1, description="Total scheduled race laps"),
    ] = None,
    attacker: Annotated[
        str,
        Query(description="Attacker driver code, e.g. NOR", examples=["NOR"]),
    ] = "NOR",
    attacker_compound: Annotated[
        str,
        Query(description="Attacker tyre compound: SOFT, MEDIUM, HARD, INTER, or WET"),
    ] = "MEDIUM",
    attacker_tyre_age: Annotated[
        int,
        Query(ge=0, description="Attacker tyre age in laps"),
    ] = 15,
    defender: Annotated[
        str,
        Query(description="Defender driver code, e.g. VER", examples=["VER"]),
    ] = "VER",
    defender_compound: Annotated[
        str,
        Query(description="Defender tyre compound: SOFT, MEDIUM, HARD, INTER, or WET"),
    ] = "HARD",
    defender_tyre_age: Annotated[
        int,
        Query(ge=0, description="Defender tyre age in laps"),
    ] = 25,
    gap_ms: Annotated[
        int,
        Query(ge=0, description="Current gap attacker → defender in milliseconds"),
    ] = 5_000,
    pit_loss_ms: Annotated[
        int,
        Query(ge=0, description="Estimated pit-stop time loss in milliseconds"),
    ] = DEFAULT_PIT_LOSS_MS,
    track_status: Annotated[
        str,
        Query(description="Track status: GREEN, SC, VSC, YELLOW, RED"),
    ] = "GREEN",
    rainfall: Annotated[
        bool,
        Query(description="True if rainfall is reported at the circuit"),
    ] = False,
) -> CausalPredictionOut:
    """Return a causal undercut viability prediction for one driver pair.

    The endpoint constructs :class:`~pitwall.engine.state.RaceState` and
    :class:`~pitwall.engine.state.DriverState` from the supplied parameters and
    calls ``evaluate_causal_live()``.  No database access is required; the
    prediction runs entirely from the structural equations encoded in
    :mod:`pitwall.causal.live_inference`.

    The response includes:

    - ``undercut_viable``: primary boolean decision
    - ``support_level``: ``"strong"`` / ``"weak"`` / ``"insufficient"``
    - ``required_gain_ms`` / ``projected_gain_ms``: break-even accounting
    - ``counterfactuals``: seven what-if scenarios (pit_now, pit_next_lap, traffic
      high/low, pit_loss ±1 000 ms, base_case)
    - ``explanations``: human-readable bullets for each scenario

    This endpoint is read-only and does not affect WebSocket alerts.
    """
    state = RaceState(
        session_id=session_id,
        circuit_id=circuit_id,
        total_laps=total_laps,
        current_lap=lap_number,
        track_status=track_status,
        rainfall=rainfall,
    )
    attacker_state = DriverState(
        driver_code=attacker,
        position=2,
        gap_to_ahead_ms=gap_ms,
        compound=attacker_compound.upper(),
        tyre_age=attacker_tyre_age,
        laps_in_stint=attacker_tyre_age,
    )
    defender_state = DriverState(
        driver_code=defender,
        position=1,
        compound=defender_compound.upper(),
        tyre_age=defender_tyre_age,
        laps_in_stint=defender_tyre_age,
    )
    result: CausalLiveResult = evaluate_causal_live(
        state,
        attacker_state,
        defender_state,
        predictor,
        pit_loss_ms=pit_loss_ms,
    )
    return _to_response(result)


def _to_response(result: CausalLiveResult) -> CausalPredictionOut:
    obs = result.observation
    return CausalPredictionOut(
        session_id=obs.session_id,
        circuit_id=obs.circuit_id,
        lap_number=obs.lap_number,
        attacker_code=obs.attacker_code,
        defender_code=obs.defender_code,
        undercut_viable=result.undercut_viable,
        support_level=result.support_level,
        confidence=result.confidence,
        required_gain_ms=result.required_gain_ms,
        projected_gain_ms=result.projected_gain_ms,
        projected_gap_after_pit_ms=result.projected_gap_after_pit_ms,
        traffic_after_pit=result.traffic_after_pit,
        top_factors=list(result.top_factors),
        explanations=list(result.explanations),
        counterfactuals=[
            CausalCounterfactualOut(
                scenario_name=cf.scenario_name,
                undercut_viable=cf.undercut_viable,
                required_gain_ms=cf.required_gain_ms,
                projected_gain_ms=cf.projected_gain_ms,
                projected_gap_after_pit_ms=cf.projected_gap_after_pit_ms,
                main_limiting_factor=cf.main_limiting_factor,
                explanation=cf.explanation,
            )
            for cf in result.counterfactuals
        ],
    )
