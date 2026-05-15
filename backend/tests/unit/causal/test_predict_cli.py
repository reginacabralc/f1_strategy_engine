"""Regression tests for the predict_causal_undercut.py CLI adapter.

Two regression fixtures verify the full structural-equation path:

Fixture 1 — VIABLE: LEC (MEDIUM age 30) chasing VER (HARD age 40) at Bahrain
lap 30, gap 500 ms, pit_loss 22 000 ms.

    Mathematics:
    - Defender pace at age 40: a_HARD + 150*40 + 5*1600 = a + 14 000 ms slower
    - Attacker fresh HARD pace at age 1:  a_HARD + 150 + 5 = a + 155 ms slower
    - Per-lap differential ≈ 13 845 ms/lap; over 5 laps: ~69 225 ms
    - Cold-tyre penalty on fresh laps 1-2 reduces this somewhat
    - gap_recuperable ≈ 74 900 ms
    - required_gain = gap(500) + pit_loss(22 000) + margin(500) = 23 000 ms
    - projected_gain_ms = estimated_gain_ms + pit_loss = 74 900 ms >> 23 000 ms
    - undercut_viable = True ✓

Fixture 2 — NOT VIABLE: SAR (HARD age 11) chasing HUL (HARD age 1) at Bahrain
lap 21, gap 56 000 ms, pit_loss 26 000 ms.

    Mathematics:
    - required_gain = 56 000 + 26 000 + 500 = 82 500 ms
    - Defender at HARD age 1 is essentially fresh → tiny per-lap differential
    - Even with high wear coefficients, 5 laps cannot close 82 500 ms
    - undercut_viable = False ✓

The coefficients in the test predictor are intentionally higher than real-world
Bahrain 2024 values (b=150-200 ms/lap vs ~45-60 ms/lap in the demo DB) because
the demo DB coefficients are fitted on 3 demo races and tend to underestimate
degradation. The exaggerated coefficients make the fixtures deterministic and
clearly illustrate the structural-equation logic.
"""

from __future__ import annotations

import pytest

from pitwall.causal.live_inference import CausalLiveResult, evaluate_causal_live
from pitwall.degradation.predictor import ScipyCoefficient, ScipyPredictor
from pitwall.engine.state import DriverState, RaceState


# ---------------------------------------------------------------------------
# Shared test predictor
# ---------------------------------------------------------------------------

def _test_predictor() -> ScipyPredictor:
    """Three-compound predictor with exaggerated wear for deterministic tests.

    The engine projects fresh-tyre pace using the *next* compound
    (SOFT→MEDIUM, MEDIUM→HARD, HARD→MEDIUM), so all three dry compounds
    must be present for any prediction involving SOFT or MEDIUM current tyres.

    Coefficients are higher than real-world fits to create large, unambiguous
    per-lap differentials that make the structural equations clearly viable or
    clearly not-viable regardless of small floating-point variation.
    """
    return ScipyPredictor(
        [
            ScipyCoefficient(
                "bahrain",
                "SOFT",
                a=94_000.0,
                b=120.0,
                c=3.5,
                r_squared=0.82,
            ),
            ScipyCoefficient(
                "bahrain",
                "MEDIUM",
                a=95_000.0,
                b=200.0,   # exaggerated: 200 ms/lap linear wear
                c=8.0,     # exaggerated: 8 ms/lap² quadratic
                r_squared=0.80,
            ),
            ScipyCoefficient(
                "bahrain",
                "HARD",
                a=95_500.0,
                b=150.0,   # exaggerated: 150 ms/lap linear wear
                c=5.0,     # exaggerated: 5 ms/lap² quadratic
                r_squared=0.75,
            ),
        ]
    )


def _bahrain_state(lap: int = 30) -> RaceState:
    return RaceState(
        session_id="bahrain_2024_R",
        circuit_id="bahrain",
        total_laps=57,
        current_lap=lap,
        track_status="GREEN",
        track_temp_c=38.0,
        air_temp_c=28.0,
        rainfall=False,
    )


# ---------------------------------------------------------------------------
# Fixture 1 — VIABLE: LEC (MEDIUM age 30) vs VER (HARD age 40), gap 500 ms
#
# Worn HARD at age 40 is dramatically slower than fresh HARD at age 1.
# With b=150 and c=5:
#   age 40 pace: a + 150*40 + 5*1600 = a + 14 000 ms above base
#   age  1 pace: a + 150   + 5*1   = a +   155 ms above base
# Differential ≈ 13 845 ms/lap → 5-lap window ≈ 69 000+ ms recuperable gap.
# pit_loss = 22 000 ms; required_gain = 500 + 22 000 + 500 = 23 000 ms.
# projected_gain >> required_gain → undercut_viable = True.
# ---------------------------------------------------------------------------

def _lec_viable() -> DriverState:
    return DriverState(
        driver_code="LEC",
        team_code="ferrari",
        position=2,
        gap_to_ahead_ms=500,
        compound="MEDIUM",
        tyre_age=30,
        laps_in_stint=30,
    )


def _ver_viable() -> DriverState:
    return DriverState(
        driver_code="VER",
        team_code="red_bull",
        position=1,
        compound="HARD",
        tyre_age=40,
        laps_in_stint=40,
    )


# ---------------------------------------------------------------------------
# Fixture 2 — NOT VIABLE: SAR (HARD age 11) vs HUL (HARD age 1), gap 56 000 ms
#
# Defender is near-fresh (age 1) → tiny per-lap pace advantage for attacker.
# required_gain = 56 000 + 26 000 + 500 = 82 500 ms.
# Even with exaggerated coefficients, 5 laps cannot recuperate 82 500 ms.
# ---------------------------------------------------------------------------

def _sar_not_viable() -> DriverState:
    return DriverState(
        driver_code="SAR",
        team_code="williams",
        position=2,
        gap_to_ahead_ms=56_000,
        compound="HARD",
        tyre_age=11,
        laps_in_stint=11,
    )


def _hul_not_viable() -> DriverState:
    return DriverState(
        driver_code="HUL",
        team_code="haas",
        position=1,
        compound="HARD",
        tyre_age=1,
        laps_in_stint=1,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_viable_fixture_lec_ver_large_tyre_age_delta() -> None:
    """LEC on worn MEDIUM is viable against VER on very worn HARD (age delta 10).

    The 5-lap projected gain (~74 900 ms) far exceeds the required gain
    (500 + 22 000 + 500 = 23 000 ms).  The structural-equation path must
    conclude undercut_viable = True.
    """
    result: CausalLiveResult = evaluate_causal_live(
        _bahrain_state(lap=30),
        _lec_viable(),
        _ver_viable(),
        _test_predictor(),
        pit_loss_ms=22_000,
    )

    assert result.observation.attacker_code == "LEC"
    assert result.observation.defender_code == "VER"
    assert result.observation.gap_to_rival_ms == 500
    assert result.observation.tyre_age_delta == 10  # VER age 40 - LEC age 30

    # Core viability result
    assert result.undercut_viable is True
    assert result.support_level in {"strong", "weak"}
    assert result.required_gain_ms is not None
    assert result.projected_gain_ms is not None
    assert result.projected_gain_ms >= result.required_gain_ms

    # Counterfactuals must cover the full scenario set
    scenario_names = {cf.scenario_name for cf in result.counterfactuals}
    assert scenario_names == {
        "base_case",
        "pit_now",
        "pit_next_lap",
        "pit_now_high_traffic",
        "pit_now_low_traffic",
        "pit_loss_minus_1000_ms",
        "pit_loss_plus_1000_ms",
    }

    # Explanations must reference the fresh-tyre gain result
    assert any("projected fresh-tyre gain" in e for e in result.explanations)

    # Top factors: projected_gap_after_pit_ms must be first when viable
    assert result.top_factors[0] == "projected_gap_after_pit_ms"
    assert "gap_to_rival_ms" in result.top_factors


def test_not_viable_fixture_sar_hul_large_gap() -> None:
    """SAR cannot undercut HUL when trailing by 56 seconds.

    required_gain = 56 000 + 26 000 + 500 = 82 500 ms.  No 5-lap tyre
    advantage can close 82 500 ms regardless of degradation rates.  The
    structural-equation path must return undercut_viable = False.
    """
    result: CausalLiveResult = evaluate_causal_live(
        _bahrain_state(lap=21),
        _sar_not_viable(),
        _hul_not_viable(),
        _test_predictor(),
        pit_loss_ms=26_000,
    )

    assert result.observation.attacker_code == "SAR"
    assert result.observation.gap_to_rival_ms == 56_000

    assert result.undercut_viable is False
    if result.required_gain_ms is not None and result.projected_gain_ms is not None:
        assert result.projected_gain_ms < result.required_gain_ms

    # Explanation must indicate not viable
    assert any(
        "not viable" in e or "not supported" in e or "below" in e
        for e in result.explanations
    )


def test_missing_gap_returns_insufficient_support() -> None:
    """When gap_to_rival_ms is None, support must be insufficient and viable False."""
    no_gap = DriverState(
        driver_code="LEC",
        position=2,
        gap_to_ahead_ms=None,
        compound="MEDIUM",
        tyre_age=20,
        laps_in_stint=20,
    )
    result = evaluate_causal_live(
        _bahrain_state(lap=20),
        no_gap,
        _ver_viable(),
        _test_predictor(),
        pit_loss_ms=22_000,
    )

    assert result.undercut_viable is False
    assert result.support_level == "insufficient"
    assert result.required_gain_ms is None
    assert any("not contain enough" in e or "not supported" in e for e in result.explanations)


def test_confidence_and_top_factors_populated_for_viable() -> None:
    """Confidence and top_factors must be non-trivial for a well-supported viable pair."""
    result = evaluate_causal_live(
        _bahrain_state(lap=30),
        _lec_viable(),
        _ver_viable(),
        _test_predictor(),
        pit_loss_ms=22_000,
    )

    assert 0.0 <= result.confidence <= 1.0
    assert len(result.top_factors) >= 2
    # projected_gap_after_pit_ms is first when viable and the gap is clearly negative
    assert result.top_factors[0] == "projected_gap_after_pit_ms"
