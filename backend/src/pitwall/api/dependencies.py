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

from fastapi import Request

from pitwall.api.connections import ConnectionManager
from pitwall.core.topics import Topics
from pitwall.engine.loop import EngineLoop
from pitwall.engine.projection import PacePredictor
from pitwall.engine.replay_manager import ReplayManager
from pitwall.repositories.degradation import DegradationRepository, InMemoryDegradationRepository
from pitwall.repositories.events import InMemorySessionEventLoader, SessionEventLoader
from pitwall.repositories.sessions import InMemorySessionRepository, SessionRepository


@lru_cache(maxsize=1)
def get_session_repository() -> SessionRepository:
    """Return the active :class:`SessionRepository`.

    V1 default: in-memory fixture with the three demo races.
    Stream A can replace this body with a SQL-backed implementation.
    """
    return InMemorySessionRepository()


@lru_cache(maxsize=1)
def get_degradation_repository() -> DegradationRepository:
    """Return the active :class:`DegradationRepository`.

    V1 default: in-memory (empty → 404 until DB is seeded).
    Stream A wires a SQL implementation once ``make fit-degradation`` has run.
    """
    return InMemoryDegradationRepository()


@lru_cache(maxsize=1)
def get_event_loader() -> SessionEventLoader:
    """Return the active :class:`SessionEventLoader`.

    V1 default: empty in-memory loader (returns [] → 404 on replay start).
    Stream A wires a SQL loader here once the demo sessions are in the DB.
    """
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
        return loop._predictor  # noqa: SLF001
    except AttributeError:
        from pitwall.degradation.predictor import ScipyPredictor

        return ScipyPredictor([])
