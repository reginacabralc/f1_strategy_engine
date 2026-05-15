"""FastAPI dependency providers.

These are the seams each stream will fill in as their implementations land:

- ``get_session_repository`` — Stream A wires the SQL repo on Day 3 (done).
- ``get_event_loader``       — Stream A wires the SQL event loader on Day 3 (done).
- ``get_replay_manager``     — reads from ``request.app.state``.
- ``get_topics``             — reads from ``request.app.state``.
- ``get_connection_manager`` — reads from ``request.app.state``.
- ``get_engine_loop``        — reads from ``request.app.state``.

Tests should override providers with ``app.dependency_overrides`` rather
than monkey-patching this module::

    app.dependency_overrides[get_event_loader] = lambda: my_loader
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from fastapi import Request

from pitwall.api.connections import ConnectionManager
from pitwall.core.topics import Topics
from pitwall.db.engine import create_db_engine, database_url_from_env
from pitwall.engine.loop import EngineLoop
from pitwall.engine.projection import PacePredictor
from pitwall.engine.replay_manager import ReplayManager
from pitwall.repositories.degradation import DegradationRepository, InMemoryDegradationRepository
from pitwall.repositories.events import InMemorySessionEventLoader, SessionEventLoader
from pitwall.repositories.sessions import InMemorySessionRepository, SessionRepository
from pitwall.repositories.sql import (
    SqlDegradationRepository,
    SqlSessionEventLoader,
    SqlSessionRepository,
)


@lru_cache(maxsize=1)
def _sql_engine_if_configured() -> Any | None:
    """Return a cached SQLAlchemy engine when DATABASE_URL is configured.

    Unit tests and no-DB local API usage keep the in-memory fixtures. Docker,
    ``make demo``, and DB-backed local development set ``DATABASE_URL`` and use
    the real Stream A tables.
    """
    try:
        database_url = database_url_from_env()
    except RuntimeError:
        return None
    if not database_url:
        return None
    return create_db_engine(database_url)


@lru_cache(maxsize=1)
def get_session_repository() -> SessionRepository:
    """Return the active :class:`SessionRepository`.

    Use Stream A's SQL-backed repository when ``DATABASE_URL`` is configured.
    Without a DB URL, fall back to the in-memory demo catalogue used by unit
    tests and no-DB local exploration.
    """
    engine = _sql_engine_if_configured()
    if engine is not None:
        return SqlSessionRepository(engine)
    return InMemorySessionRepository()


@lru_cache(maxsize=1)
def get_degradation_repository() -> DegradationRepository:
    """Return the active :class:`DegradationRepository`.

    Use Stream A's persisted ``degradation_coefficients`` when a DB is
    configured. Without a DB URL, keep the empty in-memory repository.
    """
    engine = _sql_engine_if_configured()
    if engine is not None:
        return SqlDegradationRepository(engine)
    return InMemoryDegradationRepository()


@lru_cache(maxsize=1)
def get_event_loader() -> SessionEventLoader:
    """Return the active :class:`SessionEventLoader`.

    Use DB events when ``DATABASE_URL`` is configured; otherwise return the
    empty in-memory loader so tests can inject fixture events explicitly.
    """
    engine = _sql_engine_if_configured()
    if engine is not None:
        return SqlSessionEventLoader(engine)
    return InMemorySessionEventLoader()


def get_replay_manager(request: Request) -> ReplayManager:
    """Return the process-wide :class:`ReplayManager` from ``app.state``."""
    return request.app.state.replay_manager  # type: ignore[no-any-return]


def get_topics(request: Request) -> Topics:
    """Return the process-wide :class:`Topics` from ``app.state``."""
    return request.app.state.topics  # type: ignore[no-any-return]


def get_connection_manager(request: Request) -> ConnectionManager:
    """Return the process-wide :class:`ConnectionManager` from ``app.state``."""
    return request.app.state.connection_manager  # type: ignore[no-any-return]


def get_engine_loop(request: Request) -> EngineLoop:
    """Return the process-wide :class:`EngineLoop` from ``app.state``."""
    return request.app.state.engine_loop  # type: ignore[no-any-return]


def get_predictor(request: Request) -> PacePredictor:
    """Return the process-wide :class:`PacePredictor` from the engine loop.

    Used by the causal prediction endpoint so it shares the same predictor
    instance that the live engine uses.  Falls back to an empty ScipyPredictor
    if ``app.state.engine_loop`` is not present (e.g. in unit tests that use
    ``TestClient(create_app())`` without starting the lifespan).
    """
    try:
        loop: EngineLoop = request.app.state.engine_loop
        return loop._predictor
    except AttributeError:
        from pitwall.degradation.predictor import ScipyPredictor

        return ScipyPredictor([])
