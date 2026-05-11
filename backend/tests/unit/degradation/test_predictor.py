"""Tests for the scipy-backed PacePredictor implementation."""

from __future__ import annotations

import pytest

from pitwall.degradation.predictor import ScipyCoefficient, ScipyPredictor
from pitwall.engine.projection import (
    PaceContext,
    PacePredictor,
    UnsupportedContextError,
)
from pitwall.engine.state import DriverState, RaceState
from pitwall.engine.undercut import evaluate_undercut


def test_scipy_predictor_satisfies_pace_predictor_protocol() -> None:
    predictor = ScipyPredictor(
        [
            ScipyCoefficient(
                circuit_id="monaco",
                compound="MEDIUM",
                a=80_000.0,
                b=100.0,
                c=2.0,
                r_squared=0.72,
                n_laps=42,
            )
        ]
    )

    assert isinstance(predictor, PacePredictor)


def test_predict_uses_quadratic_coefficients_and_r2_confidence() -> None:
    predictor = ScipyPredictor(
        [
            ScipyCoefficient(
                circuit_id="monaco",
                compound="MEDIUM",
                a=80_000.0,
                b=100.0,
                c=2.0,
                r_squared=0.72,
                n_laps=42,
            )
        ]
    )

    prediction = predictor.predict(
        PaceContext(
            driver_code="LEC",
            circuit_id="monaco",
            compound="MEDIUM",
            tyre_age=10,
        )
    )

    assert prediction.predicted_lap_time_ms == 81_200
    assert prediction.confidence == pytest.approx(0.72)


def test_is_available_matches_normalized_circuit_and_compound() -> None:
    predictor = ScipyPredictor(
        [
            ScipyCoefficient(
                circuit_id="monaco",
                compound="MEDIUM",
                a=80_000.0,
                b=100.0,
                c=2.0,
                r_squared=0.72,
                n_laps=42,
            )
        ]
    )

    assert predictor.is_available("Monaco", "MEDIUM") is True
    assert predictor.is_available("monaco", "SOFT") is False


def test_predict_raises_unsupported_context_for_missing_coefficients() -> None:
    predictor = ScipyPredictor([])

    with pytest.raises(UnsupportedContextError, match="no scipy coefficient"):
        predictor.predict(
            PaceContext(
                driver_code="LEC",
                circuit_id="monaco",
                compound="MEDIUM",
                tyre_age=10,
            )
        )


def test_load_coefficients_from_connection_rows() -> None:
    class FakeRow:
        def __init__(self, values: dict[str, object]) -> None:
            self._mapping = values

    class FakeConnection:
        def execute(self, statement: object) -> list[FakeRow]:
            assert "degradation_coefficients" in str(statement)
            return [
                FakeRow(
                    {
                        "circuit_id": "monaco",
                        "compound": "MEDIUM",
                        "a": 80_000.0,
                        "b": 100.0,
                        "c": 2.0,
                        "r_squared": 0.72,
                        "n_laps": 42,
                    }
                )
            ]

    predictor = ScipyPredictor.from_connection(FakeConnection())

    assert predictor.is_available("monaco", "MEDIUM") is True


def test_confidence_clamps_r2_to_pace_prediction_range() -> None:
    high_r2 = ScipyPredictor(
        [
            ScipyCoefficient(
                circuit_id="monaco",
                compound="MEDIUM",
                a=80_000.0,
                b=100.0,
                c=2.0,
                r_squared=1.4,
            )
        ]
    )
    low_r2 = ScipyPredictor(
        [
            ScipyCoefficient(
                circuit_id="monaco",
                compound="MEDIUM",
                a=80_000.0,
                b=100.0,
                c=2.0,
                r_squared=-0.2,
            )
        ]
    )

    ctx = PaceContext(
        driver_code="LEC",
        circuit_id="monaco",
        compound="MEDIUM",
        tyre_age=10,
    )

    assert high_r2.predict(ctx).confidence == 1.0
    assert low_r2.predict(ctx).confidence == 0.0


def test_engine_undercut_accepts_persisted_style_scipy_predictor() -> None:
    class FakeRow:
        def __init__(self, values: dict[str, object]) -> None:
            self._mapping = values

    class FakeConnection:
        def execute(self, statement: object) -> list[FakeRow]:
            assert "degradation_coefficients" in str(statement)
            return [
                FakeRow(
                    {
                        "circuit_id": "monaco",
                        "compound": "MEDIUM",
                        "a": 80_000.0,
                        "b": 250.0,
                        "c": 5.0,
                        "r_squared": 0.82,
                        "n_laps": 120,
                    }
                ),
                FakeRow(
                    {
                        "circuit_id": "monaco",
                        "compound": "HARD",
                        "a": 79_000.0,
                        "b": 120.0,
                        "c": 2.0,
                        "r_squared": 0.76,
                        "n_laps": 100,
                    }
                ),
            ]

    predictor = ScipyPredictor.from_connection(FakeConnection())
    state = RaceState(session_id="monaco_2024_R", circuit_id="monaco")
    attacker = DriverState(
        driver_code="NOR",
        team_code="mclaren",
        position=2,
        compound="MEDIUM",
        tyre_age=23,
        laps_in_stint=23,
        gap_to_ahead_ms=5_000,
    )
    defender = DriverState(
        driver_code="VER",
        team_code="red_bull",
        position=1,
        compound="MEDIUM",
        tyre_age=25,
        laps_in_stint=25,
        gap_to_ahead_ms=None,
    )

    decision = evaluate_undercut(state, attacker, defender, predictor, pit_loss_ms=21_000)

    assert decision.attacker_code == "NOR"
    assert decision.defender_code == "VER"
    assert 0.0 <= decision.score <= 1.0
    assert 0.0 <= decision.confidence <= 1.0
