"""Tests for data_quality_factor, cold-tyre calibration, and custom penalties."""

from __future__ import annotations

from pitwall.degradation.predictor import ScipyCoefficient, ScipyPredictor
from pitwall.engine.calibration import calibrate_cold_tyre_penalties
from pitwall.engine.projection import COLD_TYRE_PENALTIES_MS, project_pace
from pitwall.engine.state import DriverState, RaceState
from pitwall.engine.undercut import (
    _FULL_QUALITY_LAPS,
    _TRAFFIC_GAP_MS,
    CONFIDENCE_THRESHOLD,
    _data_quality_factor,
    evaluate_undercut,
)

# ---------------------------------------------------------------------------
# data_quality_factor
# ---------------------------------------------------------------------------


def test_data_quality_factor_is_one_for_full_quality_stint() -> None:
    atk = DriverState("A", laps_in_stint=_FULL_QUALITY_LAPS, gap_to_ahead_ms=5_000)
    assert _data_quality_factor(atk) == 1.0


def test_data_quality_factor_is_one_for_more_than_full_quality_laps() -> None:
    atk = DriverState("A", laps_in_stint=30, gap_to_ahead_ms=5_000)
    assert _data_quality_factor(atk) == 1.0


def test_data_quality_factor_scales_linearly_for_short_stint() -> None:
    for laps in range(3, _FULL_QUALITY_LAPS):
        atk = DriverState("A", laps_in_stint=laps, gap_to_ahead_ms=5_000)
        expected = laps / _FULL_QUALITY_LAPS
        assert abs(_data_quality_factor(atk) - expected) < 1e-9, (
            f"laps={laps}: expected {expected:.4f}, got {_data_quality_factor(atk):.4f}"
        )


def test_data_quality_factor_reduces_for_traffic() -> None:
    # Full-quality stint, but very close gap
    atk = DriverState("A", laps_in_stint=20, gap_to_ahead_ms=_TRAFFIC_GAP_MS - 1)
    factor = _data_quality_factor(atk)
    assert factor < 1.0
    assert abs(factor - 0.8) < 1e-9  # 1.0 - 0.2


def test_data_quality_factor_no_traffic_penalty_at_boundary() -> None:
    # Exactly at _TRAFFIC_GAP_MS → no penalty
    atk = DriverState("A", laps_in_stint=20, gap_to_ahead_ms=_TRAFFIC_GAP_MS)
    assert _data_quality_factor(atk) == 1.0


def test_data_quality_factor_clamped_to_zero() -> None:
    # Short stint (3 laps) + traffic → factor = 3/8 - 0.2 = 0.175, never negative
    atk = DriverState("A", laps_in_stint=3, gap_to_ahead_ms=500)
    factor = _data_quality_factor(atk)
    assert 0.0 <= factor <= 1.0
    assert factor < 0.5


def test_data_quality_factor_no_gap_does_not_trigger_traffic() -> None:
    # gap_to_ahead_ms is None → no traffic penalty
    atk = DriverState("A", laps_in_stint=20, gap_to_ahead_ms=None)
    assert _data_quality_factor(atk) == 1.0


# ---------------------------------------------------------------------------
# data_quality_factor applied inside evaluate_undercut
# ---------------------------------------------------------------------------


def _viable_pred() -> ScipyPredictor:
    return ScipyPredictor(
        [
            ScipyCoefficient("monaco", "MEDIUM", 74_500.0, 250.0, 8.0, 0.9),
            ScipyCoefficient("monaco", "HARD", 74_000.0, 80.0, 2.0, 0.85),
        ]
    )


def _state() -> RaceState:
    return RaceState(session_id="t", circuit_id="monaco")


def test_confidence_reduced_for_short_stint_attacker() -> None:
    pred = _viable_pred()
    state = _state()

    # Attacker with only 3 laps in stint → quality factor = 3/8
    atk_short = DriverState(
        driver_code="ATK", position=2, compound="MEDIUM",
        tyre_age=3, laps_in_stint=3, gap_to_ahead_ms=3_000,
    )
    def_ = DriverState(
        driver_code="DEF", position=1, compound="MEDIUM",
        tyre_age=25, laps_in_stint=25,
    )

    # Attacker with 20 laps → quality factor = 1.0
    atk_full = DriverState(
        driver_code="ATK", position=2, compound="MEDIUM",
        tyre_age=20, laps_in_stint=20, gap_to_ahead_ms=3_000,
    )

    d_short = evaluate_undercut(state, atk_short, def_, pred)
    d_full = evaluate_undercut(state, atk_full, def_, pred)

    assert d_short.confidence < d_full.confidence, (
        f"Short stint should have lower confidence: {d_short.confidence} vs {d_full.confidence}"
    )


def test_confidence_reduced_for_traffic() -> None:
    pred = _viable_pred()
    state = _state()

    base_atk = DriverState(
        driver_code="ATK", position=2, compound="MEDIUM",
        tyre_age=20, laps_in_stint=20, gap_to_ahead_ms=8_000,  # no traffic
    )
    traffic_atk = DriverState(
        driver_code="ATK", position=2, compound="MEDIUM",
        tyre_age=20, laps_in_stint=20, gap_to_ahead_ms=800,   # traffic!
    )
    def_ = DriverState(
        driver_code="DEF", position=1, compound="MEDIUM",
        tyre_age=25, laps_in_stint=25,
    )

    d_base = evaluate_undercut(state, base_atk, def_, pred)
    d_traffic = evaluate_undercut(state, traffic_atk, def_, pred)

    assert d_traffic.confidence < d_base.confidence


def test_low_quality_factor_suppresses_alert() -> None:
    """Short stint + traffic together can push confidence below threshold."""
    pred = _viable_pred()
    state = _state()

    # 3 laps + traffic → factor = 3/8 - 0.2 = 0.175
    # min(0.9, 0.85) * 0.175 ≈ 0.149 < CONFIDENCE_THRESHOLD
    atk = DriverState(
        driver_code="ATK", position=2, compound="MEDIUM",
        tyre_age=3, laps_in_stint=3, gap_to_ahead_ms=500,
    )
    def_ = DriverState(
        driver_code="DEF", position=1, compound="MEDIUM",
        tyre_age=25, laps_in_stint=25,
    )

    d = evaluate_undercut(state, atk, def_, pred)
    assert d.confidence < CONFIDENCE_THRESHOLD
    assert d.should_alert is False


# ---------------------------------------------------------------------------
# calibrate_cold_tyre_penalties
# ---------------------------------------------------------------------------


def test_calibration_empty_input_returns_zeros() -> None:
    result = calibrate_cold_tyre_penalties([], n_penalty_laps=3)
    assert result == (0, 0, 0)


def test_calibration_single_observation() -> None:
    result = calibrate_cold_tyre_penalties([[800, 300, 0]], n_penalty_laps=3)
    assert result == (800, 300, 0)


def test_calibration_median_of_multiple_observations() -> None:
    data = [[800, 300, 0], [900, 280, 10], [750, 320, 5]]
    result = calibrate_cold_tyre_penalties(data, n_penalty_laps=3)
    # Medians: [800, 300, 5]
    assert result == (800, 300, 5)


def test_calibration_shorter_observations_fill_with_zero() -> None:
    data = [[800], [900]]  # only 1 lap recorded
    result = calibrate_cold_tyre_penalties(data, n_penalty_laps=3)
    assert result[0] in (800, 850)  # median of [800, 900]
    assert result[1] == 0
    assert result[2] == 0


def test_calibration_negative_deltas_clamped_to_zero() -> None:
    data = [[-50, -20, 0]]  # Negative = attacker was faster than baseline
    result = calibrate_cold_tyre_penalties(data, n_penalty_laps=3)
    assert result == (0, 0, 0)


def test_calibration_returns_correct_length() -> None:
    data = [[800, 300, 0, 10, 5]]
    for n in [1, 2, 3, 4, 5, 6]:
        result = calibrate_cold_tyre_penalties(data, n_penalty_laps=n)
        assert len(result) == n


# ---------------------------------------------------------------------------
# project_pace with custom cold_tyre_penalties
# ---------------------------------------------------------------------------


def _flat_pred(lap_ms: int = 74_000) -> ScipyPredictor:
    return ScipyPredictor([ScipyCoefficient("monaco", "HARD", float(lap_ms), 0.0, 0.0, 0.8)])


def test_custom_penalties_override_module_default() -> None:
    pred = _flat_pred(74_000)
    custom = (1_200, 600, 100)  # different from default (800, 300, 0)

    penalised = project_pace(
        "A", "monaco", "HARD", 0, 3, pred,
        apply_cold_tyre_penalty=True,
        cold_tyre_penalties=custom,
    )
    no_penalty = project_pace("A", "monaco", "HARD", 0, 3, pred,
                              apply_cold_tyre_penalty=False)

    assert penalised[0] == no_penalty[0] + 1_200
    assert penalised[1] == no_penalty[1] + 600
    assert penalised[2] == no_penalty[2] + 100


def test_default_penalties_unchanged_when_none_passed() -> None:
    pred = _flat_pred(74_000)

    with_default = project_pace("A", "monaco", "HARD", 0, 3, pred,
                                apply_cold_tyre_penalty=True)
    with_explicit = project_pace("A", "monaco", "HARD", 0, 3, pred,
                                 apply_cold_tyre_penalty=True,
                                 cold_tyre_penalties=COLD_TYRE_PENALTIES_MS)

    assert with_default == with_explicit


def test_custom_empty_penalties_means_no_penalty() -> None:
    pred = _flat_pred(74_000)
    no_pen = project_pace("A", "monaco", "HARD", 0, 3, pred,
                          apply_cold_tyre_penalty=False)
    custom_empty = project_pace("A", "monaco", "HARD", 0, 3, pred,
                                apply_cold_tyre_penalty=True,
                                cold_tyre_penalties=())
    assert custom_empty == no_pen


def test_calibrate_then_apply_roundtrip() -> None:
    """Calibrate from data, pass to project_pace, verify the right penalties apply."""
    data = [[900, 350, 50], [800, 250, 30]]
    penalties = calibrate_cold_tyre_penalties(data, n_penalty_laps=3)
    pred = _flat_pred(74_000)

    flat = project_pace("A", "monaco", "HARD", 0, 3, pred, apply_cold_tyre_penalty=False)
    penalised = project_pace("A", "monaco", "HARD", 0, 3, pred,
                             apply_cold_tyre_penalty=True,
                             cold_tyre_penalties=penalties)

    for i in range(3):
        assert penalised[i] == flat[i] + penalties[i]


# ---------------------------------------------------------------------------
# Backtest API endpoint
# ---------------------------------------------------------------------------


def test_backtest_endpoint_returns_404_stub() -> None:
    from fastapi.testclient import TestClient

    from pitwall.api.main import create_app

    app = create_app()
    with TestClient(app) as client:
        r = client.get("/api/v1/backtest/monaco_2024_R")
    assert r.status_code == 404
    assert "monaco_2024_R" in r.json()["detail"]


def test_backtest_endpoint_with_predictor_param_returns_404() -> None:
    from fastapi.testclient import TestClient

    from pitwall.api.main import create_app

    app = create_app()
    with TestClient(app) as client:
        r = client.get("/api/v1/backtest/bahrain_2024_R?predictor=scipy")
    assert r.status_code == 404


def test_backtest_invalid_predictor_param_returns_422() -> None:
    from fastapi.testclient import TestClient

    from pitwall.api.main import create_app

    app = create_app()
    with TestClient(app) as client:
        r = client.get("/api/v1/backtest/monaco_2024_R?predictor=lstm")
    assert r.status_code == 422
