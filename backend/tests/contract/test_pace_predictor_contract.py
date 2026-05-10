"""Contract: PacePredictor as consumed by the undercut engine.

This test demonstrates how Stream B's :mod:`pitwall.engine.undercut`
will call the predictor that Stream A delivers (see Stream A Day 1
plan and ``docs/quanta/04-ventana-undercut.md``). It serves as the
cross-stream sign-off: if Stream A ever changes the surface in a way
that breaks this consumer pattern, the test fails and forces a
renegotiation.

The test is intentionally simple — a deterministic linear predictor
plus a back-of-the-envelope gain calculation. Real engine logic
(safety-car suspension, cold-tyre penalty, confidence weighting)
arrives in Stream B Day 5.
"""

from __future__ import annotations

from typing import ClassVar

from pitwall.engine import (
    Compound,
    PaceContext,
    PacePrediction,
    PacePredictor,
)

# --------------------------------------------------------------------------
# Deterministic stub — only used by this contract test.
# Production predictors live in `pitwall.degradation` (Scipy) and
# `pitwall.ml` (XGBoost).
# --------------------------------------------------------------------------


class _LinearPredictor:
    """One base lap-time + one degradation rate per compound."""

    BASE_MS: ClassVar[dict[str, int]] = {
        "SOFT": 73_500,
        "MEDIUM": 75_000,
        "HARD": 76_000,
        "INTER": 95_000,
        "WET": 105_000,
    }
    RATE_MS_PER_LAP: ClassVar[dict[str, int]] = {
        "SOFT": 200,
        "MEDIUM": 100,
        "HARD": 50,
        "INTER": 300,
        "WET": 400,
    }

    def predict(self, ctx: PaceContext) -> PacePrediction:
        base = self.BASE_MS[ctx.compound]
        rate = self.RATE_MS_PER_LAP[ctx.compound]
        lap_ms = base + rate * ctx.tyre_age
        return PacePrediction(predicted_lap_time_ms=lap_ms, confidence=0.85)

    def is_available(self, circuit_id: str, compound: Compound) -> bool:
        return compound in self.BASE_MS


# --------------------------------------------------------------------------
# Sign-off tests — exercising the call sites from quanta 04.
# --------------------------------------------------------------------------


def test_stub_satisfies_protocol_at_runtime() -> None:
    assert isinstance(_LinearPredictor(), PacePredictor)


def test_engine_call_pattern_projecting_five_laps_ahead() -> None:
    """Reproduce the projection loop that ``pitwall.engine.undercut``
    will run for every relevant pair on every ``lap_complete`` event.

    Scenario: attacker and defender both 20 laps into a MEDIUM stint
    at Monaco. The attacker is considering an undercut — simulate
    fresh HARDs. The engine projects ``k = 1..5`` laps and sums the
    per-lap gain; if the cumulative gain exceeds
    ``pit_loss_ms + gap_actual_ms``, an alert is emitted.

    This test asserts the call mechanics (the contract), not the
    alert decision — decision tests are Stream B Day 5 territory.
    """
    predictor: PacePredictor = _LinearPredictor()
    PROJECTION_HORIZON = 5

    defender_compound: Compound = "MEDIUM"
    defender_age_now = 20
    attacker_compound_after_pit: Compound = "HARD"

    cumulative_gain_ms = 0
    for k in range(1, PROJECTION_HORIZON + 1):
        defender_ctx = PaceContext(
            driver_code="VER",
            circuit_id="monaco",
            compound=defender_compound,
            tyre_age=defender_age_now + k,
        )
        attacker_ctx = PaceContext(
            driver_code="NOR",
            circuit_id="monaco",
            compound=attacker_compound_after_pit,
            tyre_age=k - 1,  # k = 1 → first lap on new tyres → age = 0
        )

        defender_lap = predictor.predict(defender_ctx)
        attacker_lap = predictor.predict(attacker_ctx)

        assert defender_lap.predicted_lap_time_ms > 0
        assert attacker_lap.predicted_lap_time_ms > 0
        assert 0.0 <= defender_lap.confidence <= 1.0
        assert 0.0 <= attacker_lap.confidence <= 1.0

        cumulative_gain_ms += (
            defender_lap.predicted_lap_time_ms - attacker_lap.predicted_lap_time_ms
        )

    # Defender on MEDIUM aged 21..25 → 75 000 + 100·age ∈ [77 100, 77 500].
    # Attacker on HARD aged 0..4    → 76 000 + 50·age   ∈ [76 000, 76 200].
    # Per-lap gain ranges from ~1 100 ms (k=1) to ~1 300 ms (k=5).
    # We assert the order of magnitude rather than the exact number so
    # the test does not get tightly coupled to the stub's coefficients.
    assert 4_000 < cumulative_gain_ms < 8_000


def test_is_available_gate_before_predict() -> None:
    """The engine will use ``is_available`` to skip pairs that the
    predictor cannot serve, rather than catching ``UnsupportedContext``
    in the hot path."""
    p: PacePredictor = _LinearPredictor()
    assert p.is_available("monaco", "MEDIUM") is True
    assert p.is_available("monaco", "WET") is True


def test_optional_context_fields_accepted() -> None:
    """The XGBoost predictor will use the optional fields. The contract
    requires that any predictor accept them — even if it ignores them
    (as the stub does)."""
    predictor: PacePredictor = _LinearPredictor()
    full_ctx = PaceContext(
        driver_code="VER",
        circuit_id="monaco",
        compound="MEDIUM",
        tyre_age=15,
        team_code="RBR",
        track_temp_c=38.2,
        air_temp_c=24.0,
        humidity_pct=62.0,
        stint_position=2,
        lap_in_stint=15,
        laps_remaining=55,
        total_laps=78,
    )
    pred = predictor.predict(full_ctx)
    assert pred.predicted_lap_time_ms == 75_000 + 100 * 15
