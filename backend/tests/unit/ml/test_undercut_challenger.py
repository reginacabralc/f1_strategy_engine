from __future__ import annotations

import polars as pl
import pytest

from pitwall.ml.undercut_challenger import (
    PairLevelMetrics,
    build_temporal_session_split,
    classification_metrics,
)


def _row(
    session_id: str,
    season: int,
    label: bool,
    *,
    success: bool | None = None,
) -> dict[str, object]:
    return {
        "session_id": session_id,
        "season": season,
        "lap_number": 10,
        "total_laps": 60,
        "laps_remaining": 50,
        "race_phase": "early",
        "circuit_id": "bahrain",
        "attacker_code": "NOR",
        "defender_code": "VER",
        "attacker_team_code": "mclaren",
        "defender_team_code": "red_bull_racing",
        "current_position": 2,
        "rival_position": 1,
        "gap_to_rival_ms": 1200,
        "attacker_compound": "MEDIUM",
        "defender_compound": "HARD",
        "attacker_next_compound": "HARD",
        "attacker_tyre_age": 12,
        "defender_tyre_age": 25,
        "tyre_age_delta": 13,
        "attacker_laps_in_stint": 12,
        "defender_laps_in_stint": 25,
        "track_temp_c": 38.0,
        "air_temp_c": 28.0,
        "pit_loss_estimate_ms": 21_000,
        "traffic_after_pit_cars": 0,
        "nearest_traffic_gap_ms": 5000,
        "fresh_tyre_advantage_ms": 900,
        "projected_gain_if_pit_now_ms": 24_000,
        "required_gain_to_clear_rival_ms": 22_700,
        "projected_gap_after_pit_ms": -1300,
        "pace_confidence": 0.4,
        "traffic_after_pit": "low",
        "clean_air_potential": "high",
        "undercut_viable": label,
        "undercut_success": success,
        "row_usable": True,
    }


def test_temporal_session_split_keeps_sessions_disjoint() -> None:
    frame = pl.DataFrame(
        [
            _row("bahrain_2024_R", 2024, True),
            _row("monaco_2024_R", 2024, False),
            _row("australian_2025_R", 2025, True),
            _row("monaco_2025_R", 2025, False),
        ]
    )

    split = build_temporal_session_split(frame, validation_fraction=0.5)

    assert set(split.train_sessions).isdisjoint(split.validation_sessions)
    assert split.train.height == 2
    assert split.validation.height == 2


def test_classification_metrics_reports_pr_auc_and_brier() -> None:
    metrics = classification_metrics(
        y_true=[True, False, True, False],
        probabilities=[0.9, 0.7, 0.8, 0.1],
        threshold=0.5,
    )

    assert isinstance(metrics, PairLevelMetrics)
    assert metrics.precision == pytest.approx(2 / 3)
    assert metrics.recall == pytest.approx(1.0)
    assert metrics.f1 == pytest.approx(0.8)
    assert metrics.brier_score == pytest.approx((0.1**2 + 0.7**2 + 0.2**2 + 0.1**2) / 4)
    assert metrics.pr_auc is not None
