"""Runtime configuration via environment variables.

Settings are read from environment variables (and a `.env` file if
present) at process start. The shape is intentionally flat in V1; if
the surface grows we can split it into nested models without touching
call sites because everything reads through ``get_settings()``.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

PredictorName = Literal["scipy", "xgboost"]


class Settings(BaseSettings):
    """Process-wide configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Database -----------------------------------------------------
    # Stream A wires this up on Day 3; the V1 in-memory repository
    # ignores it.
    database_url: str = "postgresql://pitwall:pitwall@db:5432/pitwall"

    # --- Logging ------------------------------------------------------
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    # --- Predictor selection -----------------------------------------
    pace_predictor: PredictorName = "scipy"

    # --- ML model paths ----------------------------------------------
    # Path to the serialised XGBoost pace model. Relative paths are
    # resolved from the process working directory (repo root in dev,
    # /app in Docker). The file is only required when
    # PACE_PREDICTOR=xgboost; setting the env var without training
    # first returns 409 from POST /api/v1/config/predictor.
    xgb_model_path: str = "models/xgb_pace_v1.json"

    # --- Replay defaults ---------------------------------------------
    replay_default_session: str = "monaco_2024_R"
    replay_default_speed: float = 30.0


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton.

    Cached so every dependency that imports it sees the same instance.
    Tests that need a different configuration should clear the cache or
    use FastAPI's ``app.dependency_overrides``.
    """
    return Settings()
