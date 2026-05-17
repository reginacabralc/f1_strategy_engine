"""Tests for replay-based Scipy/XGBoost backtest comparison."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest

from pitwall.engine.backtest import run_backtest
from pitwall.engine.projection import PaceContext, PacePrediction
from pitwall.feeds.base import Event

_TS = datetime(2024, 5, 26, 13, 0, 0, tzinfo=UTC)


class _UndercutPredictor:
    def predict(self, ctx: PaceContext) -> PacePrediction:
        lap_ms = 90_000 if ctx.compound == "MEDIUM" else 72_000
        return PacePrediction(predicted_lap_time_ms=lap_ms, confidence=0.95)

    def is_available(self, circuit_id: str, compound: str) -> bool:
        return True


def _event(event_type: str, payload: dict[str, Any], offset: int) -> Event:
    return cast(
        Event,
        {
            "type": event_type,
            "session_id": "monaco_2024_R",
            "ts": _TS + timedelta(seconds=offset),
            "payload": payload,
        },
    )


def _lap(
    driver_code: str,
    lap_number: int,
    position: int,
    gap_to_ahead_ms: int | None,
    *,
    compound: str = "MEDIUM",
    tyre_age: int = 20,
    lap_time_ms: int = 80_000,
    is_pit_in: bool = False,
    offset: int = 0,
) -> Event:
    return _event(
        "lap_complete",
        {
            "driver_code": driver_code,
            "lap_number": lap_number,
            "position": position,
            "gap_to_ahead_ms": gap_to_ahead_ms,
            "gap_to_leader_ms": 0 if position == 1 else gap_to_ahead_ms,
            "compound": compound,
            "tyre_age": tyre_age,
            "lap_time_ms": lap_time_ms,
            "is_valid": True,
            "is_pit_in": is_pit_in,
            "is_pit_out": False,
            "track_status": "GREEN",
        },
        offset,
    )


def _session_events() -> list[Event]:
    events: list[Event] = [
        _event(
            "session_start",
            {"circuit_id": "monaco", "total_laps": 78, "drivers": ["LEC", "NOR"]},
            0,
        )
    ]
    offset = 1
    for lap in range(1, 9):
        events.append(_lap("LEC", lap, 1, None, tyre_age=24 + lap, offset=offset))
        offset += 1
        events.append(_lap("NOR", lap, 2, 2_000, tyre_age=lap + 8, offset=offset))
        offset += 1
    events.append(_lap("NOR", 9, 2, 1_800, tyre_age=17, is_pit_in=True, offset=offset))
    offset += 1
    events.append(_lap("LEC", 9, 1, None, tyre_age=33, offset=offset))
    offset += 1
    events.append(_lap("NOR", 12, 1, None, compound="HARD", tyre_age=2, offset=offset))
    offset += 1
    events.append(_lap("LEC", 12, 2, 1_500, tyre_age=36, offset=offset))
    return events


def test_run_backtest_matches_first_alert_to_actual_successful_undercut() -> None:
    result = run_backtest(
        "monaco_2024_R",
        _session_events(),
        _UndercutPredictor(),
        predictor_name="scipy",
        pit_loss_table={},
    )

    assert result.session_id == "monaco_2024_R"
    assert result.predictor == "scipy"
    assert result.precision == pytest.approx(1.0)
    assert result.recall == pytest.approx(1.0)
    assert result.f1 == pytest.approx(1.0)
    assert result.mean_lead_time_laps is not None
    assert result.true_positives[0].attacker == "NOR"
    assert result.true_positives[0].defender == "LEC"
    assert result.true_positives[0].lap_actual == 9
    assert result.mae_k1_ms is not None
    assert result.threshold_sweep
    default_row = next(
        row for row in result.threshold_sweep
        if row["score_threshold"] == 0.4 and row["confidence_threshold"] == 0.5
    )
    assert default_row["precision"] == pytest.approx(1.0)
    assert default_row["recall"] == pytest.approx(1.0)


def test_run_backtest_returns_zero_metrics_when_no_known_undercuts() -> None:
    events: list[Event] = [
        _event("session_start", {"circuit_id": "monaco", "total_laps": 78}, 0),
        _lap("LEC", 1, 1, None, offset=1),
    ]

    result = run_backtest(
        "monaco_2024_R",
        events,
        _UndercutPredictor(),
        predictor_name="xgboost",
        pit_loss_table={},
    )

    assert result.predictor == "xgboost"
    assert result.precision == 0.0
    assert result.recall == 0.0
    assert result.f1 == 0.0
    assert result.true_positives == []
    assert result.false_negatives == []


def test_run_backtest_does_not_count_unsuccessful_pit_stops_as_false_negatives() -> None:
    events = [
        _event(
            "session_start",
            {"circuit_id": "monaco", "total_laps": 78, "drivers": ["LEC", "NOR"]},
            0,
        ),
        _lap("LEC", 2, 1, None, offset=1),
        _lap("NOR", 2, 2, 2_000, is_pit_in=True, offset=2),
        _lap("LEC", 6, 1, None, offset=3),
        _lap("NOR", 6, 2, 2_000, compound="HARD", offset=4),
    ]

    result = run_backtest(
        "monaco_2024_R",
        events,
        _UndercutPredictor(),
        predictor_name="scipy",
        pit_loss_table={},
    )

    assert result.false_negatives == []
    assert result.recall == 0.0


def test_threshold_sweep_counts_confidence_suppressed_alerts() -> None:
    class _LowConfidencePredictor(_UndercutPredictor):
        def predict(self, ctx: PaceContext) -> PacePrediction:
            lap_ms = 90_000 if ctx.compound == "MEDIUM" else 72_000
            return PacePrediction(predicted_lap_time_ms=lap_ms, confidence=0.3)

    result = run_backtest(
        "monaco_2024_R",
        _session_events(),
        _LowConfidencePredictor(),
        predictor_name="xgboost",
        pit_loss_table={},
    )

    default_row = next(
        row for row in result.threshold_sweep
        if row["score_threshold"] == 0.4 and row["confidence_threshold"] == 0.5
    )
    assert default_row["suppressed_by_confidence"] > 0
