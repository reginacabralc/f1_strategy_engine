"""Runtime configuration routes — ``POST /api/v1/config/predictor``.

Allows switching the active :class:`~pitwall.engine.projection.PacePredictor`
without restarting the backend.  The new predictor takes effect on the next
``lap_complete`` processed by the engine loop.

XGBoost is gated behind a 409 until ``make train-xgb`` has produced
``models/xgb_pace_v1.json`` (Day 8–10).  Switching to ``scipy`` always
succeeds: it reloads coefficients from the DB or falls back to an empty
predictor if the DB is unreachable.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from pitwall.api.dependencies import get_engine_loop
from pitwall.api.schemas import SetPredictorRequest, SetPredictorResponse
from pitwall.core.config import get_settings
from pitwall.core.logging import get_logger
from pitwall.engine.loop import EngineLoop
from pitwall.engine.projection import PacePredictor

router = APIRouter(prefix="/api/v1/config", tags=["config"])

EngineLoopDep = Annotated[EngineLoop, Depends(get_engine_loop)]

_log = get_logger(__name__)


def _load_scipy() -> PacePredictor:
    """Reload ScipyPredictor from DB; fall back to empty on any error."""
    from pitwall.degradation.predictor import ScipyPredictor

    try:
        from pitwall.db.engine import create_db_engine

        return ScipyPredictor.from_engine(create_db_engine())
    except Exception:
        return ScipyPredictor([])


@router.post(
    "/predictor",
    operation_id="setActivePredictor",
    summary="Switch the active pace predictor at runtime",
    response_model=SetPredictorResponse,
    responses={
        400: {"description": "Unknown predictor name."},
        409: {"description": "Requested predictor is not loaded."},
    },
)
async def set_active_predictor(
    body: SetPredictorRequest,
    engine_loop: EngineLoopDep,
) -> SetPredictorResponse:
    """Switch ``PacePredictor`` between ``scipy`` and ``xgboost`` without restart.

    - ``scipy``: always succeeds; reloads coefficients from DB (empty fallback).
    - ``xgboost``: 409 until ``models/xgb_pace_v1.json`` exists (run
      ``make train-xgb`` first).
    """
    if body.predictor == "xgboost":
        settings = get_settings()
        model_path = Path(settings.xgb_model_path)
        if not model_path.exists():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"XGBoost model not found at '{model_path}'. "
                    "Run 'make train-xgb' to train and serialise the model first."
                ),
            )
        try:
            from pitwall.ml.predictor import XGBoostPredictor

            predictor: PacePredictor = XGBoostPredictor.from_file(model_path)
        except ImportError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "XGBoost dependency is not installed in this runtime. "
                    "The model file exists, but the predictor cannot load "
                    "without the xgboost package."
                ),
            ) from exc
    elif body.predictor == "causal":
        # Causal mode uses the scipy predictor for pace projection (the causal
        # graph itself is a structural-equation analyzer, not a learned pace
        # model — see docs/causal_model_performance.md). We swap to scipy under
        # the hood but tag the engine with the "causal" label so:
        #   1. snapshots broadcast active_predictor="causal"
        #   2. the causal observer keeps emitting predictor_used='causal' alerts
        #      (it already runs in parallel when demo_mode is active)
        # No XGBoost / causal model logic is altered.
        predictor = _load_scipy()
    else:
        predictor = _load_scipy()

    engine_loop.set_predictor(predictor, body.predictor)
    _log.info("predictor_switched", predictor=body.predictor)
    return SetPredictorResponse(active_predictor=body.predictor)
