"""FastAPI application factory.

Run locally with::

    uvicorn pitwall.api.main:app --reload --port 8000

The module-level ``app`` is the artifact uvicorn imports. Tests build
their own copy via :func:`create_app` to keep a clean dependency
override surface.

State management
----------------
:class:`~pitwall.core.topics.Topics` and
:class:`~pitwall.engine.replay_manager.ReplayManager` are created
synchronously inside ``create_app()`` and attached to ``app.state``
immediately.  This means they are available even when ``TestClient`` is
used without a context manager (i.e. without running the lifespan).
The lifespan only performs cleanup on shutdown.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from pitwall import __version__
from pitwall.api.routes import sessions as sessions_routes
from pitwall.api.routes import replay as replay_routes
from pitwall.api.schemas import Health
from pitwall.core.config import get_settings
from pitwall.core.logging import configure_logging
from pitwall.core.topics import Topics
from pitwall.engine.replay_manager import ReplayManager


def create_app() -> FastAPI:
    """Build a fresh FastAPI app instance.

    Each call creates new :class:`~pitwall.core.topics.Topics` and
    :class:`~pitwall.engine.replay_manager.ReplayManager` instances so
    tests that call ``create_app()`` are fully isolated.
    """
    settings = get_settings()
    configure_logging(settings.log_level)

    topics = Topics()
    replay_manager = ReplayManager(topics)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        await replay_manager.stop()

    app = FastAPI(
        title="PitWall API",
        version=__version__,
        description=(
            "Real-time F1 undercut detection engine. "
            "WebSocket channel documented in "
            "`docs/interfaces/websocket_messages.md`."
        ),
        lifespan=lifespan,
    )

    app.state.topics = topics
    app.state.replay_manager = replay_manager

    @app.get(
        "/health",
        operation_id="getHealth",
        tags=["health"],
        summary="Liveness probe",
        response_model=Health,
    )
    async def health() -> Health:
        """Always returns 200 when the process is alive."""
        return Health(status="ok", version=__version__)

    @app.get(
        "/ready",
        operation_id="getReady",
        tags=["health"],
        summary="Readiness probe",
        response_model=Health,
    )
    async def ready() -> Health:
        """V1: process-up is ready. Stream A wires DB and model checks here on Day 3."""
        return Health(status="ok", version=__version__)

    app.include_router(sessions_routes.router)
    app.include_router(replay_routes.router)

    return app


# uvicorn entry point.
app = create_app()
