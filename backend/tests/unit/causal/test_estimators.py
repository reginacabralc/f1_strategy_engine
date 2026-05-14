"""Tests for DoWhy estimator preparation helpers."""

from __future__ import annotations

import pandas as pd
import pytest

from pitwall.causal.estimators import EffectSpec, _backdoor_gml_for_frame, _prepare_frame


def test_prepare_frame_keeps_required_columns_and_converts_booleans() -> None:
    data = pd.DataFrame(
        {
            "fresh_tyre_advantage_ms": [1000, 2000, None],
            "undercut_viable": [True, False, True],
            "lap_number": [10, 11, 12],
            "gap_to_rival_ms": [2000, 3000, 4000],
            "extra": ["ignored", "ignored", "ignored"],
        }
    )

    frame = _prepare_frame(
        data,
        EffectSpec(
            treatment="fresh_tyre_advantage_ms",
            outcome="undercut_viable",
            common_causes=("lap_number", "gap_to_rival_ms"),
        ),
    )

    assert list(frame.columns) == [
        "fresh_tyre_advantage_ms",
        "undercut_viable",
        "lap_number",
        "gap_to_rival_ms",
    ]
    assert len(frame) == 2
    assert frame["undercut_viable"].tolist() == [1, 0]


def test_prepare_frame_rejects_missing_columns() -> None:
    data = pd.DataFrame({"x": [1], "y": [1]})

    with pytest.raises(ValueError, match="missing required DoWhy column"):
        _prepare_frame(
            data,
            EffectSpec(treatment="x", outcome="missing", common_causes=()),
        )


def test_backdoor_gml_for_frame_contains_only_observed_estimate_columns() -> None:
    data = pd.DataFrame(
        {
            "fresh_tyre_advantage_ms": [1000],
            "undercut_viable": [1],
            "gap_to_rival_ms": [2000],
        }
    )

    graph = _backdoor_gml_for_frame(
        data,
        EffectSpec(
            treatment="fresh_tyre_advantage_ms",
            outcome="undercut_viable",
            common_causes=("gap_to_rival_ms",),
        ),
    )

    assert 'label "fresh_tyre_advantage_ms"' in graph
    assert 'label "undercut_viable"' in graph
    assert 'label "gap_to_rival_ms"' in graph
    assert "attacker_degradation_estimate" not in graph
