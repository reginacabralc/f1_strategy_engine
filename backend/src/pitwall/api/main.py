"""FastAPI application factory.

Run locally with::

    uvicorn pitwall.api.main:app --reload --port 8000

The module-level ``app`` is the artifact uvicorn imports. Tests build
their own copy via :func:`create_app` to keep a clean dependency
override surface.
"""

from __future__ import annotations

from fastapi import FastAPI

from pitwall import __version__
from pitwall.api.routes import sessions as sessions_routes
from pitwall.api.schemas import Health
from pitwall.core.config import get_settings
from pitwall.core.logging import configure_logging


def create_app() -> FastAPI:
    """Build a fresh FastAPI app instance.

    Side effects:
      - Configures process-wide structured logging.

    Returns:
        A FastAPI app with health/readiness probes and the session
        catalogue route mounted. Day-3+ routes (replay, snapshot,
        degradation, backtest, config) will be added here.
    """
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="PitWall API",
        version=__version__,
        description=(
            "Real-time F1 undercut detection engine. "
            "WebSocket channel documented in "
            "`docs/interfaces/websocket_messages.md`."
        ),
    )

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
        """V1: process-up is ready. Stream A wires the real DB and
        model checks here on Day 3 once the SQL repository lands."""
        return Health(status="ok", version=__version__)

    app.include_router(sessions_routes.router)

    return app


# uvicorn entry point.
app = create_app()
