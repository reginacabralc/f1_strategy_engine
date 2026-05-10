"""Pydantic schemas mirroring the OpenAPI contract.

Field names match ``docs/interfaces/openapi_v1.yaml`` exactly. CI runs
``backend/tests/contract/test_openapi_export.py`` to ensure this
mirror stays in sync with the static spec.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class Health(BaseModel):
    status: str = "ok"
    version: str = Field(..., examples=["0.1.0"])


class SessionSummary(BaseModel):
    session_id: str = Field(..., examples=["monaco_2024_R"])
    circuit_id: str = Field(..., examples=["monaco"])
    season: int = Field(..., examples=[2024])
    round_number: int = Field(..., examples=[8])
    date: date
    total_laps: int | None = Field(default=None, examples=[78])


# ---------------------------------------------------------------------------
# Replay schemas (mirror of openapi_v1.yaml ReplayStartRequest / ReplayRun /
# ReplayStopResponse).
# ---------------------------------------------------------------------------


class ReplayStartRequest(BaseModel):
    session_id: str = Field(..., examples=["monaco_2024_R"])
    speed_factor: float = Field(
        default=30.0,
        ge=1.0,
        le=1000.0,
        description="Wall-clock acceleration factor. 1 = real time, 1000 = test mode.",
        examples=[30.0],
    )


class ReplayRun(BaseModel):
    run_id: UUID
    session_id: str
    speed_factor: float
    started_at: datetime
    pace_predictor: Literal["scipy", "xgboost"]


class ReplayStopResponse(BaseModel):
    stopped: bool = Field(
        ...,
        description=(
            "True if a replay was running and has been stopped; "
            "false if nothing was running."
        ),
    )
    run_id: UUID | None = None
