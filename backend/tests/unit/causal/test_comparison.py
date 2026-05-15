"""Tests for causal/scipy/xgb disagreement reporting."""

from __future__ import annotations

import pandas as pd

from pitwall.causal.comparison import build_disagreement_table, summarize_disagreements


def test_build_disagreement_table_marks_xgb_not_evaluated_without_column() -> None:
    data = pd.DataFrame(
        {
            "session_id": ["monaco_2024_R", "monaco_2024_R"],
            "lap_number": [10, 11],
            "attacker_code": ["NOR", "LEC"],
            "defender_code": ["VER", "NOR"],
            "undercut_viable": [True, False],
            "projected_gain_if_pit_now_ms": [40_000, 5_000],
            "pit_loss_estimate_ms": [20_000, 20_000],
            "gap_to_rival_ms": [2_000, 10_000],
            "pace_confidence": [0.8, 0.8],
        }
    )

    table = build_disagreement_table(data)
    summary = summarize_disagreements(table)

    assert table["xgb_status"].unique().tolist() == ["not_evaluated_in_dataset"]
    assert summary.row_count == 2
    assert summary.comparable_scipy_rows == 2
    assert summary.causal_vs_scipy_disagreements == 0
    assert summary.xgb_status == "not_evaluated_in_dataset"
    assert summary.causal_vs_xgb_disagreements is None


def test_build_disagreement_table_detects_causal_vs_scipy_disagreement() -> None:
    data = pd.DataFrame(
        {
            "session_id": ["monaco_2024_R"],
            "lap_number": [10],
            "attacker_code": ["NOR"],
            "defender_code": ["VER"],
            "undercut_viable": [True],
            "projected_gain_if_pit_now_ms": [22_000],
            "pit_loss_estimate_ms": [20_000],
            "gap_to_rival_ms": [2_000],
            "pace_confidence": [0.8],
        }
    )

    table = build_disagreement_table(data)

    assert bool(table.loc[0, "causal_scipy_decision"]) is True
    assert bool(table.loc[0, "scipy_engine_decision"]) is False
    assert bool(table.loc[0, "causal_vs_scipy_disagreement"]) is True
