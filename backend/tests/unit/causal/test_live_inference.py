"""Tests for Phase 8/9 live causal inference and explanations."""

from __future__ import annotations

from pitwall.causal.live_inference import build_live_observation, evaluate_causal_live
from pitwall.degradation.predictor import ScipyCoefficient, ScipyPredictor
from pitwall.engine.state import DriverState, RaceState


def _predictor() -> ScipyPredictor:
    return ScipyPredictor(
        [
            ScipyCoefficient(
                "monaco",
                "MEDIUM",
                a=80_000.0,
                b=250.0,
                c=5.0,
                r_squared=0.85,
            ),
            ScipyCoefficient(
                "monaco",
                "HARD",
                a=79_000.0,
                b=120.0,
                c=2.0,
                r_squared=0.80,
            ),
        ]
    )


def _state() -> RaceState:
    return RaceState(
        session_id="monaco_2024_R",
        circuit_id="monaco",
        total_laps=78,
        current_lap=30,
        track_status="GREEN",
        track_temp_c=42.0,
        air_temp_c=26.0,
        rainfall=False,
    )


def _attacker(gap_ms: int | None = 5_000) -> DriverState:
    return DriverState(
        driver_code="NOR",
        team_code="mclaren",
        position=2,
        gap_to_ahead_ms=gap_ms,
        compound="MEDIUM",
        tyre_age=23,
        laps_in_stint=23,
    )


def _defender() -> DriverState:
    return DriverState(
        driver_code="VER",
        team_code="red_bull",
        position=1,
        compound="MEDIUM",
        tyre_age=30,
        laps_in_stint=30,
    )


def test_build_live_observation_uses_current_pair_state() -> None:
    observation = build_live_observation(
        _state(),
        _attacker(),
        _defender(),
        pit_loss_ms=21_000,
    )

    assert observation.session_id == "monaco_2024_R"
    assert observation.lap_number == 30
    assert observation.laps_remaining == 48
    assert observation.attacker_code == "NOR"
    assert observation.defender_code == "VER"
    assert observation.gap_to_rival_ms == 5_000
    assert observation.tyre_age_delta == 7


def test_evaluate_causal_live_predicts_simulates_and_explains() -> None:
    result = evaluate_causal_live(
        _state(),
        _attacker(),
        _defender(),
        _predictor(),
        pit_loss_ms=21_000,
    )

    assert result.observation.attacker_code == "NOR"
    assert result.support_level in {"strong", "weak"}
    assert result.required_gain_ms is not None
    assert result.projected_gain_ms is not None
    assert result.top_factors
    assert {scenario.scenario_name for scenario in result.counterfactuals} == {
        "base_case",
        "pit_now",
        "pit_next_lap",
        "pit_now_high_traffic",
        "pit_now_low_traffic",
        "pit_loss_minus_1000_ms",
        "pit_loss_plus_1000_ms",
    }
    assert any("projected fresh-tyre gain" in text for text in result.explanations)
    assert any("pit_loss_plus_1000_ms" in text for text in result.explanations)


def test_evaluate_causal_live_marks_missing_gap_as_insufficient() -> None:
    result = evaluate_causal_live(
        _state(),
        _attacker(gap_ms=None),
        _defender(),
        _predictor(),
        pit_loss_ms=21_000,
    )

    assert result.undercut_viable is False
    assert result.support_level == "insufficient"
    assert result.required_gain_ms is None
    assert any("not contain enough" in text for text in result.explanations)


def test_adaptive_confidence_r2_035_gives_strong_support() -> None:
    """R²=0.35 is above the demo-data threshold and must give strong support."""
    pred = ScipyPredictor([
        ScipyCoefficient("monaco", "MEDIUM", a=80_000.0, b=250.0, c=5.0, r_squared=0.35),
        ScipyCoefficient("monaco", "HARD",   a=79_000.0, b=120.0, c=2.0, r_squared=0.35),
    ])
    state = RaceState(
        session_id="monaco_2024_R", circuit_id="monaco", total_laps=78, current_lap=30,
        track_status="GREEN", track_temp_c=42.0, air_temp_c=26.0, rainfall=False,
    )
    attacker = DriverState(
        driver_code="NOR", team_code="mclaren", position=2, gap_to_ahead_ms=5_000,
        compound="MEDIUM", tyre_age=23, laps_in_stint=23,
    )
    defender = DriverState(
        driver_code="VER", team_code="red_bull", position=1,
        compound="MEDIUM", tyre_age=30, laps_in_stint=30,
    )
    result = evaluate_causal_live(state, attacker, defender, pred, pit_loss_ms=21_000)
    assert result.support_level != "insufficient", (
        f"Expected strong/weak but got {result.support_level!r}. "
        "Check CONFIDENCE_STRONG_THRESHOLD in live_inference.py"
    )


def test_adaptive_confidence_r2_010_gives_insufficient() -> None:
    """R²=0.10 is noise-level and must give insufficient support."""
    pred = ScipyPredictor([
        ScipyCoefficient("monaco", "MEDIUM", a=80_000.0, b=250.0, c=5.0, r_squared=0.10),
        ScipyCoefficient("monaco", "HARD",   a=79_000.0, b=120.0, c=2.0, r_squared=0.10),
    ])
    state = RaceState(
        session_id="monaco_2024_R", circuit_id="monaco", total_laps=78, current_lap=30,
        track_status="GREEN", track_temp_c=42.0, air_temp_c=26.0, rainfall=False,
    )
    attacker = DriverState(
        driver_code="NOR", position=2, gap_to_ahead_ms=5_000,
        compound="MEDIUM", tyre_age=23, laps_in_stint=23,
    )
    defender = DriverState(
        driver_code="VER", position=1, compound="MEDIUM", tyre_age=30, laps_in_stint=30,
    )
    result = evaluate_causal_live(state, attacker, defender, pred, pit_loss_ms=21_000)
    assert result.support_level == "insufficient"
