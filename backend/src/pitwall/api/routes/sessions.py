"""Session catalogue routes — ``/api/v1/sessions``."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from pitwall.api.dependencies import get_session_repository
from pitwall.api.schemas import SessionSummary
from pitwall.repositories.sessions import SessionRepository, SessionRow

router = APIRouter(prefix="/api/v1", tags=["sessions"])

SessionRepositoryDep = Annotated[SessionRepository, Depends(get_session_repository)]


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
