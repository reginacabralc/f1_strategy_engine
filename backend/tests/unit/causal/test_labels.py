"""Tests for causal undercut viability label construction."""

from __future__ import annotations

from pitwall.causal.labels import (
    DegradationCurve,
    ViabilityInputs,
    compute_undercut_viability_label,
)


def _curves() -> dict[tuple[str, str], DegradationCurve]:
    return {
        ("monaco", "MEDIUM"): DegradationCurve("monaco", "MEDIUM", 80_000, 200, 0, 0.8),
        ("monaco", "HARD"): DegradationCurve("monaco", "HARD", 78_000, 20, 0, 0.7),
    }


def test_viability_label_true_when_projected_gain_clears_required_gain() -> None:
    label = compute_undercut_viability_label(
        ViabilityInputs(
            circuit_id="monaco",
            attacker_compound="MEDIUM",
            defender_compound="MEDIUM",
            attacker_tyre_age=15,
            defender_tyre_age=30,
            gap_to_rival_ms=2_000,
            pit_loss_estimate_ms=10_000,
            track_status="GREEN",
            rainfall=False,
        ),
        _curves(),
    )

    assert label.row_usable is True
    assert label.undercut_viable is True
    assert label.undercut_window_open is True
    assert label.next_compound == "HARD"
    assert label.pace_delta_to_rival_ms == 3_000
    assert label.required_gain_to_clear_rival_ms == 12_500
    assert label.projected_gain_if_pit_now_ms is not None
    assert label.projected_gap_after_pit_ms is not None
    assert label.projected_gap_after_pit_ms <= 0


def test_viability_label_false_when_required_gain_is_too_large() -> None:
    label = compute_undercut_viability_label(
        ViabilityInputs(
            circuit_id="monaco",
            attacker_compound="MEDIUM",
            defender_compound="MEDIUM",
            attacker_tyre_age=15,
            defender_tyre_age=30,
            gap_to_rival_ms=25_000,
            pit_loss_estimate_ms=25_000,
            track_status="GREEN",
            rainfall=False,
        ),
        _curves(),
    )

    assert label.row_usable is True
    assert label.undercut_viable is False
    assert label.undercut_window_open is False


def test_viability_label_marks_non_green_as_unusable() -> None:
    label = compute_undercut_viability_label(
        ViabilityInputs(
            circuit_id="monaco",
            attacker_compound="MEDIUM",
            defender_compound="MEDIUM",
            attacker_tyre_age=15,
            defender_tyre_age=30,
            gap_to_rival_ms=2_000,
            pit_loss_estimate_ms=10_000,
            track_status="SC",
            rainfall=False,
        ),
        _curves(),
    )

    assert label.row_usable is False
    assert label.undercut_viable is None
    assert label.missing_reason == "non_green_track_status"


def test_viability_label_does_not_support_wet_compounds() -> None:
    label = compute_undercut_viability_label(
        ViabilityInputs(
            circuit_id="monaco",
            attacker_compound="INTER",
            defender_compound="MEDIUM",
            attacker_tyre_age=15,
            defender_tyre_age=30,
            gap_to_rival_ms=2_000,
            pit_loss_estimate_ms=10_000,
            track_status="GREEN",
            rainfall=False,
        ),
        _curves(),
    )

    assert label.row_usable is False
    assert label.missing_reason == "unsupported_attacker_compound"


def test_degradation_lookup_adds_global_compound_fallback() -> None:
    from pitwall.causal.labels import build_degradation_lookup

    lookup = build_degradation_lookup(
        [
            {"circuit_id": "a", "compound": "HARD", "a": 1, "b": 2, "c": 3, "r_squared": 0.2},
            {"circuit_id": "b", "compound": "HARD", "a": 3, "b": 4, "c": 5, "r_squared": 0.6},
        ]
    )

    assert lookup[("__global__", "HARD")].a == 2
    assert lookup[("__global__", "HARD")].confidence == 0.4
