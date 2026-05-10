"""Pydantic schemas mirroring the OpenAPI contract.

Field names match ``docs/interfaces/openapi_v1.yaml`` exactly. CI runs
``backend/tests/contract/test_openapi_export.py`` to ensure this
mirror stays in sync with the static spec.
"""

from __future__ import annotations

from datetime import date

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
