"""Session repository — list of sessions known to the system.

This module is the cross-stream seam for the ``/api/v1/sessions``
endpoint. Stream B's API layer depends on the :class:`SessionRepository`
Protocol; Stream A drops in :class:`SqlSessionRepository` on Day 3
once the DB is populated by ``scripts/ingest_season.py``. Until then
the in-memory implementation below serves the three demo races so the
HTTP surface and the frontend can be exercised end-to-end.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol


@dataclass(frozen=True, slots=True)
class SessionRow:
    """One row in the catalogue of available sessions.

    Field names match the ``SessionSummary`` schema in
    ``docs/interfaces/openapi_v1.yaml`` and the ``sessions`` and
    ``events`` tables in ``docs/interfaces/db_schema_v1.sql``.
    """

    session_id: str
    circuit_id: str
    season: int
    round_number: int
    date: date
    total_laps: int | None


class SessionRepository(Protocol):
    """Read-only access to the session catalogue."""

    async def list_sessions(self) -> list[SessionRow]: ...


# --------------------------------------------------------------------------
# V1 in-memory implementation — three demo races, round numbers verified
# against the 2024 calendar (see Stream A Day 1 sign-off).
# --------------------------------------------------------------------------


_DEMO_SESSIONS: tuple[SessionRow, ...] = (
    SessionRow(
        session_id="bahrain_2024_R",
        circuit_id="bahrain",
        season=2024,
        round_number=1,
        date=date(2024, 3, 2),
        total_laps=57,
    ),
    SessionRow(
        session_id="monaco_2024_R",
        circuit_id="monaco",
        season=2024,
        round_number=8,
        date=date(2024, 5, 26),
        total_laps=78,
    ),
    SessionRow(
        session_id="hungary_2024_R",
        circuit_id="hungary",
        season=2024,
        round_number=13,
        date=date(2024, 7, 21),
        total_laps=70,
    ),
)


class InMemorySessionRepository:
    """Returns the three demo races. Replace with SQL on Day 3."""

    def __init__(self, sessions: tuple[SessionRow, ...] | None = None) -> None:
        self._sessions = sessions if sessions is not None else _DEMO_SESSIONS

    async def list_sessions(self) -> list[SessionRow]:
        return list(self._sessions)
