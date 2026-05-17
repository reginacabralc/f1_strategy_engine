from __future__ import annotations

import json
from pathlib import Path

from pitwall.ml.tuning import (
    CandidateResult,
    SearchCandidate,
    candidate_search_space,
    load_selected_hyperparameters,
    load_selected_tuning_config,
    select_best_candidate,
)


def test_select_best_candidate_uses_mae_then_rmse_then_gap() -> None:
    candidates = [
        CandidateResult(
            candidate_id="wide_gap",
            hyperparameters={"max_depth": 5},
            num_boost_round=100,
            aggregate_metrics={
                "holdout_mae_ms": 900.0,
                "holdout_rmse_ms": 1200.0,
                "train_validation_gap_mae_ms": 800.0,
            },
            fold_metrics=[],
        ),
        CandidateResult(
            candidate_id="best",
            hyperparameters={"max_depth": 3},
            num_boost_round=100,
            aggregate_metrics={
                "holdout_mae_ms": 900.0,
                "holdout_rmse_ms": 1100.0,
                "train_validation_gap_mae_ms": 200.0,
            },
            fold_metrics=[],
        ),
        CandidateResult(
            candidate_id="worse_mae",
            hyperparameters={"max_depth": 4},
            num_boost_round=100,
            aggregate_metrics={
                "holdout_mae_ms": 950.0,
                "holdout_rmse_ms": 1000.0,
                "train_validation_gap_mae_ms": 50.0,
            },
            fold_metrics=[],
        ),
    ]

    selected = select_best_candidate(candidates)

    assert selected.candidate_id == "best"


def test_candidate_search_space_is_seeded_and_covers_objectives_and_rounds() -> None:
    first = candidate_search_space(n_random=8, seed=123, include_curated=False)
    second = candidate_search_space(n_random=8, seed=123, include_curated=False)

    assert first == second
    assert all(isinstance(candidate, SearchCandidate) for candidate in first)
    assert {candidate.hyperparameters["objective"] for candidate in first} >= {
        "reg:squarederror",
        "reg:absoluteerror",
        "reg:pseudohubererror",
    }
    assert len({candidate.num_boost_round for candidate in first}) > 1


def test_load_selected_tuning_config_returns_hyperparameters_and_rounds(tmp_path: Path) -> None:
    report_path = tmp_path / "xgb_tuning_report.json"
    report_path.write_text(
        json.dumps(
            {
                "selected_config": {
                    "hyperparameters": {"max_depth": 2, "eta": 0.02},
                    "num_boost_round": 100,
                }
            }
        )
    )

    assert load_selected_tuning_config(report_path) == (
        {"max_depth": 2, "eta": 0.02},
        100,
    )
    assert load_selected_hyperparameters(report_path) == {"max_depth": 2, "eta": 0.02}
