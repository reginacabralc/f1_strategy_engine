"""Backtest route — ``GET /api/v1/backtest/{session_id}``."""

from __future__ import annotations

from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Query, status

from pitwall.api.dependencies import get_engine_loop, get_event_loader
from pitwall.api.schemas import BacktestResult, PredictorName, UndercutMatch
from pitwall.core.config import get_settings
from pitwall.engine.backtest import BacktestResultData, run_backtest
from pitwall.engine.loop import EngineLoop
from pitwall.engine.projection import PacePredictor
from pitwall.repositories.events import SessionEventLoader

router = APIRouter(prefix="/api/v1", tags=["backtest"])

EventLoaderDep = Annotated[SessionEventLoader, Depends(get_event_loader)]
EngineLoopDep = Annotated[EngineLoop, Depends(get_engine_loop)]


@router.get(
    "/backtest/{session_id}",
    operation_id="getBacktestResult",
    summary="Engine alerts vs known undercuts for a session",
    response_model=BacktestResult,
    responses={
        404: {"description": "Session not found, or no replay events available."},
    },
)
async def get_backtest_result(
    session_id: str,
    event_loader: EventLoaderDep,
    engine_loop: EngineLoopDep,
    predictor: Annotated[
        PredictorName | None,
        Query(description="Predictor to evaluate. Defaults to the server-side active predictor."),
    ] = None,
) -> BacktestResult:
    """Return precision/recall/F1 for engine alerts vs replay-derived undercuts."""
    try:
        events = await event_loader.load_events(session_id)
    except Exception:
        events = []
    if not events:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No replay events available for session {session_id!r}.",
        )
    predictor_name = predictor or cast(PredictorName, engine_loop.predictor_name)
    active_predictor = _load_predictor(predictor_name, engine_loop)
    result = run_backtest(
        session_id,
        events,
        active_predictor,
        predictor_name=predictor_name,
        pit_loss_table=engine_loop._pit_loss_table,
    )
    return _to_schema(result)


def _load_predictor(name: PredictorName, engine_loop: EngineLoop) -> PacePredictor:
    if name == engine_loop.predictor_name:
        return engine_loop._predictor
    if name == "scipy":
        from pitwall.degradation.predictor import ScipyPredictor

        try:
            from pitwall.db.engine import create_db_engine

            return ScipyPredictor.from_engine(create_db_engine())
        except Exception:
            return ScipyPredictor([])

    settings = get_settings()
    model_path = settings.xgb_model_path
    try:
        from pitwall.ml.predictor import XGBoostPredictor

        return XGBoostPredictor.from_file(model_path)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"XGBoost model not found at '{model_path}'. Run 'make train-xgb' first.",
        ) from exc
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="XGBoost dependency is not installed in this runtime.",
        ) from exc


def _to_schema(result: BacktestResultData) -> BacktestResult:
    return BacktestResult(
        session_id=result.session_id,
        predictor=result.predictor,
        precision=result.precision,
        recall=result.recall,
        f1=result.f1,
        mean_lead_time_laps=result.mean_lead_time_laps,
        mae_k1_ms=result.mae_k1_ms,
        mae_k3_ms=result.mae_k3_ms,
        mae_k5_ms=result.mae_k5_ms,
        true_positives=[UndercutMatch(**match.__dict__) for match in result.true_positives],
        false_positives=[UndercutMatch(**match.__dict__) for match in result.false_positives],
        false_negatives=[UndercutMatch(**match.__dict__) for match in result.false_negatives],
    )
