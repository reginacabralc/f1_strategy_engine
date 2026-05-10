"""FastAPI dependency providers.

These are the seams each stream will fill in as their implementations land:

- ``get_session_repository`` — Stream A wires the SQL repo on Day 3.
- ``get_event_loader``       — Stream A wires the SQL event loader on Day 3.
- ``get_replay_manager``     — reads from ``request.app.state`` (set in
                               ``create_app()`` synchronously so it is
                               available even without the lifespan running).
- ``get_topics``             — same pattern as ``get_replay_manager``.

Tests should override providers with ``app.dependency_overrides`` rather
than monkey-patching this module:

    app.dependency_overrides[get_event_loader] = lambda: my_loader
"""

from __future__ import annotations

from functools import lru_cache

from fastapi import Request

from pitwall.core.topics import Topics
from pitwall.engine.replay_manager import ReplayManager
from pitwall.repositories.events import InMemorySessionEventLoader, SessionEventLoader
from pitwall.repositories.sessions import InMemorySessionRepository, SessionRepository


@lru_cache(maxsize=1)
def get_session_repository() -> SessionRepository:
    """Return the active :class:`SessionRepository`.

    V1 default: in-memory fixture with the three demo races.
    Stream A replaces this body with a SQL-backed implementation on Day 3.
    """
    return InMemorySessionRepository()


@lru_cache(maxsize=1)
def get_event_loader() -> SessionEventLoader:
    """Return the active :class:`SessionEventLoader`.

    V1 default: empty in-memory loader (always returns [] → 404 on replay
    start unless tests inject events via ``dependency_overrides``).
    Stream A wires a SQL loader here on Day 3 once the demo sessions are
    loaded into the DB.
    """
    return InMemorySessionEventLoader()


def get_replay_manager(request: Request) -> ReplayManager:
    """Return the process-wide :class:`ReplayManager` from ``app.state``.

    The manager is created synchronously in :func:`~pitwall.api.main.create_app`
    so it is available whether or not the lifespan context manager has run.
    """
    return request.app.state.replay_manager  # type: ignore[no-any-return]


def get_topics(request: Request) -> Topics:
    """Return the process-wide :class:`Topics` from ``app.state``."""
    return request.app.state.topics  # type: ignore[no-any-return]
