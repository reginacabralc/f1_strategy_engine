"""Tests for project_pace() and COLD_TYRE_PENALTIES_MS."""

from __future__ import annotations

import pytest

from pitwall.degradation.predictor import ScipyCoefficient, ScipyPredictor
from pitwall.engine.projection import (
    COLD_TYRE_PENALTIES_MS,
    UnsupportedContextError,
    project_pace,
)


def _predictor() -> ScipyPredictor:
    return ScipyPredictor(
        [
            ScipyCoefficient("monaco", "MEDIUM", a=80_000.0, b=200.0, c=4.0, r_squared=0.8),
            ScipyCoefficient("monaco", "HARD", a=79_000.0, b=120.0, c=2.0, r_squared=0.75),
        ]
    )


def test_project_pace_defender_projects_k_laps_forward() -> None:
    pred = _predictor()
    times = project_pace("VER", "monaco", "MEDIUM", start_age=20, k=3, predictor=pred)

    assert len(times) == 3
    # a + b*(20+j) + c*(20+j)² for j=1,2,3
    # j=1: 80000 + 200*21 + 4*441 = 80000 + 4200 + 1764 = 85964
    assert times[0] == 85_964
    # j=2: 80000 + 200*22 + 4*484 = 80000 + 4400 + 1936 = 86336
    assert times[1] == 86_336
    # j=3: 80000 + 200*23 + 4*529 = 80000 + 4600 + 2116 = 86716
    assert times[2] == 86_716


def test_project_pace_without_penalty_ignores_cold_tyre() -> None:
    pred = _predictor()
    times = project_pace(
        "VER",
        "monaco",
        "MEDIUM",
        start_age=5,
        k=2,
        predictor=pred,
        apply_cold_tyre_penalty=False,
    )
    # No penalty added — raw quadratic output
    assert times[0] == 80_000 + 200 * 6 + 4 * 36  # = 81344
    assert times[1] == 80_000 + 200 * 7 + 4 * 49  # = 81596


def test_project_pace_with_cold_tyre_adds_penalties() -> None:
    pred = _predictor()
    times = project_pace(
        "NOR",
        "monaco",
        "HARD",
        start_age=0,
        k=3,
        predictor=pred,
        apply_cold_tyre_penalty=True,
    )
    # j=1: base(1) + COLD_TYRE_PENALTIES_MS[0]
    base_j1 = 79_000 + 120 * 1 + 2 * 1  # = 79122
    assert times[0] == base_j1 + COLD_TYRE_PENALTIES_MS[0]  # +800

    # j=2: base(2) + COLD_TYRE_PENALTIES_MS[1]
    base_j2 = 79_000 + 120 * 2 + 2 * 4  # = 79248
    assert times[1] == base_j2 + COLD_TYRE_PENALTIES_MS[1]  # +300

    # j=3: base(3) + 0 (no more penalty)
    base_j3 = 79_000 + 120 * 3 + 2 * 9  # = 79378
    assert times[2] == base_j3


def test_project_pace_raises_on_missing_coefficients() -> None:
    pred = ScipyPredictor([])
    with pytest.raises(UnsupportedContextError):
        project_pace("VER", "monaco", "SOFT", start_age=5, k=1, predictor=pred)


def test_cold_tyre_penalties_constants() -> None:
    # Verify the three published values match the documented spec.
    assert COLD_TYRE_PENALTIES_MS[0] == 800
    assert COLD_TYRE_PENALTIES_MS[1] == 300
    assert COLD_TYRE_PENALTIES_MS[2] == 0
