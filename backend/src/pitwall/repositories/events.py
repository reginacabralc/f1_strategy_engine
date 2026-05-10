"""SessionEventLoader — loads the ordered event sequence for a session.

This is the DB-side seam for the replay pipeline. Stream B owns the
Protocol; Stream A drops a SQL-backed implementation in on Day 3 by
editing ``pitwall.api.dependencies.get_event_loader``.

The pattern mirrors ``SessionRepository`` from Day 2: today we ship the
Protocol plus an in-memory fixture loader; the SQL loader follows once
Alembic migrations and demo data are in place.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pitwall.feeds.base import Event


@runtime_checkable
class SessionEventLoader(Protocol):
    """Provide the ordered replay-event sequence for a given session.

    Implementations must return events sorted ascending by ``ts``.
    An empty list means the session is unknown or has no data — callers
    treat this as a 404.
    """

    async def load_events(self, session_id: str) -> list[Event]:
        """Return all events for *session_id* in ascending ts order."""
        ...


class InMemorySessionEventLoader:
    """Fixture-backed loader for use before Stream A wires the DB.

    Pass a ``sessions`` mapping of ``{session_id: [Event, ...]}``.
    An unknown *session_id* returns an empty list.
    """

    def __init__(
        self,
        sessions: dict[str, list[Event]] | None = None,
    ) -> None:
        self._sessions: dict[str, list[Event]] = sessions or {}

    async def load_events(self, session_id: str) -> list[Event]:
        events = self._sessions.get(session_id, [])
        return sorted(events, key=lambda e: e["ts"])
