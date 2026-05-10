"""Tests for the PacePredictor protocol and supporting types.

These tests lock the contract that Stream A and Stream B agreed on at
the Day 1 kickoff. Changing them is a signal that the contract has
moved and the change must be reviewed by both streams.
"""

from __future__ import annotations

import pytest

from pitwall.engine.projection import (
    Compound,
    PaceContext,
    PacePrediction,
    PacePredictor,
    UnsupportedContextError,
)

# --------------------------------------------------------------------------
# PaceContext
# --------------------------------------------------------------------------


class TestPaceContext:
    def test_minimal_required_fields(self) -> None:
        ctx = PaceContext(
            driver_code="VER",
            circuit_id="monaco",
            compound="MEDIUM",
            tyre_age=10,
        )
        assert ctx.driver_code == "VER"
        assert ctx.circuit_id == "monaco"
        assert ctx.compound == "MEDIUM"
        assert ctx.tyre_age == 10
        # All optional fields default to None.
        assert ctx.team_code is None
        assert ctx.track_temp_c is None
        assert ctx.air_temp_c is None
        assert ctx.humidity_pct is None
        assert ctx.stint_position is None
        assert ctx.lap_in_stint is None
        assert ctx.laps_remaining is None
        assert ctx.total_laps is None

    def test_all_optional_fields_accepted(self) -> None:
        ctx = PaceContext(
            driver_code="VER",
            circuit_id="monaco",
            compound="MEDIUM",
            tyre_age=10,
            team_code="RBR",
            track_temp_c=38.2,
            air_temp_c=24.0,
            humidity_pct=62.0,
            stint_position=2,
            lap_in_stint=10,
            laps_remaining=55,
            total_laps=78,
        )
        assert ctx.team_code == "RBR"
        assert ctx.track_temp_c == pytest.approx(38.2)
        assert ctx.humidity_pct == pytest.approx(62.0)

    def test_rejects_empty_driver_code(self) -> None:
        with pytest.raises(ValueError, match="driver_code"):
            PaceContext(
                driver_code="",
                circuit_id="monaco",
                compound="MEDIUM",
                tyre_age=10,
            )

    def test_rejects_empty_circuit_id(self) -> None:
        with pytest.raises(ValueError, match="circuit_id"):
            PaceContext(
                driver_code="VER",
                circuit_id="",
                compound="MEDIUM",
                tyre_age=10,
            )

    def test_rejects_negative_tyre_age(self) -> None:
        with pytest.raises(ValueError, match="tyre_age must be >= 0"):
            PaceContext(
                driver_code="VER",
                circuit_id="monaco",
                compound="MEDIUM",
                tyre_age=-1,
            )

    def test_accepts_zero_tyre_age(self) -> None:
        # Out-lap on a brand-new tyre is tyre_age = 0.
        ctx = PaceContext(
            driver_code="VER",
            circuit_id="monaco",
            compound="MEDIUM",
            tyre_age=0,
        )
        assert ctx.tyre_age == 0

    def test_rejects_negative_lap_in_stint(self) -> None:
        with pytest.raises(ValueError, match="lap_in_stint must be >= 0"):
            PaceContext(
                driver_code="VER",
                circuit_id="monaco",
                compound="MEDIUM",
                tyre_age=10,
                lap_in_stint=-1,
            )

    def test_rejects_zero_stint_position(self) -> None:
        with pytest.raises(ValueError, match="stint_position must be >= 1"):
            PaceContext(
                driver_code="VER",
                circuit_id="monaco",
                compound="MEDIUM",
                tyre_age=10,
                stint_position=0,
            )

    def test_rejects_zero_total_laps(self) -> None:
        with pytest.raises(ValueError, match="total_laps must be > 0"):
            PaceContext(
                driver_code="VER",
                circuit_id="monaco",
                compound="MEDIUM",
                tyre_age=10,
                total_laps=0,
            )

    def test_rejects_negative_laps_remaining(self) -> None:
        with pytest.raises(ValueError, match="laps_remaining must be >= 0"):
            PaceContext(
                driver_code="VER",
                circuit_id="monaco",
                compound="MEDIUM",
                tyre_age=10,
                laps_remaining=-1,
            )

    def test_rejects_humidity_below_zero(self) -> None:
        with pytest.raises(ValueError, match="humidity_pct"):
            PaceContext(
                driver_code="VER",
                circuit_id="monaco",
                compound="MEDIUM",
                tyre_age=10,
                humidity_pct=-0.1,
            )

    def test_rejects_humidity_above_one_hundred(self) -> None:
        with pytest.raises(ValueError, match="humidity_pct"):
            PaceContext(
                driver_code="VER",
                circuit_id="monaco",
                compound="MEDIUM",
                tyre_age=10,
                humidity_pct=100.5,
            )

    def test_accepts_humidity_at_boundaries(self) -> None:
        PaceContext(
            driver_code="VER",
            circuit_id="monaco",
            compound="MEDIUM",
            tyre_age=10,
            humidity_pct=0.0,
        )
        PaceContext(
            driver_code="VER",
            circuit_id="monaco",
            compound="MEDIUM",
            tyre_age=10,
            humidity_pct=100.0,
        )

    def test_is_frozen(self) -> None:
        ctx = PaceContext(
            driver_code="VER",
            circuit_id="monaco",
            compound="MEDIUM",
            tyre_age=10,
        )
        # frozen=True dataclasses raise FrozenInstanceError (a TypeError
        # subclass). We accept either to keep the test resilient.
        with pytest.raises((AttributeError, TypeError)):
            ctx.tyre_age = 20  # type: ignore[misc]

    def test_is_hashable_for_caching(self) -> None:
        # Frozen + slots dataclass is hashable; useful for memoising
        # predictions inside the engine hot path.
        ctx = PaceContext(
            driver_code="VER",
            circuit_id="monaco",
            compound="MEDIUM",
            tyre_age=10,
        )
        assert hash(ctx) == hash(ctx)


# --------------------------------------------------------------------------
# PacePrediction
# --------------------------------------------------------------------------


class TestPacePrediction:
    def test_valid_prediction(self) -> None:
        p = PacePrediction(predicted_lap_time_ms=74_500, confidence=0.8)
        assert p.predicted_lap_time_ms == 74_500
        assert p.confidence == pytest.approx(0.8)

    def test_rejects_zero_lap_time(self) -> None:
        with pytest.raises(ValueError, match="predicted_lap_time_ms must be > 0"):
            PacePrediction(predicted_lap_time_ms=0, confidence=0.5)

    def test_rejects_negative_lap_time(self) -> None:
        with pytest.raises(ValueError, match="predicted_lap_time_ms must be > 0"):
            PacePrediction(predicted_lap_time_ms=-100, confidence=0.5)

    def test_rejects_confidence_above_one(self) -> None:
        with pytest.raises(ValueError, match=r"confidence must be in"):
            PacePrediction(predicted_lap_time_ms=74_500, confidence=1.1)

    def test_rejects_confidence_below_zero(self) -> None:
        with pytest.raises(ValueError, match=r"confidence must be in"):
            PacePrediction(predicted_lap_time_ms=74_500, confidence=-0.1)

    def test_accepts_confidence_at_boundaries(self) -> None:
        PacePrediction(predicted_lap_time_ms=1, confidence=0.0)
        PacePrediction(predicted_lap_time_ms=1, confidence=1.0)


# --------------------------------------------------------------------------
# UnsupportedContextError
# --------------------------------------------------------------------------


def test_unsupported_context_error_is_lookup_error() -> None:
    """Engines may catch the broader LookupError without importing us."""
    with pytest.raises(LookupError):
        raise UnsupportedContextError("no fit for (monaco, WET)")


# --------------------------------------------------------------------------
# PacePredictor protocol
# --------------------------------------------------------------------------


class _DummyPredictor:
    """Minimal stub used to verify the protocol shape via runtime_checkable.

    Both implementations (Scipy and XGBoost) will need to expose the same
    surface; this dummy is the minimum we expect the engine to be able to
    treat as a :class:`PacePredictor`.
    """

    def predict(self, ctx: PaceContext) -> PacePrediction:
        return PacePrediction(predicted_lap_time_ms=80_000, confidence=0.5)

    def is_available(self, circuit_id: str, compound: Compound) -> bool:
        return True


class TestPacePredictorProtocol:
    def test_dummy_satisfies_protocol_at_runtime(self) -> None:
        # runtime_checkable Protocol verifies attribute presence (and that
        # they are callable), not signatures.
        assert isinstance(_DummyPredictor(), PacePredictor)

    def test_predictor_can_be_called(self) -> None:
        predictor: PacePredictor = _DummyPredictor()
        ctx = PaceContext(
            driver_code="VER",
            circuit_id="monaco",
            compound="MEDIUM",
            tyre_age=15,
        )
        result = predictor.predict(ctx)
        assert result.predicted_lap_time_ms > 0
        assert 0.0 <= result.confidence <= 1.0

    def test_is_available_returns_bool(self) -> None:
        predictor: PacePredictor = _DummyPredictor()
        assert predictor.is_available("monaco", "MEDIUM") is True

    def test_object_without_predict_does_not_satisfy_protocol(self) -> None:
        class NotAPredictor:
            def is_available(self, circuit_id: str, compound: Compound) -> bool:
                return True

        assert not isinstance(NotAPredictor(), PacePredictor)

    def test_object_without_is_available_does_not_satisfy_protocol(self) -> None:
        class NotAPredictor:
            def predict(self, ctx: PaceContext) -> PacePrediction:
                return PacePrediction(predicted_lap_time_ms=70_000, confidence=0.5)

        assert not isinstance(NotAPredictor(), PacePredictor)
