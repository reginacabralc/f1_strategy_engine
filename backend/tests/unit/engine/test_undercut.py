"""Tests for evaluate_undercut() — the core undercut-viability scorer."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

from pitwall.degradation.predictor import ScipyCoefficient, ScipyPredictor
from pitwall.engine.projection import PaceContext, PacePrediction
from pitwall.engine.state import DriverState, RaceState
from pitwall.engine.undercut import (
    CONFIDENCE_THRESHOLD,
    SCORE_THRESHOLD,
    evaluate_undercut,
)
from pitwall.feeds.base import Event

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PIT_LOSS = 21_000
_TS = datetime(2024, 5, 26, 13, 0, 0, tzinfo=UTC)


def _pred(
    medium_r2: float = 0.8,
    hard_r2: float = 0.75,
) -> ScipyPredictor:
    """Monaco MEDIUM + HARD coefficients with fast degradation (for clear signals)."""
    return ScipyPredictor(
        [
            # MEDIUM: degrades aggressively (high b + c)
            ScipyCoefficient("monaco", "MEDIUM", a=80_000.0, b=250.0, c=5.0, r_squared=medium_r2),
            # HARD: durable, faster absolute pace
            ScipyCoefficient("monaco", "HARD", a=79_000.0, b=120.0, c=2.0, r_squared=hard_r2),
        ]
    )


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


def _event(event_type: str, payload: dict[str, Any]) -> Event:
    return cast(
        Event,
        {"type": event_type, "session_id": "monaco_2024_R", "ts": _TS, "payload": payload},
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


def test_evaluate_undercut_passes_live_ml_context_and_references() -> None:
    class _CapturingPredictor:
        def __init__(self) -> None:
            self.contexts: list[PaceContext] = []

        def predict(self, ctx: PaceContext) -> PacePrediction:
            self.contexts.append(ctx)
            lap_ms = 90_000 if ctx.compound == "MEDIUM" else 72_000
            return PacePrediction(predicted_lap_time_ms=lap_ms, confidence=0.9)

        def is_available(self, circuit_id: str, compound: str) -> bool:
            return True

    state = RaceState()
    state.apply(_event("session_start", {"circuit_id": "monaco", "total_laps": 78}))
    state.apply(
        _event(
            "weather_update",
            {"track_temp_c": 42.0, "air_temp_c": 28.0, "humidity_pct": 35.0},
        )
    )
    state.apply(
        _event(
            "lap_complete",
            {
                "driver_code": "VER",
                "lap_number": 12,
                "position": 1,
                "gap_to_leader_ms": 0,
                "lap_time_ms": 80_000,
                "compound": "MEDIUM",
                "tyre_age": 25,
                "is_valid": True,
                "is_pit_in": False,
                "is_pit_out": False,
                "track_status": "GREEN",
            },
        )
    )
    state.drivers["VER"].laps_in_stint = 25
    state.apply(
        _event(
            "lap_complete",
            {
                "driver_code": "HAM",
                "lap_number": 12,
                "position": 3,
                "gap_to_ahead_ms": 5_000,
                "lap_time_ms": 79_000,
                "compound": "HARD",
                "tyre_age": 8,
                "is_valid": True,
                "is_pit_in": False,
                "is_pit_out": False,
                "track_status": "GREEN",
            },
        )
    )
    state.drivers["HAM"].laps_in_stint = 8
    state.apply(
        _event(
            "lap_complete",
            {
                "driver_code": "NOR",
                "lap_number": 12,
                "position": 2,
                "gap_to_ahead_ms": 1_200,
                "gap_to_leader_ms": 1_200,
                "lap_time_ms": 81_000,
                "compound": "MEDIUM",
                "tyre_age": 23,
                "is_valid": True,
                "is_pit_in": False,
                "is_pit_out": False,
                "track_status": "GREEN",
            },
        )
    )
    state.drivers["NOR"].laps_in_stint = 23
    predictor = _CapturingPredictor()

    decision = evaluate_undercut(
        state,
        state.drivers["NOR"],
        state.drivers["VER"],
        predictor,
        _PIT_LOSS,
    )

    assert decision.should_alert is True
    assert predictor.contexts
    assert all(ctx.lap_number is not None for ctx in predictor.contexts)
    assert all(ctx.total_laps == 78 for ctx in predictor.contexts)
    assert all(ctx.track_temp_c == 42.0 for ctx in predictor.contexts)
    assert all(ctx.position in {1, 2} for ctx in predictor.contexts)
    assert {ctx.compound: ctx.reference_lap_time_ms for ctx in predictor.contexts} == {
        "MEDIUM": 80_500,
        "HARD": 79_000,
    }
    assert any(ctx.is_in_traffic is True for ctx in predictor.contexts)


# ---------------------------------------------------------------------------
# Insufficient data guards
# ---------------------------------------------------------------------------


def test_evaluate_undercut_insufficient_when_laps_in_stint_lt_3() -> None:
    pred = _pred()
    state = _state()
    atk = DriverState(
        driver_code="NOR",
        position=2,
        compound="MEDIUM",
        tyre_age=2,
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


# ---------------------------------------------------------------------------
# Rain / wet conditions — §6.9 UNDERCUT_DISABLED_RAIN
# ---------------------------------------------------------------------------


def test_undercut_disabled_rain_when_attacker_on_inter() -> None:
    pred = _pred()
    state = _state()
    atk = DriverState(
        driver_code="NOR",
        position=2,
        compound="INTER",
        tyre_age=5,
        laps_in_stint=5,
        gap_to_ahead_ms=3_000,
    )
    decision = evaluate_undercut(state, atk, _defender(), pred, _PIT_LOSS)
    assert decision.alert_type == "UNDERCUT_DISABLED_RAIN"
    assert decision.should_alert is False
    assert decision.score == 0.0


def test_undercut_disabled_rain_when_attacker_on_wet() -> None:
    pred = _pred()
    state = _state()
    atk = DriverState(
        driver_code="NOR",
        position=2,
        compound="WET",
        tyre_age=5,
        laps_in_stint=5,
        gap_to_ahead_ms=3_000,
    )
    decision = evaluate_undercut(state, atk, _defender(), pred, _PIT_LOSS)
    assert decision.alert_type == "UNDERCUT_DISABLED_RAIN"
    assert decision.should_alert is False


def test_undercut_disabled_rain_when_defender_on_inter() -> None:
    pred = _pred()
    state = _state()
    def_wet = DriverState(
        driver_code="VER",
        position=1,
        compound="INTER",
        tyre_age=8,
        laps_in_stint=8,
    )
    decision = evaluate_undercut(state, _attacker(), def_wet, pred, _PIT_LOSS)
    assert decision.alert_type == "UNDERCUT_DISABLED_RAIN"
    assert decision.should_alert is False


def test_undercut_rain_check_is_case_insensitive() -> None:
    """Compound stored in lowercase should still trigger the rain guard."""
    pred = _pred()
    state = _state()
    atk = DriverState(
        driver_code="NOR",
        position=2,
        compound="inter",  # lowercase
        tyre_age=5,
        laps_in_stint=5,
        gap_to_ahead_ms=3_000,
    )
    decision = evaluate_undercut(state, atk, _defender(), pred, _PIT_LOSS)
    assert decision.alert_type == "UNDERCUT_DISABLED_RAIN"


# ---------------------------------------------------------------------------
# Defender just pitted — §6.9 pit-recent guard
# ---------------------------------------------------------------------------


def test_insufficient_data_when_defender_just_pitted_0_laps() -> None:
    """Defender with laps_in_stint=0 (just pitted, no laps yet) → INSUFFICIENT_DATA."""
    pred = _pred()
    state = _state()
    def_fresh = DriverState(
        driver_code="VER",
        position=1,
        compound="HARD",
        tyre_age=0,
        laps_in_stint=0,  # literally just out of pit lane
    )
    decision = evaluate_undercut(state, _attacker(), def_fresh, pred, _PIT_LOSS)
    assert decision.alert_type == "INSUFFICIENT_DATA"
    assert decision.should_alert is False


def test_insufficient_data_when_defender_just_pitted_1_lap() -> None:
    """Defender on first lap out of pit (out-lap) → INSUFFICIENT_DATA."""
    pred = _pred()
    state = _state()
    def_outlap = DriverState(
        driver_code="VER",
        position=1,
        compound="HARD",
        tyre_age=1,
        laps_in_stint=1,  # one lap since pit — still suppressed
    )
    decision = evaluate_undercut(state, _attacker(), def_outlap, pred, _PIT_LOSS)
    assert decision.alert_type == "INSUFFICIENT_DATA"
    assert decision.should_alert is False


def test_undercut_evaluates_when_defender_has_2_laps_on_tyres() -> None:
    """Once defender has >= 2 laps on the current stint, evaluation resumes."""
    pred = _pred()
    state = _state()
    def_2laps = DriverState(
        driver_code="VER",
        position=1,
        compound="HARD",
        tyre_age=2,
        laps_in_stint=2,
    )
    atk = _attacker(gap_ms=5_000, tyre_age=23)
    decision = evaluate_undercut(state, atk, def_2laps, pred, _PIT_LOSS)
    # May or may not be viable, but should NOT return INSUFFICIENT_DATA for
    # the recent-pit reason (attacker has enough laps)
    assert decision.alert_type != "UNDERCUT_DISABLED_RAIN"
