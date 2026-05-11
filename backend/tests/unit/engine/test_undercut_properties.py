"""Property-based tests for the undercut engine — master plan §11.5.

Two invariants specified in the master plan:

1. ``pit_loss > gap_recuperable_max  →  no UNDERCUT_VIABLE``
2. ``confidence < CONFIDENCE_THRESHOLD  →  no alert``

We test these with Hypothesis to exercise a wide range of inputs that
would be tedious to enumerate manually.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from pitwall.degradation.predictor import ScipyCoefficient, ScipyPredictor
from pitwall.engine.state import DriverState, RaceState
from pitwall.engine.undercut import (
    CONFIDENCE_THRESHOLD,
    SCORE_THRESHOLD,
    evaluate_undercut,
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _state(circuit: str = "monaco") -> RaceState:
    return RaceState(session_id="test", circuit_id=circuit)


def _pred(medium_r2: float = 0.8, hard_r2: float = 0.8) -> ScipyPredictor:
    return ScipyPredictor(
        [
            ScipyCoefficient("monaco", "MEDIUM", 74_500.0, 200.0, 5.0, medium_r2),
            ScipyCoefficient("monaco", "HARD", 74_000.0, 80.0, 2.0, hard_r2),
        ]
    )


# ---------------------------------------------------------------------------
# Invariant 1: pit_loss > gap_recuperable_max → score == 0, no UNDERCUT_VIABLE
#
# When both drivers lap at the same time, gap_recuperable = 0.
# Since pit_loss > 0 always, (gap_recuperable - pit_loss - ...) < 0 → score = 0.
# ---------------------------------------------------------------------------


@given(
    lap_ms=st.integers(min_value=60_000, max_value=120_000),
    pit_loss=st.integers(min_value=18_000, max_value=35_000),
    gap_actual=st.integers(min_value=500, max_value=29_000),
    r2=st.floats(min_value=0.51, max_value=1.0),
    laps_in_stint=st.integers(min_value=10, max_value=40),
)
@settings(max_examples=300)
def test_no_viable_when_equal_pace_predictor(
    lap_ms: int,
    pit_loss: int,
    gap_actual: int,
    r2: float,
    laps_in_stint: int,
) -> None:
    """When attacker and defender lap identically, gap_recuperable = 0.

    Regardless of all other parameters, score = 0 and should_alert = False.
    """
    pred = ScipyPredictor(
        [
            ScipyCoefficient("monaco", "MEDIUM", float(lap_ms), 0.0, 0.0, r2),
            ScipyCoefficient("monaco", "HARD", float(lap_ms), 0.0, 0.0, r2),
        ]
    )
    attacker = DriverState(
        driver_code="ATK",
        position=2,
        compound="MEDIUM",
        tyre_age=laps_in_stint,
        laps_in_stint=laps_in_stint,
        gap_to_ahead_ms=gap_actual,
    )
    defender = DriverState(
        driver_code="DEF",
        position=1,
        compound="MEDIUM",
        tyre_age=laps_in_stint + 2,
        laps_in_stint=laps_in_stint + 2,
    )

    decision = evaluate_undercut(_state(), attacker, defender, pred, pit_loss)

    # No time is recuperated because both drive identically → score = 0
    assert decision.score == 0.0, (
        f"Expected score=0 with equal-pace predictor, got {decision.score}"
    )
    assert decision.should_alert is False


@given(
    attacker_lap_ms=st.integers(min_value=60_000, max_value=120_000),
    delta=st.integers(min_value=500, max_value=10_000),
    pit_loss=st.integers(min_value=18_000, max_value=35_000),
    gap_actual=st.integers(min_value=500, max_value=29_000),
    r2=st.floats(min_value=0.51, max_value=1.0),
    laps_in_stint=st.integers(min_value=10, max_value=40),
)
@settings(max_examples=300)
def test_no_viable_when_attacker_faster_than_defender(
    attacker_lap_ms: int,
    delta: int,
    pit_loss: int,
    gap_actual: int,
    r2: float,
    laps_in_stint: int,
) -> None:
    """Attacker lapping FASTER than defender: undercut makes no sense.

    If the attacker is already quicker, their pace advantage over the
    defender is negative (defender - attacker < 0), so gap_recuperable <= 0
    and score = 0.
    """
    defender_lap_ms = attacker_lap_ms - delta  # defender is faster
    pred = ScipyPredictor(
        [
            ScipyCoefficient("monaco", "MEDIUM", float(attacker_lap_ms), 0.0, 0.0, r2),
            ScipyCoefficient("monaco", "HARD", float(defender_lap_ms), 0.0, 0.0, r2),
        ]
    )
    attacker = DriverState(
        driver_code="ATK",
        position=2,
        compound="MEDIUM",
        tyre_age=laps_in_stint,
        laps_in_stint=laps_in_stint,
        gap_to_ahead_ms=gap_actual,
    )
    defender = DriverState(
        driver_code="DEF",
        position=1,
        compound="HARD",
        tyre_age=laps_in_stint + 2,
        laps_in_stint=laps_in_stint + 2,
    )

    decision = evaluate_undercut(_state(), attacker, defender, pred, pit_loss)

    assert decision.score == 0.0
    assert decision.should_alert is False


# ---------------------------------------------------------------------------
# Invariant 2: confidence < CONFIDENCE_THRESHOLD → should_alert = False
#
# We construct an otherwise-viable scenario (heavy degradation, close gap)
# and sweep R² from 0 to CONFIDENCE_THRESHOLD to verify the guard fires.
# ---------------------------------------------------------------------------


@given(r2=st.floats(min_value=0.0, max_value=CONFIDENCE_THRESHOLD - 1e-9))
@settings(max_examples=200)
def test_no_alert_when_confidence_below_threshold(r2: float) -> None:
    """``confidence < CONFIDENCE_THRESHOLD`` must suppress all alerts.

    Regardless of how large score is, if confidence drops below the threshold
    no UNDERCUT_VIABLE alert should be emitted.
    """
    pred = _pred(medium_r2=r2, hard_r2=r2)
    attacker = DriverState(
        driver_code="ATK",
        position=2,
        compound="MEDIUM",
        tyre_age=20,
        laps_in_stint=20,
        gap_to_ahead_ms=2_000,
    )
    defender = DriverState(
        driver_code="DEF",
        position=1,
        compound="MEDIUM",
        tyre_age=30,
        laps_in_stint=30,
    )

    decision = evaluate_undercut(_state(), attacker, defender, pred)

    assert decision.confidence < CONFIDENCE_THRESHOLD, (
        f"Expected confidence < {CONFIDENCE_THRESHOLD}, got {decision.confidence}"
    )
    assert decision.should_alert is False, (
        f"Expected no alert with R²={r2:.4f}, but should_alert={decision.should_alert}"
    )


# ---------------------------------------------------------------------------
# Invariant 3: score in [0, 1] always (clamping)
# ---------------------------------------------------------------------------


@given(
    a_ms=st.integers(min_value=60_000, max_value=90_000),
    d_ms=st.integers(min_value=60_000, max_value=90_000),
    pit_loss=st.integers(min_value=1, max_value=60_000),
    gap_actual=st.integers(min_value=0, max_value=29_000),
    laps=st.integers(min_value=10, max_value=50),
)
@settings(max_examples=400)
def test_score_always_in_zero_one(
    a_ms: int, d_ms: int, pit_loss: int, gap_actual: int, laps: int
) -> None:
    """``UndercutDecision.score`` must always be in ``[0.0, 1.0]``."""
    pred = ScipyPredictor(
        [
            ScipyCoefficient("monaco", "MEDIUM", float(a_ms), 0.0, 0.0, 0.8),
            ScipyCoefficient("monaco", "HARD", float(d_ms), 0.0, 0.0, 0.8),
        ]
    )
    attacker = DriverState(
        driver_code="A",
        position=2,
        compound="MEDIUM",
        tyre_age=laps,
        laps_in_stint=laps,
        gap_to_ahead_ms=gap_actual,
    )
    defender = DriverState(
        driver_code="D",
        position=1,
        compound="HARD",
        tyre_age=laps + 2,
        laps_in_stint=laps + 2,
    )

    d = evaluate_undercut(_state(), attacker, defender, pred, pit_loss)

    assert 0.0 <= d.score <= 1.0, f"Score out of bounds: {d.score}"
    assert 0.0 <= d.confidence <= 1.0, f"Confidence out of bounds: {d.confidence}"


# ---------------------------------------------------------------------------
# Invariant 4: should_alert ↔ score AND confidence above thresholds
# ---------------------------------------------------------------------------


@given(
    a_ms=st.integers(min_value=60_000, max_value=90_000),
    d_ms=st.integers(min_value=60_000, max_value=90_000),
    pit_loss=st.integers(min_value=10_000, max_value=30_000),
    gap_actual=st.integers(min_value=100, max_value=29_000),
    r2=st.floats(min_value=0.0, max_value=1.0),
    laps=st.integers(min_value=10, max_value=50),
)
@settings(max_examples=500)
def test_should_alert_iff_both_thresholds_exceeded(
    a_ms: int,
    d_ms: int,
    pit_loss: int,
    gap_actual: int,
    r2: float,
    laps: int,
) -> None:
    """``should_alert`` must equal ``score > SCORE_THRESHOLD AND confidence > CONFIDENCE_THRESHOLD``."""  # noqa: E501
    pred = ScipyPredictor(
        [
            ScipyCoefficient("monaco", "MEDIUM", float(a_ms), 0.0, 0.0, r2),
            ScipyCoefficient("monaco", "HARD", float(d_ms), 0.0, 0.0, r2),
        ]
    )
    attacker = DriverState(
        driver_code="A",
        position=2,
        compound="MEDIUM",
        tyre_age=laps,
        laps_in_stint=laps,
        gap_to_ahead_ms=gap_actual,
    )
    defender = DriverState(
        driver_code="D",
        position=1,
        compound="HARD",
        tyre_age=laps + 2,
        laps_in_stint=laps + 2,
    )

    d = evaluate_undercut(_state(), attacker, defender, pred, pit_loss)

    expected_alert = d.score > SCORE_THRESHOLD and d.confidence > CONFIDENCE_THRESHOLD
    assert d.should_alert == expected_alert, (
        f"should_alert mismatch: score={d.score:.4f} conf={d.confidence:.4f} "
        f"expected_alert={expected_alert} actual={d.should_alert}"
    )
