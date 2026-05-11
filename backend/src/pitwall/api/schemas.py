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

PredictorName = Literal["scipy", "xgboost"]


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
            "True if a replay was running and has been stopped; false if nothing was running."
        ),
    )
    run_id: UUID | None = None


# ---------------------------------------------------------------------------
# Snapshot schemas (mirror of RaceSnapshot / DriverState in openapi_v1.yaml).
# ---------------------------------------------------------------------------


class DriverStateOut(BaseModel):
    """Per-driver state inside a :class:`RaceSnapshotOut`."""

    driver_code: str
    team_code: str | None = None
    position: int | None = None
    gap_to_leader_ms: int | None = None
    gap_to_ahead_ms: int | None = None
    last_lap_ms: int | None = None
    compound: str | None = None
    tyre_age: int = 0
    is_in_pit: bool = False
    is_lapped: bool = False
    last_pit_lap: int | None = None
    stint_number: int = 1
    undercut_score: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Normalised undercut viability score towards the driver ahead.",
    )


class RaceSnapshotOut(BaseModel):
    """Current in-memory race state for an active replay session."""

    session_id: str
    current_lap: int
    track_status: str = "GREEN"
    track_temp_c: float | None = None
    air_temp_c: float | None = None
    humidity_pct: float | None = None
    drivers: list[DriverStateOut]
    active_predictor: PredictorName
    last_event_ts: datetime


# ---------------------------------------------------------------------------
# Degradation schemas (mirror of DegradationCurve in openapi_v1.yaml).
# ---------------------------------------------------------------------------


class DegradationCoefficients(BaseModel):
    """Quadratic coefficients: ``lap_time_ms(t) = a + b·t + c·t²``."""

    a: float
    b: float
    c: float


class DegradationSamplePoint(BaseModel):
    tyre_age: int
    lap_time_ms: int


class DegradationCurve(BaseModel):
    circuit_id: str
    compound: str
    coefficients: DegradationCoefficients
    r_squared: float | None = Field(default=None, ge=0.0, le=1.0)
    n_samples: int
    sample_points: list[DegradationSamplePoint] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Config schemas (mirror of SetPredictorRequest / SetPredictorResponse in
# openapi_v1.yaml).
# ---------------------------------------------------------------------------


class SetPredictorRequest(BaseModel):
    predictor: PredictorName


class SetPredictorResponse(BaseModel):
    active_predictor: PredictorName


# ---------------------------------------------------------------------------
# Backtest schemas (mirror of UndercutMatch / BacktestResult in
# openapi_v1.yaml).  Populated by Stream A (E9-E10).
# ---------------------------------------------------------------------------


class UndercutMatch(BaseModel):
    """One (attacker, defender) undercut event from the curated ground-truth list."""

    attacker: str = Field(..., examples=["NOR"])
    defender: str = Field(..., examples=["VER"])
    lap_alerted: int | None = Field(
        default=None, description="Lap on which the engine first emitted UNDERCUT_VIABLE."
    )
    lap_actual: int | None = Field(
        default=None, description="Lap on which the actual pit stop occurred."
    )
    was_successful: bool | None = Field(
        default=None,
        description="True if attacker finished ahead of defender after the stop exchange.",
    )


class BacktestResult(BaseModel):
    """Engine alert quality metrics against the curated known-undercut list."""

    session_id: str
    predictor: PredictorName
    precision: float = Field(..., ge=0.0, le=1.0)
    recall: float = Field(..., ge=0.0, le=1.0)
    f1: float = Field(..., ge=0.0, le=1.0)
    mean_lead_time_laps: float | None = Field(
        default=None, description="Average laps between first alert and actual stop."
    )
    mae_k1_ms: int | None = None
    mae_k3_ms: int | None = None
    mae_k5_ms: int | None = None
    true_positives: list[UndercutMatch] = Field(default_factory=list)
    false_positives: list[UndercutMatch] = Field(default_factory=list)
    false_negatives: list[UndercutMatch] = Field(default_factory=list)
