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
from typing import Literal, Protocol, cast, runtime_checkable

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
    stint_number: int | None = None
    lap_in_stint: int | None = None  # tyre_age within the current stint
    lap_in_stint_ratio: float | None = None
    laps_remaining: int | None = None
    total_laps: int | None = None
    lap_number: int | None = None
    race_progress: float | None = None
    fuel_proxy: float | None = None
    position: int | None = None
    gap_to_ahead_ms: int | None = None
    gap_to_leader_ms: int | None = None
    is_in_traffic: bool | None = None
    dirty_air_proxy_ms: int | None = None
    reference_lap_time_ms: float | None = None
    driver_pace_offset_ms: float | None = None
    driver_pace_offset_missing: bool | None = None

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
        if self.stint_number is not None and self.stint_number < 1:
            raise ValueError(f"stint_number must be >= 1, got {self.stint_number}")
        if self.total_laps is not None and self.total_laps <= 0:
            raise ValueError(f"total_laps must be > 0, got {self.total_laps}")
        if self.laps_remaining is not None and self.laps_remaining < 0:
            raise ValueError(f"laps_remaining must be >= 0, got {self.laps_remaining}")
        if self.humidity_pct is not None and not 0.0 <= self.humidity_pct <= 100.0:
            raise ValueError(f"humidity_pct must be in [0, 100], got {self.humidity_pct}")
        if self.lap_number is not None and self.lap_number < 0:
            raise ValueError(f"lap_number must be >= 0, got {self.lap_number}")
        if self.position is not None and self.position < 1:
            raise ValueError(f"position must be >= 1, got {self.position}")
        if self.gap_to_ahead_ms is not None and self.gap_to_ahead_ms < 0:
            raise ValueError(f"gap_to_ahead_ms must be >= 0, got {self.gap_to_ahead_ms}")
        if self.gap_to_leader_ms is not None and self.gap_to_leader_ms < 0:
            raise ValueError(f"gap_to_leader_ms must be >= 0, got {self.gap_to_leader_ms}")
        if self.dirty_air_proxy_ms is not None and self.dirty_air_proxy_ms < 0:
            raise ValueError(
                f"dirty_air_proxy_ms must be >= 0, got {self.dirty_air_proxy_ms}"
            )
        if self.reference_lap_time_ms is not None and self.reference_lap_time_ms <= 0:
            raise ValueError(
                f"reference_lap_time_ms must be > 0, got {self.reference_lap_time_ms}"
            )
        for name, value in (
            ("lap_in_stint_ratio", self.lap_in_stint_ratio),
            ("race_progress", self.race_progress),
            ("fuel_proxy", self.fuel_proxy),
        ):
            if value is not None and not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in [0, 1], got {value}")


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
            raise ValueError(f"predicted_lap_time_ms must be > 0, got {self.predicted_lap_time_ms}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be in [0.0, 1.0], got {self.confidence}")


class UnsupportedContextError(LookupError):
    """Raised by a predictor when no prediction can be produced for the
    given context — typically when no fitted model exists for the
    ``(circuit_id, compound)`` cell.

    Inherits from :class:`LookupError` so callers can catch the broader
    type without needing to import this class.
    """


COLD_TYRE_PENALTIES_MS: tuple[int, ...] = (800, 300, 0)
"""Out-lap and warm-up lap time penalties for a driver on fresh tyres.

Index 0 (j=1): out-lap  → +800 ms
Index 1 (j=2): warm-up  → +300 ms
Index 2+ (j≥3): no penalty

Source: master plan §6.5.  Calibrated from 2022-2024 FastF1 pit-out laps;
the penalty decays to zero after two laps on the new compound.
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


def project_pace(
    driver_code: str,
    circuit_id: str,
    compound: str,
    start_age: int,
    k: int,
    predictor: PacePredictor,
    *,
    apply_cold_tyre_penalty: bool = False,
    cold_tyre_penalties: tuple[int, ...] | None = None,
    team_code: str | None = None,
    track_temp_c: float | None = None,
    air_temp_c: float | None = None,
    humidity_pct: float | None = None,
    stint_position: int | None = None,
    stint_number: int | None = None,
    lap_in_stint: int | None = None,
    lap_in_stint_ratio: float | None = None,
    laps_remaining: int | None = None,
    total_laps: int | None = None,
    lap_number: int | None = None,
    race_progress: float | None = None,
    fuel_proxy: float | None = None,
    position: int | None = None,
    gap_to_ahead_ms: int | None = None,
    gap_to_leader_ms: int | None = None,
    is_in_traffic: bool | None = None,
    dirty_air_proxy_ms: int | None = None,
    reference_lap_time_ms: float | None = None,
    driver_pace_offset_ms: float | None = None,
    driver_pace_offset_missing: bool | None = None,
) -> list[int]:
    """Project *k* lap times (ms) forward from tyre age *start_age*.

    For the **defender** staying out on worn tyres::

        project_pace(defender.driver_code, circuit_id, defender.compound,
                     start_age=defender.tyre_age, k=5, predictor,
                     apply_cold_tyre_penalty=False)

    For the **attacker** on fresh tyres after a pit stop::

        project_pace(attacker.driver_code, circuit_id, next_compound,
                     start_age=0, k=5, predictor,
                     apply_cold_tyre_penalty=True)

    The out-lap and warm-up lap penalties are added only when
    *apply_cold_tyre_penalty* is ``True``.  The default penalties come from
    :data:`COLD_TYRE_PENALTIES_MS`.  Pass *cold_tyre_penalties* to override
    with values calibrated from historical data (see
    :func:`~pitwall.engine.calibration.calibrate_cold_tyre_penalties`).

    Args:
        cold_tyre_penalties: Override the module-level
            :data:`COLD_TYRE_PENALTIES_MS`.  ``None`` (default) uses the
            module constant.  Stream A can pass empirically calibrated values
            from ``make compute-cold-tyre-penalties``.

    Returns:
        A list of *k* integers; element ``j-1`` is the projected lap time
        at ``tyre_age = start_age + j``.

    Raises:
        UnsupportedContextError: if the predictor has no model for
            ``(circuit_id, compound)``.
    """
    penalties = COLD_TYRE_PENALTIES_MS if cold_tyre_penalties is None else cold_tyre_penalties
    times: list[int] = []
    for j in range(1, k + 1):
        projected_lap_number = lap_number + j if lap_number is not None else None
        projected_lap_in_stint = lap_in_stint + j if lap_in_stint is not None else None
        projected_laps_remaining = (
            max(0, laps_remaining - j) if laps_remaining is not None else None
        )
        ctx = PaceContext(
            driver_code=driver_code,
            circuit_id=circuit_id,
            compound=cast(Compound, compound),
            tyre_age=start_age + j,
            team_code=team_code,
            track_temp_c=track_temp_c,
            air_temp_c=air_temp_c,
            humidity_pct=humidity_pct,
            stint_position=stint_position,
            stint_number=stint_number,
            lap_in_stint=projected_lap_in_stint,
            lap_in_stint_ratio=lap_in_stint_ratio,
            laps_remaining=projected_laps_remaining,
            total_laps=total_laps,
            lap_number=projected_lap_number,
            race_progress=race_progress,
            fuel_proxy=fuel_proxy,
            position=position,
            gap_to_ahead_ms=gap_to_ahead_ms,
            gap_to_leader_ms=gap_to_leader_ms,
            is_in_traffic=is_in_traffic,
            dirty_air_proxy_ms=dirty_air_proxy_ms,
            reference_lap_time_ms=reference_lap_time_ms,
            driver_pace_offset_ms=driver_pace_offset_ms,
            driver_pace_offset_missing=driver_pace_offset_missing,
        )
        lap_ms = predictor.predict(ctx).predicted_lap_time_ms
        if apply_cold_tyre_penalty:
            penalty_idx = j - 1
            if penalty_idx < len(penalties):
                lap_ms += penalties[penalty_idx]
        times.append(lap_ms)
    return times
