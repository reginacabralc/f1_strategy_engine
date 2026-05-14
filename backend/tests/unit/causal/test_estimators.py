"""Tests for DoWhy estimator preparation helpers."""

from __future__ import annotations

import pandas as pd
import pytest

from pitwall.causal.estimators import (
    EffectSpec,
    _backdoor_gml_for_frame,
    _prepare_frame,
    _refuted_value,
    _stability_label,
    default_effect_specs,
)


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


def test_prepare_frame_handles_nullable_object_booleans() -> None:
    data = pd.DataFrame(
        {
            "fresh_tyre_advantage_ms": [1000, 2000, 3000],
            "undercut_viable": [True, False, None],
            "rainfall": [False, None, True],
        },
        dtype=object,
    )

    frame = _prepare_frame(
        data,
        EffectSpec(
            treatment="fresh_tyre_advantage_ms",
            outcome="undercut_viable",
            common_causes=("rainfall",),
        ),
    )

    assert frame["undercut_viable"].tolist() == [1]
    assert frame["rainfall"].tolist() == [0]


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


def test_default_effect_specs_cover_phase_7_treatments() -> None:
    treatments = {spec.treatment for spec in default_effect_specs()}

    assert treatments == {
        "fresh_tyre_advantage_ms",
        "gap_to_rival_ms",
        "tyre_age_delta",
    }


def test_refuted_value_and_stability_labels() -> None:
    class _Refutation:
        new_effect = 0.11

    assert _refuted_value(_Refutation()) == 0.11
    assert _stability_label(0.10, 0.11) == "stable"
    assert _stability_label(0.10, 0.17) == "sensitive"
    assert _stability_label(0.10, 0.30) == "unstable"
    assert _stability_label(0.10, None) == "unsupported"
