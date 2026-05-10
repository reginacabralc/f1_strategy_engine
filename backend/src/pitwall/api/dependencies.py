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
from pitwall.db.engine import create_db_engine, database_url_from_env
from pitwall.engine.replay_manager import ReplayManager
from pitwall.repositories.events import InMemorySessionEventLoader, SessionEventLoader
from pitwall.repositories.sessions import InMemorySessionRepository, SessionRepository
from pitwall.repositories.sql import EngineLike, SqlSessionEventLoader, SqlSessionRepository


@lru_cache(maxsize=1)
def _db_engine_or_none() -> EngineLike | None:
    """Return a configured DB engine, or ``None`` when local DB is not enabled."""
    try:
        database_url = database_url_from_env()
    except RuntimeError:
        return None
    return create_db_engine(database_url)


@lru_cache(maxsize=1)
def get_session_repository() -> SessionRepository:
    """Return the active :class:`SessionRepository`.

    Uses the Stream A SQL repository when ``DATABASE_URL`` is configured,
    otherwise falls back to the in-memory three-race demo catalogue.
    """
    engine = _db_engine_or_none()
    if engine is not None:
        return SqlSessionRepository(engine)
    return InMemorySessionRepository()


@lru_cache(maxsize=1)
def get_event_loader() -> SessionEventLoader:
    """Return the active :class:`SessionEventLoader`.

    Uses the Stream A SQL replay-event loader when ``DATABASE_URL`` is
    configured. Without a DB URL, replay starts still require test or
    development fixtures injected via ``dependency_overrides``.
    """
    engine = _db_engine_or_none()
    if engine is not None:
        return SqlSessionEventLoader(engine)
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
