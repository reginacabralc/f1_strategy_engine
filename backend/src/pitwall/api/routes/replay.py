"""Replay control routes.

POST /api/v1/replay/start  — boot a ReplayFeed against a session.
POST /api/v1/replay/stop   — stop the active replay (idempotent).

One replay runs at a time in V1.  The routes read the active
:class:`~pitwall.engine.replay_manager.ReplayManager` and
:class:`~pitwall.repositories.events.SessionEventLoader` from FastAPI
dependency injection so tests can substitute either without touching the
application code.

Both routes broadcast a ``replay_state`` WebSocket message when the replay
lifecycle changes, so connected clients can update their "replay active"
indicator without polling REST.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, HTTPException, status

from pitwall.api.connections import ConnectionManager
from pitwall.api.dependencies import (
    get_connection_manager,
    get_engine_loop,
    get_event_loader,
    get_replay_manager,
)
from pitwall.api.schemas import PredictorName, ReplayRun, ReplayStartRequest, ReplayStopResponse
from pitwall.engine.loop import EngineLoop
from pitwall.engine.replay_manager import ReplayManager
from pitwall.repositories.events import SessionEventLoader

router = APIRouter(prefix="/api/v1/replay", tags=["replay"])

ReplayManagerDep = Annotated[ReplayManager, Depends(get_replay_manager)]
SessionEventLoaderDep = Annotated[SessionEventLoader, Depends(get_event_loader)]
ConnectionManagerDep = Annotated[ConnectionManager, Depends(get_connection_manager)]
EngineLoopDep = Annotated[EngineLoop, Depends(get_engine_loop)]


def _replay_state_message(
    state: str,
    run_id: str,
    session_id: str,
    speed_factor: float,
    pace_predictor: str,
) -> dict[str, Any]:
    return {
        "v": 1,
        "type": "replay_state",
        "ts": datetime.now(UTC).isoformat(),
        "payload": {
            "run_id": run_id,
            "session_id": session_id,
            "state": state,
            "speed_factor": speed_factor,
            "pace_predictor": pace_predictor,
        },
    }


@router.post(
    "/start",
    operation_id="startReplay",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ReplayRun,
    summary="Start a replay of a historical session",
    responses={
        400: {"description": "Malformed request body."},
        404: {"description": "Session not found or has no events."},
        409: {"description": "A replay is already running."},
    },
)
async def start_replay(
    body: ReplayStartRequest,
    replay_manager: ReplayManagerDep,
    event_loader: SessionEventLoaderDep,
    cm: ConnectionManagerDep,
    engine_loop: EngineLoopDep,
) -> ReplayRun:
    if replay_manager.is_running:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"A replay for session {replay_manager.current_session_id!r} is already "
                "running. POST /api/v1/replay/stop first."
            ),
        )

    events = await event_loader.load_events(body.session_id)
    if not events:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {body.session_id!r} not found or has no events.",
        )

    run_id = await replay_manager.start(body.session_id, body.speed_factor, events)

    # Build response before the next await: the replay task may finish (draining a
    # short fixture) and set is_running=False, which would make started_at return None.
    response = ReplayRun(
        run_id=run_id,
        session_id=body.session_id,
        speed_factor=body.speed_factor,
        started_at=replay_manager.started_at,  # type: ignore[arg-type]
        pace_predictor=cast(PredictorName, engine_loop.predictor_name),
    )

    await cm.broadcast_json(
        _replay_state_message(
            state="started",
            run_id=str(run_id),
            session_id=body.session_id,
            speed_factor=body.speed_factor,
            pace_predictor=engine_loop.predictor_name,
        )
    )

    return response


@router.post(
    "/stop",
    operation_id="stopReplay",
    status_code=status.HTTP_200_OK,
    response_model=ReplayStopResponse,
    summary="Stop the active replay",
)
async def stop_replay(
    replay_manager: ReplayManagerDep,
    cm: ConnectionManagerDep,
    engine_loop: EngineLoopDep,
) -> ReplayStopResponse:
    # Read internal state BEFORE stop() clears it.  current_session_id gates on
    # is_running, which may already be False if the replay task finished on its own
    # (short fixture or speed_factor=∞).  The private attributes always hold the
    # last value until stop() resets them.
    session_id: str | None = replay_manager._session_id
    speed_factor: float = replay_manager._speed_factor or 1.0

    run_id = await replay_manager.stop()

    if run_id is not None and session_id is not None:
        await cm.broadcast_json(
            _replay_state_message(
                state="stopped",
                run_id=str(run_id),
                session_id=session_id,
                speed_factor=speed_factor,
                pace_predictor=engine_loop.predictor_name,
            )
        )

    return ReplayStopResponse(stopped=run_id is not None, run_id=run_id)
