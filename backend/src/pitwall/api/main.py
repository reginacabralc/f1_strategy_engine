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

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from pitwall import __version__
from pitwall.api.connections import ConnectionManager
from pitwall.api.routes import backtest as backtest_routes
from pitwall.api.routes import causal as causal_routes
from pitwall.api.routes import config as config_routes
from pitwall.api.routes import degradation as degradation_routes
from pitwall.api.routes import replay as replay_routes
from pitwall.api.routes import sessions as sessions_routes
from pitwall.api.schemas import Health
from pitwall.api.ws import router as ws_router
from pitwall.core.config import get_settings
from pitwall.core.logging import configure_logging, get_logger
from pitwall.core.topics import Topics
from pitwall.db.engine import create_db_engine
from pitwall.engine.loop import EngineLoop
from pitwall.engine.pit_loss import PitLossTable
from pitwall.engine.projection import PacePredictor
from pitwall.engine.replay_manager import ReplayManager
from pitwall.pit_loss.estimation import load_pit_loss_table


def _build_predictor() -> PacePredictor:
    """Try to load ScipyPredictor from DB; fall back to empty on failure."""
    from pitwall.degradation.predictor import ScipyPredictor

    try:
        return ScipyPredictor.from_engine(create_db_engine())
    except Exception:
        return ScipyPredictor([])


def _build_pit_loss_table() -> PitLossTable:
    """Try to load Stream A pit-loss estimates from DB; fall back to empty."""
    try:
        with create_db_engine().connect() as connection:
            return load_pit_loss_table(connection)
    except Exception:
        return {}


_log = get_logger(__name__)


def _database_is_ready() -> bool:
    """Return whether the configured DB accepts a simple query."""
    try:
        with create_db_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        return False
    return True


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
    pit_loss_table = _build_pit_loss_table()
    engine_loop = EngineLoop(
        topics,
        connection_manager,
        predictor,
        pit_loss_table,
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
            engine_loop.set_pit_loss_table(_build_pit_loss_table())
        except Exception:
            pass  # keep the predictor we already have

        _log.info(
            "pitwall_startup",
            version=__version__,
            pace_predictor=settings.pace_predictor,
        )
        await engine_loop.start()
        yield
        await engine_loop.stop()
        await replay_manager.stop()
        _log.info("pitwall_shutdown")

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
        """Return 200 only when the DB-backed runtime can serve demo data."""
        if not _database_is_ready():
            raise HTTPException(status_code=503, detail="Database is not ready.")
        return Health(status="ok", version=__version__)

    app.include_router(sessions_routes.router)
    app.include_router(replay_routes.router)
    app.include_router(degradation_routes.router)
    app.include_router(config_routes.router)
    app.include_router(backtest_routes.router)
    app.include_router(causal_routes.router)
    app.include_router(ws_router)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        _log.exception("unhandled_exception", path=request.url.path, exc_info=exc)
        return JSONResponse(status_code=500, content={"detail": "Internal server error."})

    return app


# uvicorn entry point.
app = create_app()
