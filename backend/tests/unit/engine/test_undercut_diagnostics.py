"""Tests for undercut score, threshold, and label diagnostics."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest

from pitwall.engine.projection import PaceContext, PacePrediction
from pitwall.engine.state import DriverState, RaceState
from pitwall.engine.undercut_diagnostics import (
    DecisionRecord,
    LabelRecord,
    ThresholdConfig,
    UndercutDiagnosticConfig,
    audit_labels_against_decisions,
    collect_score_decompositions,
    decompose_undercut_decision,
    label_records_from_backtest_objects,
    score_threshold_config,
    sweep_thresholds,
)
from pitwall.feeds.base import Event


class _ConstantPredictor:
    def predict(self, ctx: PaceContext) -> PacePrediction:
        lap_ms = 91_000 if ctx.driver_code == "DEF" else 86_000
        return PacePrediction(predicted_lap_time_ms=lap_ms, confidence=0.90)

    def is_available(self, circuit_id: str, compound: str) -> bool:
        return True


def _state() -> RaceState:
    state = RaceState(session_id="test_R", circuit_id="monaco", total_laps=78, current_lap=20)
    state.drivers = {
        "DEF": DriverState(
            driver_code="DEF",
            team_code="team_a",
            position=1,
            gap_to_ahead_ms=None,
            gap_to_leader_ms=0,
            compound="MEDIUM",
            tyre_age=25,
            stint_number=1,
            laps_in_stint=25,
        ),
        "ATK": DriverState(
            driver_code="ATK",
            team_code="team_b",
            position=2,
            gap_to_ahead_ms=1_500,
            gap_to_leader_ms=1_500,
            compound="MEDIUM",
            tyre_age=12,
            stint_number=1,
            laps_in_stint=12,
        ),
    }
    return state


def test_score_decomposition_exposes_raw_score_terms() -> None:
    state = _state()
    config = UndercutDiagnosticConfig(k=3, margin_ms=500, score_threshold=0.4)

    row = decompose_undercut_decision(
        state,
        state.drivers["ATK"],
        state.drivers["DEF"],
        _ConstantPredictor(),
        pit_loss_ms=10_000,
        config=config,
    )

    assert row.gap_recuperable_ms == 13_900
    assert row.raw_score_ms == 1_900
    assert row.raw_score == pytest.approx(0.19)
    assert row.score == pytest.approx(0.19)
    assert row.should_alert is False
    assert row.insufficient_reason is None
    assert row.insufficient_detail is None
    assert row.suppressed_by_score is True
    assert row.suppressed_by_confidence is False


def test_margin_and_pit_loss_scaling_do_not_change_production_constants() -> None:
    state = _state()

    base = decompose_undercut_decision(
        state,
        state.drivers["ATK"],
        state.drivers["DEF"],
        _ConstantPredictor(),
        pit_loss_ms=10_000,
        config=UndercutDiagnosticConfig(k=3, margin_ms=500, pit_loss_scale=1.0),
    )
    scaled = decompose_undercut_decision(
        state,
        state.drivers["ATK"],
        state.drivers["DEF"],
        _ConstantPredictor(),
        pit_loss_ms=10_000,
        config=UndercutDiagnosticConfig(k=3, margin_ms=0, pit_loss_scale=0.8),
    )

    assert base.pit_loss_ms == 10_000
    assert scaled.pit_loss_ms == 8_000
    assert base.raw_score_ms == 1_900
    assert scaled.raw_score_ms == 4_400


def test_score_decomposition_records_insufficient_reason() -> None:
    state = _state()
    state.drivers["ATK"].gap_to_ahead_ms = None

    row = decompose_undercut_decision(
        state,
        state.drivers["ATK"],
        state.drivers["DEF"],
        _ConstantPredictor(),
    )

    assert row.alert_type == "INSUFFICIENT_DATA"
    assert row.insufficient_reason == "missing_gap_actual"
    assert row.insufficient_detail is None


def test_threshold_sweep_counts_alerts_and_suppression_reasons() -> None:
    labels = [LabelRecord(attacker="ATK", defender="DEF", lap_actual=12)]
    decisions = [
        DecisionRecord(
            attacker="ATK",
            defender="DEF",
            lap_number=10,
            score=0.50,
            confidence=0.70,
            estimated_gain_ms=2_000,
        ),
        DecisionRecord(
            attacker="AAA",
            defender="BBB",
            lap_number=10,
            score=0.60,
            confidence=0.20,
            estimated_gain_ms=1_500,
        ),
        DecisionRecord(
            attacker="CCC",
            defender="DDD",
            lap_number=10,
            score=0.10,
            confidence=0.90,
            estimated_gain_ms=500,
        ),
    ]

    row = sweep_thresholds(
        labels,
        decisions,
        configs=[
            ThresholdConfig(
                score_threshold=0.4,
                confidence_threshold=0.5,
                margin_ms=500,
                k=5,
                pit_loss_scale=1.0,
                cold_tyre_mode="current",
            )
        ],
    )[0]

    assert row.alerts == 1
    assert row.true_positives == 1
    assert row.false_positives == 0
    assert row.false_negatives == 0
    assert row.precision == pytest.approx(1.0)
    assert row.recall == pytest.approx(1.0)
    assert row.f1 == pytest.approx(1.0)
    assert row.suppressed_by_confidence == 1
    assert row.suppressed_by_score == 1


def test_zero_threshold_sweep_can_recover_positive_score_alerts() -> None:
    labels = [LabelRecord(attacker="ATK", defender="DEF", lap_actual=12)]
    decisions = [
        DecisionRecord(
            attacker="ATK",
            defender="DEF",
            lap_number=11,
            score=0.01,
            confidence=0.01,
            estimated_gain_ms=100,
        )
    ]

    row = sweep_thresholds(
        labels,
        decisions,
        configs=[
            ThresholdConfig(
                score_threshold=0.0,
                confidence_threshold=0.0,
                margin_ms=500,
                k=5,
                pit_loss_scale=1.0,
                cold_tyre_mode="current",
            )
        ],
    )[0]

    assert row.alerts == 1
    assert row.true_positives == 1


def test_label_audit_flags_labels_not_relevant_before_pit() -> None:
    labels = [
        LabelRecord(attacker="ATK", defender="DEF", lap_actual=20),
        LabelRecord(attacker="NOR", defender="LEC", lap_actual=30),
    ]
    decisions = [
        DecisionRecord(
            attacker="NOR",
            defender="LEC",
            lap_number=28,
            score=0.0,
            confidence=0.8,
            estimated_gain_ms=-20_000,
        )
    ]

    rows = audit_labels_against_decisions(labels, decisions, window_laps=5)
    by_pair = {(row.attacker, row.defender): row for row in rows}

    assert by_pair[("ATK", "DEF")].relevant_before_pit is False
    assert by_pair[("ATK", "DEF")].likely_unobservable_label is True
    assert by_pair[("NOR", "LEC")].relevant_before_pit is True
    assert by_pair[("NOR", "LEC")].exact_pair_decision_count == 1


def test_collect_score_decompositions_honors_max_rows() -> None:
    events = [
        _event("session_start", {"circuit_id": "monaco", "total_laps": 78}, 0),
        _lap_event("DEF", 1, 1, None, 1),
        _lap_event("ATK", 1, 2, 1_500, 2),
        _lap_event("DEF", 2, 1, None, 3),
        _lap_event("ATK", 2, 2, 1_500, 4),
    ]

    rows = collect_score_decompositions(events, _ConstantPredictor(), {}, max_rows=1)

    assert len(rows) == 1


def test_backtest_label_adapter_preserves_session_id() -> None:
    class _BacktestLabel:
        attacker = "ATK"
        defender = "DEF"
        lap_actual = 20
        was_successful = True

    labels = label_records_from_backtest_objects(
        [_BacktestLabel()],
        session_id="monaco_2024_R",
    )

    assert labels == [
        LabelRecord(
            attacker="ATK",
            defender="DEF",
            lap_actual=20,
            was_successful=True,
            source="backtest_final_position",
            session_id="monaco_2024_R",
        )
    ]


def _event(event_type: str, payload: dict[str, Any], offset: int) -> Event:
    return cast(
        Event,
        {
            "type": event_type,
            "session_id": "test_R",
            "ts": datetime(2024, 5, 26, 13, 0, tzinfo=UTC) + timedelta(seconds=offset),
            "payload": payload,
        },
    )


def _lap_event(
    driver_code: str,
    lap_number: int,
    position: int,
    gap_to_ahead_ms: int | None,
    offset: int,
) -> Event:
    return _event(
        "lap_complete",
        {
            "driver_code": driver_code,
            "lap_number": lap_number,
            "position": position,
            "gap_to_ahead_ms": gap_to_ahead_ms,
            "gap_to_leader_ms": gap_to_ahead_ms if position > 1 else 0,
            "compound": "MEDIUM",
            "tyre_age": 10 + lap_number,
            "lap_time_ms": 90_000,
            "is_valid": True,
            "is_pit_in": False,
            "is_pit_out": False,
            "track_status": "GREEN",
        },
        offset,
    )


def test_score_threshold_config_returns_production_defaults() -> None:
    config = score_threshold_config()

    assert config.k == 5
    assert config.margin_ms == 500
    assert config.score_threshold == pytest.approx(0.4)
    assert config.confidence_threshold == pytest.approx(0.5)
