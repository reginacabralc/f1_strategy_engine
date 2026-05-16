"""Undercut-viability scoring - master plan §6.4-6.8.

The sole public entry point is :func:`evaluate_undercut`.  It takes the
current :class:`~pitwall.engine.state.RaceState`, an attacker/defender
pair from :func:`~pitwall.engine.state.compute_relevant_pairs`, and the
active :class:`~pitwall.engine.projection.PacePredictor`.  It returns an
:class:`UndercutDecision` that encapsulates the score, confidence, and
whether an alert should be broadcast.

Math (§6.4-6.7)
----------------

1. Project the defender's lap times k=1..K_MAX laps ahead (on worn tyres).
2. Project the attacker's lap times k=1..K_MAX laps ahead (on fresh tyres,
   with cold-tyre penalty on laps 1 and 2).
3. Sum the per-lap gains: ``gap_recuperable = Σ(defender_k - attacker_k)``.
4. Score: ``clamp((gap_recuperable - pit_loss - gap_actual - MARGIN) / pit_loss, 0, 1)``
5. Confidence: ``min(R²_defender, R²_attacker)`` — both models must be reliable.
6. Alert if ``score > 0.4 AND confidence > 0.5`` (§6.8).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from pitwall.engine.pit_loss import DEFAULT_PIT_LOSS_MS
from pitwall.engine.projection import (
    Compound,
    PaceContext,
    PacePredictor,
    UnsupportedContextError,
    project_pace,
)
from pitwall.engine.state import DriverState, RaceState

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCORE_THRESHOLD: float = 0.4
"""Minimum score for an ``UNDERCUT_VIABLE`` alert (§6.8)."""

CONFIDENCE_THRESHOLD: float = 0.5
"""Minimum confidence for any alert (§6.8). Below this the model fit is
too unreliable to trust."""

K_MAX: int = 5
"""Laps ahead to project when computing cumulative gap recovery (§6.6)."""

UNDERCUT_MARGIN_MS: int = 500
"""Safety margin added to the break-even calculation (§6.6 threshold δ).

Even if gap_recuperable == pit_loss + gap_actual the undercut is too
marginal to call; the attacker needs to recoup an extra 0.5 s on top."""

# Heuristic mapping: next compound to pit for when current is known.
_NEXT_COMPOUND: dict[str, str] = {
    "SOFT": "MEDIUM",
    "MEDIUM": "HARD",
    "HARD": "MEDIUM",
    "INTER": "INTER",
    "WET": "WET",
}
_DEFAULT_NEXT_COMPOUND = "MEDIUM"

# Minimum attacker laps for full-quality projection (§6.7 data_quality_factor).
_FULL_QUALITY_LAPS: int = 8
# Gap threshold below which timing noise from traffic reduces confidence (§6.9).
_TRAFFIC_GAP_MS: int = 1_500
# Confidence penalty applied when gap is below traffic threshold.
_TRAFFIC_CONFIDENCE_PENALTY: float = 0.2


def _data_quality_factor(attacker: DriverState) -> float:
    """Compute the data-quality multiplier for confidence (§6.7).

    Returns a value in ``[0.0, 1.0]`` that scales down the raw R² confidence
    when the projection is less reliable than usual:

    - **Short stint**: attacker has fewer than :data:`_FULL_QUALITY_LAPS` laps
      on the current compound.  Factor = ``laps_in_stint / _FULL_QUALITY_LAPS``,
      giving a linear ramp from ``0.375`` (3 laps) to ``1.0`` (8+ laps).
    - **Traffic**: ``gap_to_ahead_ms < 1 500 ms``.  Lap-timing data for a car
      stuck in dirty air is noisier; subtract :data:`_TRAFFIC_CONFIDENCE_PENALTY`.
    """
    factor = 1.0

    if attacker.laps_in_stint < _FULL_QUALITY_LAPS:
        factor = attacker.laps_in_stint / _FULL_QUALITY_LAPS

    if attacker.gap_to_ahead_ms is not None and attacker.gap_to_ahead_ms < _TRAFFIC_GAP_MS:
        factor -= _TRAFFIC_CONFIDENCE_PENALTY

    return max(0.0, min(1.0, factor))


def _base_context_kwargs(
    state: RaceState,
    driver: DriverState,
    compound: str,
    *,
    start_lap_in_stint: int | None = None,
    stint_number: int | None = None,
) -> dict[str, Any]:
    current_lap = state.current_lap or None
    total_laps = state.total_laps
    laps_remaining = (
        max(0, total_laps - state.current_lap)
        if total_laps is not None and state.current_lap
        else None
    )
    gap_to_ahead_ms = driver.gap_to_ahead_ms
    return {
        "team_code": driver.team_code,
        "track_temp_c": state.track_temp_c,
        "air_temp_c": state.air_temp_c,
        "humidity_pct": state.humidity_pct,
        "stint_position": stint_number or driver.stint_number,
        "stint_number": stint_number or driver.stint_number,
        "lap_in_stint": start_lap_in_stint
        if start_lap_in_stint is not None
        else driver.laps_in_stint,
        "laps_remaining": laps_remaining,
        "total_laps": total_laps,
        "lap_number": current_lap,
        "position": driver.position,
        "gap_to_ahead_ms": gap_to_ahead_ms,
        "gap_to_leader_ms": driver.gap_to_leader_ms,
        "is_in_traffic": gap_to_ahead_ms is not None and gap_to_ahead_ms < _TRAFFIC_GAP_MS,
        "dirty_air_proxy_ms": max(0, 2_000 - gap_to_ahead_ms)
        if gap_to_ahead_ms is not None
        else 0,
        "reference_lap_time_ms": state.reference_lap_time_ms(compound),
        "driver_pace_offset_ms": None,
        "driver_pace_offset_missing": True,
    }


def _context_for_driver(
    state: RaceState,
    driver: DriverState,
    compound: str,
    tyre_age: int,
    *,
    start_lap_in_stint: int | None = None,
    stint_number: int | None = None,
) -> PaceContext:
    return PaceContext(
        driver_code=driver.driver_code,
        circuit_id=state.circuit_id or "",
        compound=cast(Compound, compound),
        tyre_age=tyre_age,
        **_base_context_kwargs(
            state,
            driver,
            compound,
            start_lap_in_stint=start_lap_in_stint,
            stint_number=stint_number,
        ),
    )


# ---------------------------------------------------------------------------
# Decision
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class UndercutDecision:
    """The output of :func:`evaluate_undercut` for one (attacker, defender) pair."""

    attacker_code: str
    defender_code: str

    alert_type: str
    """One of the ``AlertType`` enum values defined in ``openapi_v1.yaml``.

    ``UNDERCUT_VIABLE`` — conditions met, alert should be broadcast.
    ``INSUFFICIENT_DATA`` — not enough data to evaluate (laps_in_stint < 3,
    missing gap, or no predictor coefficients).
    """

    score: float
    """Normalised viability score in ``[0, 1]``.  0 means the undercut barely
    breaks even (after accounting for pit loss and current gap); 1 means the
    attacker recovers double the pit-loss time in the projection window."""

    confidence: float
    """Model reliability in ``[0, 1]`` — ``min(R²_defender, R²_attacker)``."""

    estimated_gain_ms: int
    """``gap_recuperable - pit_loss_ms``: net time gained over the defender
    after paying the pit-stop cost.  Positive → attacker comes out ahead."""

    pit_loss_ms: int
    gap_actual_ms: int | None

    should_alert: bool
    """``True`` when the alert should be broadcast to WebSocket clients."""


# ---------------------------------------------------------------------------
# Public function
# ---------------------------------------------------------------------------


def evaluate_undercut(
    state: RaceState,
    attacker: DriverState,
    defender: DriverState,
    predictor: PacePredictor,
    pit_loss_ms: int = DEFAULT_PIT_LOSS_MS,
) -> UndercutDecision:
    """Compute the undercut viability for one (attacker, defender) pair.

    Returns an :class:`UndercutDecision` in all cases; the caller should
    check :attr:`UndercutDecision.should_alert` before broadcasting.

    Args:
        state:       Current :class:`~pitwall.engine.state.RaceState`.
        attacker:    Driver behind who might benefit from pitting early.
        defender:    Driver ahead who the attacker wants to undercut.
        predictor:   Active :class:`~pitwall.engine.projection.PacePredictor`.
        pit_loss_ms: Expected time loss during the pit stop.
    """
    _base = dict(
        attacker_code=attacker.driver_code,
        defender_code=defender.driver_code,
        pit_loss_ms=pit_loss_ms,
        gap_actual_ms=attacker.gap_to_ahead_ms,
    )

    def _insufficient() -> UndercutDecision:
        return UndercutDecision(
            **_base,  # type: ignore[arg-type]
            alert_type="INSUFFICIENT_DATA",
            score=0.0,
            confidence=0.0,
            estimated_gain_ms=0,
            should_alert=False,
        )

    # Guard: rain / intermediate compounds — undercut is not calculable (§6.9).
    _atk_compound = (attacker.compound or "").upper()
    _def_compound = (defender.compound or "").upper()
    if _atk_compound in ("INTER", "WET") or _def_compound in ("INTER", "WET"):
        return UndercutDecision(
            **_base,  # type: ignore[arg-type]
            alert_type="UNDERCUT_DISABLED_RAIN",
            score=0.0,
            confidence=0.0,
            estimated_gain_ms=0,
            should_alert=False,
        )

    # Guard: defender just pitted — they already have fresh tyres, undercut
    # is moot and the projection would be misleading (§6.9).
    if defender.laps_in_stint < 2:
        return _insufficient()

    # Guard: must have at least 3 laps of stint data to project reliably (§S6).
    if attacker.laps_in_stint < 3:
        return _insufficient()

    # Guard: need a known gap to compute the break-even point.
    gap_actual_ms = attacker.gap_to_ahead_ms
    if gap_actual_ms is None:
        return _insufficient()

    def_compound = defender.compound or _DEFAULT_NEXT_COMPOUND
    next_compound = _NEXT_COMPOUND.get((attacker.compound or "").upper(), _DEFAULT_NEXT_COMPOUND)
    circuit_id = state.circuit_id or ""

    try:
        # Confidence: one representative call per (circuit, compound) cell.
        # Sample at the defender's *current* tyre age — the start of the projection
        # window. (For ScipyPredictor R² is constant, but future predictors may
        # return tyre-age-dependent confidence.)
        conf_def = predictor.predict(
            _context_for_driver(state, defender, def_compound, max(1, defender.tyre_age))
        ).confidence
        conf_atk = predictor.predict(
            _context_for_driver(
                state,
                attacker,
                next_compound,
                1,
                start_lap_in_stint=1,
                stint_number=attacker.stint_number + 1,
            )
        ).confidence
        confidence = min(conf_def, conf_atk) * _data_quality_factor(attacker)

        # Pace projections (§6.4 defender, §6.5 attacker).
        defender_kwargs = _base_context_kwargs(state, defender, def_compound)
        attacker_kwargs = _base_context_kwargs(
            state,
            attacker,
            next_compound,
            start_lap_in_stint=0,
            stint_number=attacker.stint_number + 1,
        )
        defender_laps = project_pace(
            defender.driver_code,
            circuit_id,
            def_compound,
            defender.tyre_age,
            K_MAX,
            predictor,
            apply_cold_tyre_penalty=False,
            **defender_kwargs,
        )
        attacker_laps = project_pace(
            attacker.driver_code,
            circuit_id,
            next_compound,
            0,
            K_MAX,
            predictor,
            apply_cold_tyre_penalty=True,
            **attacker_kwargs,
        )
    except UnsupportedContextError:
        return _insufficient()

    # Cumulative gap recovery over the projection window (§6.6).
    gap_recuperable_ms = sum(d - a for d, a in zip(defender_laps, attacker_laps, strict=True))
    estimated_gain_ms = gap_recuperable_ms - pit_loss_ms

    # Normalised score (§6.7).  The MARGIN ensures marginal undercuts don't
    # trigger an alert.  Guard against pit_loss_ms=0 (shouldn't happen in
    # practice but prevents ZeroDivisionError from a misconfigured table).
    raw_score = (
        gap_recuperable_ms - pit_loss_ms - gap_actual_ms - UNDERCUT_MARGIN_MS
    ) / max(1, pit_loss_ms)
    score = max(0.0, min(1.0, raw_score))

    should_alert = score > SCORE_THRESHOLD and confidence > CONFIDENCE_THRESHOLD

    return UndercutDecision(
        **_base,  # type: ignore[arg-type]
        alert_type="UNDERCUT_VIABLE",
        score=score,
        confidence=confidence,
        estimated_gain_ms=estimated_gain_ms,
        should_alert=should_alert,
    )
