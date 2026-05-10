"""Pace prediction interface.

This module defines the :class:`PacePredictor` Protocol and the supporting
data structures used by the undercut engine to project a driver's lap
time forward in time.

Two implementations are expected to satisfy this protocol:

- :class:`pitwall.degradation.predictor.ScipyPredictor` — quadratic
  ``a + b*tyre_age + c*tyre_age**2`` curve fit per ``(circuit, compound)``
  cell, used as the V1 baseline.
- :class:`pitwall.ml.predictor.XGBoostPredictor` — gradient-boosted tree
  model, the V1 ML deliverable (see ADR 0004).

The undercut engine consumes this protocol via dependency injection and
switches between implementations through the ``PACE_PREDICTOR`` env var.

Stream A owns the contract; Stream B consumes it from
:mod:`pitwall.engine.undercut`. Any change here must be reviewed by both
streams (see ``AGENTS.md``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

Compound = Literal["SOFT", "MEDIUM", "HARD", "INTER", "WET"]
"""Tyre compound identifier as reported by FastF1 and OpenF1.

Wet-weather compounds (``INTER``, ``WET``) are accepted by the type but
the V1 engine will short-circuit with ``UNDERCUT_DISABLED_RAIN`` rather
than computing a prediction (see quanta 02 and 04).
"""


@dataclass(frozen=True, slots=True)
class PaceContext:
    """Inputs for predicting a single lap's time.

    The four required fields fully specify a baseline prediction. The
    optional fields are consumed by :class:`XGBoostPredictor` (and any
    future model) and are ignored by :class:`ScipyPredictor`.

    ``tyre_age`` is the **absolute** age of the tyre on the lap being
    predicted, not a delta from the current state. Callers projecting
    ``k`` laps ahead must pass ``current_tyre_age + k``.

    The dataclass is frozen and slotted to keep instances cheap to
    create on the per-pair-per-tick hot path of the engine. See
    quanta 04 for the call pattern.
    """

    # --- Required -----------------------------------------------------
    driver_code: str
    circuit_id: str
    compound: Compound
    tyre_age: int

    # --- Optional (used by XGBoostPredictor) --------------------------
    team_code: str | None = None
    track_temp_c: float | None = None
    air_temp_c: float | None = None
    humidity_pct: float | None = None  # FastF1 reports humidity as 0..100
    stint_position: int | None = None  # 1 = first stint, 2 = second, ...
    lap_in_stint: int | None = None  # tyre_age within the current stint
    laps_remaining: int | None = None
    total_laps: int | None = None

    def __post_init__(self) -> None:
        if not self.driver_code:
            raise ValueError("driver_code must be a non-empty string")
        if not self.circuit_id:
            raise ValueError("circuit_id must be a non-empty string")
        if self.tyre_age < 0:
            raise ValueError(f"tyre_age must be >= 0, got {self.tyre_age}")
        if self.lap_in_stint is not None and self.lap_in_stint < 0:
            raise ValueError(f"lap_in_stint must be >= 0, got {self.lap_in_stint}")
        if self.stint_position is not None and self.stint_position < 1:
            raise ValueError(f"stint_position must be >= 1, got {self.stint_position}")
        if self.total_laps is not None and self.total_laps <= 0:
            raise ValueError(f"total_laps must be > 0, got {self.total_laps}")
        if self.laps_remaining is not None and self.laps_remaining < 0:
            raise ValueError(f"laps_remaining must be >= 0, got {self.laps_remaining}")
        if self.humidity_pct is not None and not 0.0 <= self.humidity_pct <= 100.0:
            raise ValueError(
                f"humidity_pct must be in [0, 100], got {self.humidity_pct}"
            )


@dataclass(frozen=True, slots=True)
class PacePrediction:
    """A predicted lap time with a confidence score."""

    predicted_lap_time_ms: int
    """Predicted lap time in whole milliseconds. Must be > 0."""

    confidence: float
    """Confidence in ``[0.0, 1.0]``. For :class:`ScipyPredictor` this is
    the R^2 of the underlying fit; for :class:`XGBoostPredictor` it is a
    proxy derived from training metrics. Callers in
    :mod:`pitwall.engine.undercut` will not emit alerts unless
    confidence exceeds 0.5 (see quanta 04)."""

    def __post_init__(self) -> None:
        if self.predicted_lap_time_ms <= 0:
            raise ValueError(
                f"predicted_lap_time_ms must be > 0, got {self.predicted_lap_time_ms}"
            )
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                f"confidence must be in [0.0, 1.0], got {self.confidence}"
            )


class UnsupportedContextError(LookupError):
    """Raised by a predictor when no prediction can be produced for the
    given context — typically when no fitted model exists for the
    ``(circuit_id, compound)`` cell.

    Inherits from :class:`LookupError` so callers can catch the broader
    type without needing to import this class.
    """


@runtime_checkable
class PacePredictor(Protocol):
    """Predicts a driver's lap time given a :class:`PaceContext`.

    Implementations must be:

    - **Stateless after construction.** The undercut engine creates a
      single instance at startup and reuses it across the whole replay.
    - **Thread- and async-safe.** Multiple calls may be in flight from
      the engine loop and from ``/api/v1/degradation`` handlers
      simultaneously.
    - **Fast.** Performance budget per ``predict()`` call: < 100 µs p95
      for :class:`ScipyPredictor`, < 5 ms p95 for
      :class:`XGBoostPredictor`. See ``docs/architecture.md`` § 8.

    Implementations are expected to handle missing optional fields in
    :class:`PaceContext` gracefully (e.g. XGBoost may impute or fall
    back to a global prior).
    """

    def predict(self, ctx: PaceContext) -> PacePrediction:
        """Predict the lap time for the given context.

        Raises:
            UnsupportedContextError: if no prediction can be produced
                (e.g. no fitted coefficients for this circuit/compound).
        """
        ...

    def is_available(self, circuit_id: str, compound: Compound) -> bool:
        """Whether ``predict()`` can succeed for this ``(circuit, compound)``.

        Engines should call this first and either fall back to another
        predictor or skip the pair when ``False``. This method must
        never raise.
        """
        ...
