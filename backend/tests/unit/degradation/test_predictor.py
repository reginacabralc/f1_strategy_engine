"""Tests for the scipy-backed PacePredictor implementation."""

from __future__ import annotations

import pytest

from pitwall.degradation.predictor import ScipyCoefficient, ScipyPredictor
from pitwall.engine.projection import (
    PaceContext,
    PacePredictor,
    UnsupportedContextError,
)


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
