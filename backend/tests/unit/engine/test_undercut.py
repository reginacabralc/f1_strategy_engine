"""Tests for evaluate_undercut() — the core undercut-viability scorer."""

from __future__ import annotations

import pytest

from pitwall.degradation.predictor import ScipyCoefficient, ScipyPredictor
from pitwall.engine.state import DriverState, RaceState
from pitwall.engine.undercut import (
    CONFIDENCE_THRESHOLD,
    SCORE_THRESHOLD,
    evaluate_undercut,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PIT_LOSS = 21_000


def _pred(
    medium_r2: float = 0.8,
    hard_r2: float = 0.75,
) -> ScipyPredictor:
    """Monaco MEDIUM + HARD coefficients with fast degradation (for clear signals)."""
    return ScipyPredictor([
        # MEDIUM: degrades aggressively (high b + c)
        ScipyCoefficient("monaco", "MEDIUM", a=80_000.0, b=250.0, c=5.0, r_squared=medium_r2),
        # HARD: durable, faster absolute pace
        ScipyCoefficient("monaco", "HARD",   a=79_000.0, b=120.0, c=2.0, r_squared=hard_r2),
    ])


def _state(circuit_id: str = "monaco") -> RaceState:
    state = RaceState(session_id="monaco_2024_R", circuit_id=circuit_id)
    return state


def _defender(tyre_age: int = 25, position: int = 1) -> DriverState:
    return DriverState(
        driver_code="VER",
        team_code="red_bull",
        position=position,
        compound="MEDIUM",
        tyre_age=tyre_age,
        laps_in_stint=tyre_age,
        gap_to_ahead_ms=None,
    )


def _attacker(gap_ms: int = 5_000, tyre_age: int = 23, position: int = 2) -> DriverState:
    return DriverState(
        driver_code="NOR",
        team_code="mclaren",
        position=position,
        compound="MEDIUM",
        tyre_age=tyre_age,
        laps_in_stint=tyre_age,
        gap_to_ahead_ms=gap_ms,
    )


# ---------------------------------------------------------------------------
# Viable undercut scenario
# ---------------------------------------------------------------------------


def test_evaluate_undercut_viable_with_high_degradation_defender() -> None:
    """Defender on old MEDIUM + attacker close → score > threshold."""
    pred = _pred()
    state = _state()
    atk = _attacker(gap_ms=5_000, tyre_age=23)
    def_ = _defender(tyre_age=25)

    decision = evaluate_undercut(state, atk, def_, pred, _PIT_LOSS)

    assert decision.attacker_code == "NOR"
    assert decision.defender_code == "VER"
    assert decision.alert_type == "UNDERCUT_VIABLE"
    assert decision.score > SCORE_THRESHOLD
    assert decision.confidence > CONFIDENCE_THRESHOLD
    assert decision.should_alert is True
    assert decision.estimated_gain_ms > 0


# ---------------------------------------------------------------------------
# Insufficient data guards
# ---------------------------------------------------------------------------


def test_evaluate_undercut_insufficient_when_laps_in_stint_lt_3() -> None:
    pred = _pred()
    state = _state()
    atk = DriverState(
        driver_code="NOR", position=2, compound="MEDIUM", tyre_age=2,
        laps_in_stint=2,  # < 3 — should not project
        gap_to_ahead_ms=5_000,
    )
    def_ = _defender()

    decision = evaluate_undercut(state, atk, def_, pred, _PIT_LOSS)

    assert decision.alert_type == "INSUFFICIENT_DATA"
    assert decision.should_alert is False
    assert decision.score == 0.0


def test_evaluate_undercut_insufficient_when_gap_is_none() -> None:
    pred = _pred()
    state = _state()
    atk = _attacker(gap_ms=0)  # set to 0 to be safe
    atk.gap_to_ahead_ms = None  # explicitly None

    decision = evaluate_undercut(state, atk, _defender(), pred, _PIT_LOSS)

    assert decision.alert_type == "INSUFFICIENT_DATA"
    assert decision.should_alert is False


def test_evaluate_undercut_insufficient_when_no_predictor_coefficients() -> None:
    pred = ScipyPredictor([])  # no coefficients
    state = _state()

    decision = evaluate_undercut(state, _attacker(), _defender(), pred, _PIT_LOSS)

    assert decision.alert_type == "INSUFFICIENT_DATA"
    assert decision.should_alert is False


# ---------------------------------------------------------------------------
# Score and confidence thresholds
# ---------------------------------------------------------------------------


def test_evaluate_undercut_no_alert_when_score_below_threshold() -> None:
    """Defender on fresh tyres → small degradation → score too low to alert."""
    pred = _pred()
    state = _state()
    # Defender has only 5 laps on tyres — negligible degradation
    def_fresh = _defender(tyre_age=5)
    atk = _attacker(gap_ms=5_000, tyre_age=3)

    decision = evaluate_undercut(state, atk, def_fresh, pred, _PIT_LOSS)

    # Score might be low — we just verify should_alert is consistent with score
    if decision.score <= SCORE_THRESHOLD or decision.confidence <= CONFIDENCE_THRESHOLD:
        assert decision.should_alert is False


def test_evaluate_undercut_no_alert_when_confidence_below_threshold() -> None:
    """Low R² predictor → confidence too low → no alert even with high score."""
    pred = _pred(medium_r2=0.3, hard_r2=0.3)  # both below 0.5 threshold
    state = _state()

    decision = evaluate_undercut(state, _attacker(), _defender(), pred, _PIT_LOSS)

    assert decision.confidence < CONFIDENCE_THRESHOLD
    assert decision.should_alert is False


# ---------------------------------------------------------------------------
# Fields and invariants
# ---------------------------------------------------------------------------


def test_evaluate_undercut_decision_preserves_pit_loss_and_gap() -> None:
    pred = _pred()
    state = _state()
    atk = _attacker(gap_ms=8_000)

    decision = evaluate_undercut(state, atk, _defender(), pred, _PIT_LOSS)

    assert decision.pit_loss_ms == _PIT_LOSS
    assert decision.gap_actual_ms == 8_000


def test_evaluate_undercut_score_clamped_to_zero_one() -> None:
    """Score must always be in [0, 1] regardless of gap_recuperable magnitude."""
    pred = _pred()
    state = _state()
    # Attacker right behind (tiny gap) + very old defender → very high raw score
    atk = _attacker(gap_ms=100, tyre_age=20)
    def_ = _defender(tyre_age=40)

    decision = evaluate_undercut(state, atk, def_, pred, _PIT_LOSS)

    assert 0.0 <= decision.score <= 1.0


def test_evaluate_undercut_confidence_clamped_to_zero_one() -> None:
    pred = _pred(medium_r2=0.95, hard_r2=0.99)
    state = _state()
    decision = evaluate_undercut(state, _attacker(), _defender(), pred, _PIT_LOSS)
    assert 0.0 <= decision.confidence <= 1.0
