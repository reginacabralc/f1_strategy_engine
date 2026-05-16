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


def test_stratified_effect_specs_returns_nonempty_list() -> None:
    """stratified_effect_specs must return specs covering gap and traffic treatments."""
    from pitwall.causal.estimators import stratified_effect_specs

    specs = stratified_effect_specs()
    assert len(specs) > 0
    # Must have circuit_filter field on each spec
    assert all(hasattr(spec, "circuit_filter") for spec in specs)
    # Must cover gap_to_rival_ms across multiple circuits
    gap_specs = [s for s in specs if s.treatment == "gap_to_rival_ms"]
    assert len(gap_specs) >= 2
    # Must cover nearest_traffic_gap_ms (numeric traffic proxy)
    traffic_specs = [s for s in specs if s.treatment == "nearest_traffic_gap_ms"]
    assert len(traffic_specs) >= 1


def test_estimate_stratified_effects_skips_small_circuits() -> None:
    """estimate_stratified_effects returns None for circuits with <200 rows."""
    import pandas as pd
    from pitwall.causal.estimators import (
        StratifiedEffectSpec,
        estimate_stratified_effects,
    )

    # Make a tiny dataframe that only has 10 rows for any circuit filter
    tiny_data = pd.DataFrame({
        "session_id": ["bahrain_2024_R"] * 10,
        "fresh_tyre_advantage_ms": range(10),
        "undercut_viable": [0, 1] * 5,
        "gap_to_rival_ms": range(1000, 1010),
        "nearest_traffic_gap_ms": range(500, 510),
        "lap_number": range(10),
        "laps_remaining": range(10),
        "current_position": [2] * 10,
        "rival_position": [1] * 10,
        "pit_loss_estimate_ms": [22000] * 10,
        "attacker_tyre_age": range(10),
        "defender_tyre_age": range(5, 15),
        "tyre_age_delta": range(10),
        "track_temp_c": [30.0] * 10,
        "air_temp_c": [25.0] * 10,
        "rainfall": [False] * 10,
    })
    specs = [
        StratifiedEffectSpec(
            treatment="gap_to_rival_ms",
            outcome="undercut_viable",
            circuit_filter="bahrain",
        )
    ]
    results = estimate_stratified_effects(tiny_data, specs)
    assert len(results) == 1
    spec, estimate = results[0]
    assert estimate is None  # < 200 rows → skipped
