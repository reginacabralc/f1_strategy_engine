"""Session catalogue routes — ``/api/v1/sessions`` and snapshot."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, status

from pitwall.api.dependencies import (
    get_engine_loop,
    get_replay_manager,
    get_session_repository,
)
from pitwall.api.schemas import (
    DriverStateOut,
    PredictorName,
    RaceSnapshotOut,
    SessionSummary,
)
from pitwall.engine.loop import EngineLoop
from pitwall.engine.replay_manager import ReplayManager
from pitwall.repositories.sessions import SessionRepository, SessionRow

router = APIRouter(prefix="/api/v1", tags=["sessions"])

SessionRepositoryDep = Annotated[SessionRepository, Depends(get_session_repository)]
ReplayManagerDep = Annotated[ReplayManager, Depends(get_replay_manager)]
EngineLoopDep = Annotated[EngineLoop, Depends(get_engine_loop)]


def _row_to_summary(row: SessionRow) -> SessionSummary:
    return SessionSummary(
        session_id=row.session_id,
        circuit_id=row.circuit_id,
        season=row.season,
        round_number=row.round_number,
        date=row.date,
        total_laps=row.total_laps,
    )


@router.get(
    "/sessions",
    operation_id="listSessions",
    summary="List sessions present in the database",
    response_model=list[SessionSummary],
)
async def list_sessions(
    repo: SessionRepositoryDep,
) -> list[SessionSummary]:
    rows = await repo.list_sessions()
    return [_row_to_summary(r) for r in rows]


@router.get(
    "/sessions/{session_id}/snapshot",
    operation_id="getSessionSnapshot",
    summary="Current engine state for an active replay",
    response_model=RaceSnapshotOut,
    responses={
        404: {"description": "No active replay for this session."},
    },
)
async def get_session_snapshot(
    session_id: str,
    replay_manager: ReplayManagerDep,
    engine_loop: EngineLoopDep,
) -> RaceSnapshotOut:
    """Return the in-memory ``RaceState`` for the session currently being replayed.

    404 if there is no active replay or the active replay is for a different session.
    """
    if not replay_manager.is_running or replay_manager.current_session_id != session_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No active replay for session {session_id!r}.",
        )

    state = engine_loop.state
    drivers = sorted(
        state.drivers.values(),
        key=lambda d: (d.position is None, d.position),
    )

    return RaceSnapshotOut(
        session_id=state.session_id or session_id,
        current_lap=state.current_lap,
        track_status=state.track_status,
        track_temp_c=state.track_temp_c,
        air_temp_c=state.air_temp_c,
        humidity_pct=state.humidity_pct,
        drivers=[
            DriverStateOut(
                driver_code=d.driver_code,
                team_code=d.team_code,
                position=d.position,
                gap_to_leader_ms=d.gap_to_leader_ms,
                gap_to_ahead_ms=d.gap_to_ahead_ms,
                last_lap_ms=d.last_lap_ms,
                compound=d.compound,
                tyre_age=d.tyre_age,
                is_in_pit=d.is_in_pit,
                is_lapped=d.is_lapped,
                last_pit_lap=d.last_pit_lap,
                stint_number=d.stint_number,
                undercut_score=d.undercut_score,
            )
            for d in drivers
        ],
        active_predictor=cast(PredictorName, engine_loop.predictor_name),
        last_event_ts=state.last_event_ts or datetime.now(UTC),
    )
