"""Replay control routes.

POST /api/v1/replay/start  — boot a ReplayFeed against a session.
POST /api/v1/replay/stop   — stop the active replay (idempotent).

One replay runs at a time in V1.  The routes read the active
:class:`~pitwall.engine.replay_manager.ReplayManager` and
:class:`~pitwall.repositories.events.SessionEventLoader` from FastAPI
dependency injection so tests can substitute either without touching the
application code.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from pitwall.api.dependencies import get_event_loader, get_replay_manager
from pitwall.api.schemas import ReplayRun, ReplayStartRequest, ReplayStopResponse
from pitwall.core.config import get_settings
from pitwall.engine.replay_manager import ReplayManager
from pitwall.repositories.events import SessionEventLoader

router = APIRouter(prefix="/api/v1/replay", tags=["replay"])


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
    replay_manager: ReplayManager = Depends(get_replay_manager),
    event_loader: SessionEventLoader = Depends(get_event_loader),
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

    return ReplayRun(
        run_id=run_id,
        session_id=body.session_id,
        speed_factor=body.speed_factor,
        started_at=replay_manager.started_at,  # type: ignore[arg-type]
        pace_predictor=get_settings().pace_predictor,
    )


@router.post(
    "/stop",
    operation_id="stopReplay",
    status_code=status.HTTP_200_OK,
    response_model=ReplayStopResponse,
    summary="Stop the active replay",
)
async def stop_replay(
    replay_manager: ReplayManager = Depends(get_replay_manager),
) -> ReplayStopResponse:
    run_id = await replay_manager.stop()
    return ReplayStopResponse(stopped=run_id is not None, run_id=run_id)
