from __future__ import annotations

import polars as pl
import pytest

from pitwall.ml.baselines import evaluate_baseline_ladder
from pitwall.ml.dataset import TARGET_COLUMN


def _row(
    fold_id: str,
    session_id: str,
    split: str,
    target: float,
    *,
    circuit_id: str = "bahrain",
    compound: str = "HARD",
    driver_code: str = "VER",
    team_code: str = "red_bull_racing",
    tyre_age: int = 5,
) -> dict[str, object]:
    return {
        "fold_id": fold_id,
        "session_id": session_id,
        "split": split,
        "circuit_id": circuit_id,
        "compound": compound,
        "driver_code": driver_code,
        "team_code": team_code,
        "tyre_age": tyre_age,
        "lap_number": tyre_age,
        "lap_in_stint": tyre_age,
        "race_progress": 0.25,
        "fuel_proxy": 0.75,
        "driver_pace_offset_ms": 0.0,
        "reference_lap_time_ms": 90_000.0,
        "row_usable": True,
        TARGET_COLUMN: target,
    }


def test_baseline_ladder_trains_only_on_fold_training_rows() -> None:
    frame = pl.DataFrame(
        [
            _row("fold_001", "train_a", "train", 100.0),
            _row("fold_001", "train_b", "train", 300.0),
            _row("fold_001", "future", "validation", 10_000.0, circuit_id="monaco"),
            _row("fold_001", "eval", "validation", 500.0),
        ]
    )
    metadata = {
        "folds": [
            {
                "fold_id": "fold_001",
                "train_session_ids": ["train_a", "train_b"],
                "validation_session_ids": ["future", "eval"],
            }
        ],
        "split_strategy": "temporal_expanding",
    }

    report = evaluate_baseline_ladder(frame, metadata)
    by_name = {row["baseline"]: row for row in report["aggregate_metrics"]}

    assert by_name["train_mean"]["mae_ms"] == pytest.approx(5_050.0)
    assert by_name["circuit_compound_median"]["mae_ms"] == pytest.approx(5_050.0)
    assert report["deferred_baselines"]["ridge_elasticnet_numeric"].startswith("scikit-learn")
