"""FastAPI application factory.

Run locally with::

    uvicorn pitwall.api.main:app --reload --port 8000

The module-level ``app`` is the artifact uvicorn imports. Tests build
their own copy via :func:`create_app` to keep a clean dependency
override surface.

Startup order (inside ``create_app``)
--------------------------------------
All stateful objects are created **synchronously** and stored on
``app.state`` before the lifespan runs.  This means ``TestClient`` can
access them even without a ``with`` context manager.  The lifespan then:

1. Tries to load the :class:`~pitwall.degradation.predictor.ScipyPredictor`
   from the DB (falls back to an empty predictor if the DB is unavailable).
2. Starts the :class:`~pitwall.engine.loop.EngineLoop` background task.
3. On shutdown: stops the loop and the active replay (if any).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from pitwall import __version__
from pitwall.api.connections import ConnectionManager
from pitwall.api.routes import replay as replay_routes
from pitwall.api.routes import sessions as sessions_routes
from pitwall.api.schemas import Health
from pitwall.api.ws import router as ws_router
from pitwall.core.config import get_settings
from pitwall.core.logging import configure_logging
from pitwall.core.topics import Topics
from pitwall.engine.loop import EngineLoop
from pitwall.engine.projection import PacePredictor
from pitwall.engine.replay_manager import ReplayManager


def _build_predictor() -> PacePredictor:
    """Try to load ScipyPredictor from DB; fall back to empty on failure."""
    from pitwall.degradation.predictor import ScipyPredictor

    try:
        from pitwall.db.engine import create_db_engine

        return ScipyPredictor.from_engine(create_db_engine())
    except Exception:
        return ScipyPredictor([])


def create_app() -> FastAPI:
    """Build a fresh FastAPI application instance.

    Each call creates new stateful objects so ``TestClient(create_app())``
    calls are fully isolated.
    """
    settings = get_settings()
    configure_logging(settings.log_level)

    # --- Stateful singletons (created synchronously for test-client access) ---
    topics = Topics()
    replay_manager = ReplayManager(topics)
    connection_manager = ConnectionManager()
    predictor = _build_predictor()
    engine_loop = EngineLoop(
        topics,
        connection_manager,
        predictor,
        {},  # pit_loss_table — Stream A populates Day 6
        settings.pace_predictor,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Try to reload a fresh predictor from DB (if available at startup).
        # This is a no-op when DATABASE_URL is unset (typical in tests).
        try:
            from pitwall.db.engine import create_db_engine
            from pitwall.degradation.predictor import ScipyPredictor

            engine_loop.set_predictor(
                ScipyPredictor.from_engine(create_db_engine()),
                settings.pace_predictor,
            )
        except Exception:
            pass  # keep the predictor we already have

        await engine_loop.start()
        yield
        await engine_loop.stop()
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

    # Store on app.state so dependency providers can reach them.
    app.state.topics = topics
    app.state.replay_manager = replay_manager
    app.state.connection_manager = connection_manager
    app.state.engine_loop = engine_loop

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
        """V1: process-up is ready. Stream A wires DB/model checks here."""
        return Health(status="ok", version=__version__)

    app.include_router(sessions_routes.router)
    app.include_router(replay_routes.router)
    app.include_router(ws_router)

    return app


# uvicorn entry point.
app = create_app()
