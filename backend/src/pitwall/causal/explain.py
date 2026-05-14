"""Human-readable explanations for causal undercut decisions."""

from __future__ import annotations

from collections.abc import Sequence


def explain_base_decision(
    *,
    undercut_viable: bool,
    support_level: str,
    gap_to_rival_ms: int | None,
    required_gain_ms: int | None,
    projected_gain_ms: int | None,
    projected_gap_after_pit_ms: int | None,
    traffic_after_pit: str,
    tyre_age_delta: int | None,
    confidence: float,
) -> list[str]:
    """Return compact explanation bullets for one live causal prediction."""

    reasons: list[str] = []
    if required_gain_ms is None or projected_gain_ms is None:
        return [
            "Undercut not supported: the live observation does not contain enough "
            "gap, tyre, pit-loss, or pace data.",
            f"Support is {support_level}; confidence={confidence:.2f}.",
        ]

    if undercut_viable:
        reasons.append(
            "Undercut viable: projected fresh-tyre gain is above the "
            "pit-loss-adjusted requirement."
        )
    else:
        reasons.append(
            "Undercut not viable: projected fresh-tyre gain is below the "
            "pit-loss-adjusted requirement."
        )

    if gap_to_rival_ms is not None:
        reasons.append(
            f"Current rival gap is {gap_to_rival_ms} ms; required gain is "
            f"{required_gain_ms} ms and projected gain is {projected_gain_ms} ms."
        )
    if projected_gap_after_pit_ms is not None:
        if projected_gap_after_pit_ms <= 0:
            reasons.append("Projected pit-cycle gap is favorable after the stop.")
        else:
            reasons.append(
                f"Projected pit-cycle gap remains {projected_gap_after_pit_ms} ms "
                "short after the stop."
            )
    if tyre_age_delta is not None:
        reasons.append(
            f"Tyre age delta is {tyre_age_delta} laps "
            "(positive means the rival is on older tyres)."
        )
    reasons.append(f"Projected pit-exit traffic is {traffic_after_pit}.")
    reasons.append(f"Support is {support_level}; confidence={confidence:.2f}.")
    return reasons


def explain_scenario(
    *,
    scenario_name: str,
    undercut_viable: bool,
    required_gain_ms: int | None,
    projected_gain_ms: int | None,
    projected_gap_after_pit_ms: int | None,
    main_limiting_factor: str,
) -> str:
    """Return one-line explanation for a counterfactual scenario."""

    status = "viable" if undercut_viable else "not viable"
    if required_gain_ms is None or projected_gain_ms is None:
        return (
            f"{scenario_name}: {status}; insufficient numeric support "
            f"({main_limiting_factor})."
        )
    gap_text = (
        "clears the rival"
        if projected_gap_after_pit_ms is not None and projected_gap_after_pit_ms <= 0
        else f"misses by {projected_gap_after_pit_ms} ms"
    )
    return (
        f"{scenario_name}: {status}; projected_gain={projected_gain_ms} ms, "
        f"required_gain={required_gain_ms} ms, {gap_text}; "
        f"main factor={main_limiting_factor}."
    )


def top_factors_from_metrics(
    *,
    gap_to_rival_ms: int | None,
    projected_gap_after_pit_ms: int | None,
    traffic_after_pit: str,
    tyre_age_delta: int | None,
) -> tuple[str, ...]:
    """Rank the most useful live explanation factors."""

    factors: list[str] = []
    if projected_gap_after_pit_ms is not None:
        factors.append("projected_gap_after_pit_ms")
    if gap_to_rival_ms is not None:
        factors.append("gap_to_rival_ms")
    if traffic_after_pit != "unknown":
        factors.append("traffic_after_pit")
    if tyre_age_delta is not None:
        factors.append("tyre_age_delta")
    return tuple(factors)


def combine_explanations(base: Sequence[str], scenarios: Sequence[str]) -> list[str]:
    """Combine base and scenario explanations with stable ordering."""

    return [*base, *scenarios]
