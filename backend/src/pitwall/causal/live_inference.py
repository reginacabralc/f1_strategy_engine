"""Live lap-by-lap causal undercut inference and counterfactual simulation."""

from __future__ import annotations

from dataclasses import dataclass

from pitwall.causal.explain import (
    combine_explanations,
    explain_base_decision,
    explain_scenario,
    top_factors_from_metrics,
)
from pitwall.engine.projection import PacePredictor
from pitwall.engine.state import DriverState, RaceState
from pitwall.engine.undercut import UNDERCUT_MARGIN_MS, evaluate_undercut

TRAFFIC_PENALTY_MS = 3_000
TRAFFIC_BONUS_MS = 1_000
PIT_LOSS_SENSITIVITY_MS = 1_000


@dataclass(frozen=True, slots=True)
class CausalLiveObservation:
    session_id: str
    circuit_id: str
    lap_number: int
    total_laps: int | None
    laps_remaining: int | None
    attacker_code: str
    defender_code: str
    current_position: int | None
    rival_position: int | None
    gap_to_rival_ms: int | None
    attacker_compound: str | None
    defender_compound: str | None
    attacker_tyre_age: int
    defender_tyre_age: int
    tyre_age_delta: int
    track_status: str
    track_temp_c: float | None
    air_temp_c: float | None
    rainfall: bool
    pit_loss_estimate_ms: int


@dataclass(frozen=True, slots=True)
class CausalScenarioResult:
    scenario_name: str
    undercut_viable: bool
    required_gain_ms: int | None
    projected_gain_ms: int | None
    projected_gap_after_pit_ms: int | None
    main_limiting_factor: str
    explanation: str


@dataclass(frozen=True, slots=True)
class CausalLiveResult:
    observation: CausalLiveObservation
    undercut_viable: bool
    support_level: str
    confidence: float
    required_gain_ms: int | None
    projected_gain_ms: int | None
    projected_gap_after_pit_ms: int | None
    traffic_after_pit: str
    top_factors: tuple[str, ...]
    explanations: tuple[str, ...]
    counterfactuals: tuple[CausalScenarioResult, ...]


def build_live_observation(
    state: RaceState,
    attacker: DriverState,
    defender: DriverState,
    *,
    pit_loss_ms: int,
) -> CausalLiveObservation:
    """Convert a current RaceState pair into the causal live observation shape."""

    laps_remaining = (
        max(0, state.total_laps - state.current_lap)
        if state.total_laps is not None
        else None
    )
    return CausalLiveObservation(
        session_id=state.session_id,
        circuit_id=state.circuit_id,
        lap_number=state.current_lap,
        total_laps=state.total_laps,
        laps_remaining=laps_remaining,
        attacker_code=attacker.driver_code,
        defender_code=defender.driver_code,
        current_position=attacker.position,
        rival_position=defender.position,
        gap_to_rival_ms=attacker.gap_to_ahead_ms,
        attacker_compound=attacker.compound,
        defender_compound=defender.compound,
        attacker_tyre_age=attacker.tyre_age,
        defender_tyre_age=defender.tyre_age,
        tyre_age_delta=defender.tyre_age - attacker.tyre_age,
        track_status=state.track_status,
        track_temp_c=state.track_temp_c,
        air_temp_c=state.air_temp_c,
        rainfall=state.rainfall,
        pit_loss_estimate_ms=pit_loss_ms,
    )


def evaluate_causal_live(
    state: RaceState,
    attacker: DriverState,
    defender: DriverState,
    predictor: PacePredictor,
    *,
    pit_loss_ms: int,
) -> CausalLiveResult:
    """Predict, simulate, and explain current undercut viability for one pair."""

    observation = build_live_observation(
        state,
        attacker,
        defender,
        pit_loss_ms=pit_loss_ms,
    )
    base = evaluate_undercut(state, attacker, defender, predictor, pit_loss_ms)
    base_metrics = _metrics_from_decision(
        gap_to_rival_ms=observation.gap_to_rival_ms,
        pit_loss_ms=pit_loss_ms,
        estimated_gain_ms=base.estimated_gain_ms,
        has_projection=base.alert_type == "UNDERCUT_VIABLE",
    )
    support_level = _support_level(base.alert_type, base.confidence, observation)
    undercut_viable = bool(base_metrics["undercut_viable"]) and support_level != "insufficient"
    traffic_after_pit = _traffic_bucket(base_metrics["projected_gap_after_pit_ms"])
    top_factors = top_factors_from_metrics(
        gap_to_rival_ms=observation.gap_to_rival_ms,
        projected_gap_after_pit_ms=base_metrics["projected_gap_after_pit_ms"],
        traffic_after_pit=traffic_after_pit,
        tyre_age_delta=observation.tyre_age_delta,
    )
    base_explanations = explain_base_decision(
        undercut_viable=undercut_viable,
        support_level=support_level,
        gap_to_rival_ms=observation.gap_to_rival_ms,
        required_gain_ms=base_metrics["required_gain_ms"],
        projected_gain_ms=base_metrics["projected_gain_ms"],
        projected_gap_after_pit_ms=base_metrics["projected_gap_after_pit_ms"],
        traffic_after_pit=traffic_after_pit,
        tyre_age_delta=observation.tyre_age_delta,
        confidence=base.confidence,
    )
    scenarios = _counterfactuals(state, attacker, defender, predictor, pit_loss_ms)
    scenario_explanations = [scenario.explanation for scenario in scenarios]
    return CausalLiveResult(
        observation=observation,
        undercut_viable=undercut_viable,
        support_level=support_level,
        confidence=base.confidence,
        required_gain_ms=base_metrics["required_gain_ms"],
        projected_gain_ms=base_metrics["projected_gain_ms"],
        projected_gap_after_pit_ms=base_metrics["projected_gap_after_pit_ms"],
        traffic_after_pit=traffic_after_pit,
        top_factors=top_factors,
        explanations=tuple(combine_explanations(base_explanations, scenario_explanations)),
        counterfactuals=scenarios,
    )


def _counterfactuals(
    state: RaceState,
    attacker: DriverState,
    defender: DriverState,
    predictor: PacePredictor,
    pit_loss_ms: int,
) -> tuple[CausalScenarioResult, ...]:
    base = evaluate_undercut(state, attacker, defender, predictor, pit_loss_ms)
    base_metrics = _metrics_from_decision(
        gap_to_rival_ms=attacker.gap_to_ahead_ms,
        pit_loss_ms=pit_loss_ms,
        estimated_gain_ms=base.estimated_gain_ms,
        has_projection=base.alert_type == "UNDERCUT_VIABLE",
    )
    next_lap = _next_lap_scenario(state, attacker, defender, predictor, pit_loss_ms)
    scenarios = [
        _scenario_from_metrics("base_case", base_metrics),
        _scenario_from_metrics("current_lap", base_metrics),
        next_lap,
        _scenario_from_metrics(
            "current_lap_high_traffic",
            _intervene_projected_gain(base_metrics, -TRAFFIC_PENALTY_MS),
        ),
        _scenario_from_metrics(
            "current_lap_low_traffic",
            _intervene_projected_gain(base_metrics, TRAFFIC_BONUS_MS),
        ),
        _scenario_from_metrics(
            "pit_loss_minus_1000_ms",
            _intervene_pit_loss(
                gap_to_rival_ms=attacker.gap_to_ahead_ms,
                pit_loss_ms=max(0, pit_loss_ms - PIT_LOSS_SENSITIVITY_MS),
                projected_gain_ms=base_metrics["projected_gain_ms"],
            ),
        ),
        _scenario_from_metrics(
            "pit_loss_plus_1000_ms",
            _intervene_pit_loss(
                gap_to_rival_ms=attacker.gap_to_ahead_ms,
                pit_loss_ms=pit_loss_ms + PIT_LOSS_SENSITIVITY_MS,
                projected_gain_ms=base_metrics["projected_gain_ms"],
            ),
        ),
    ]
    return tuple(scenarios)


def _next_lap_scenario(
    state: RaceState,
    attacker: DriverState,
    defender: DriverState,
    predictor: PacePredictor,
    pit_loss_ms: int,
) -> CausalScenarioResult:
    next_state = RaceState(
        session_id=state.session_id,
        circuit_id=state.circuit_id,
        total_laps=state.total_laps,
        current_lap=state.current_lap + 1,
        track_status=state.track_status,
        track_temp_c=state.track_temp_c,
        air_temp_c=state.air_temp_c,
        humidity_pct=state.humidity_pct,
        rainfall=state.rainfall,
    )
    next_attacker = _copy_driver(attacker, tyre_age_delta=1, laps_in_stint_delta=1)
    next_defender = _copy_driver(defender, tyre_age_delta=1, laps_in_stint_delta=1)
    decision = evaluate_undercut(
        next_state,
        next_attacker,
        next_defender,
        predictor,
        pit_loss_ms,
    )
    return _scenario_from_metrics(
        "next_lap",
        _metrics_from_decision(
            gap_to_rival_ms=next_attacker.gap_to_ahead_ms,
            pit_loss_ms=pit_loss_ms,
            estimated_gain_ms=decision.estimated_gain_ms,
            has_projection=decision.alert_type == "UNDERCUT_VIABLE",
        ),
    )


def _metrics_from_decision(
    *,
    gap_to_rival_ms: int | None,
    pit_loss_ms: int,
    estimated_gain_ms: int,
    has_projection: bool,
) -> dict[str, int | bool | None]:
    if not has_projection:
        return {
            "undercut_viable": False,
            "required_gain_ms": None,
            "projected_gain_ms": None,
            "projected_gap_after_pit_ms": None,
        }
    projected_gain_ms = estimated_gain_ms + pit_loss_ms
    if gap_to_rival_ms is None:
        return {
            "undercut_viable": False,
            "required_gain_ms": None,
            "projected_gain_ms": None,
            "projected_gap_after_pit_ms": None,
        }
    required_gain_ms = gap_to_rival_ms + pit_loss_ms + UNDERCUT_MARGIN_MS
    projected_gap_after_pit_ms = required_gain_ms - projected_gain_ms
    return {
        "undercut_viable": projected_gap_after_pit_ms <= 0,
        "required_gain_ms": required_gain_ms,
        "projected_gain_ms": projected_gain_ms,
        "projected_gap_after_pit_ms": projected_gap_after_pit_ms,
    }


def _intervene_projected_gain(
    metrics: dict[str, int | bool | None],
    delta_ms: int,
) -> dict[str, int | bool | None]:
    projected_gain = _int_or_none(metrics["projected_gain_ms"])
    required_gain = _int_or_none(metrics["required_gain_ms"])
    if projected_gain is None or required_gain is None:
        return dict(metrics)
    projected_gain += delta_ms
    projected_gap = required_gain - projected_gain
    return {
        **metrics,
        "undercut_viable": projected_gap <= 0,
        "projected_gain_ms": projected_gain,
        "projected_gap_after_pit_ms": projected_gap,
    }


def _intervene_pit_loss(
    *,
    gap_to_rival_ms: int | None,
    pit_loss_ms: int,
    projected_gain_ms: int | bool | None,
) -> dict[str, int | bool | None]:
    projected_gain = _int_or_none(projected_gain_ms)
    if gap_to_rival_ms is None or projected_gain is None:
        return {
            "undercut_viable": False,
            "required_gain_ms": None,
            "projected_gain_ms": projected_gain,
            "projected_gap_after_pit_ms": None,
        }
    required_gain = gap_to_rival_ms + pit_loss_ms + UNDERCUT_MARGIN_MS
    projected_gap = required_gain - projected_gain
    return {
        "undercut_viable": projected_gap <= 0,
        "required_gain_ms": required_gain,
        "projected_gain_ms": projected_gain,
        "projected_gap_after_pit_ms": projected_gap,
    }


def _scenario_from_metrics(
    scenario_name: str,
    metrics: dict[str, int | bool | None],
) -> CausalScenarioResult:
    required_gain = _int_or_none(metrics["required_gain_ms"])
    projected_gain = _int_or_none(metrics["projected_gain_ms"])
    projected_gap = _int_or_none(metrics["projected_gap_after_pit_ms"])
    undercut_viable = bool(metrics["undercut_viable"])
    main_limiting_factor = _main_limiting_factor(
        required_gain_ms=required_gain,
        projected_gain_ms=projected_gain,
        projected_gap_after_pit_ms=projected_gap,
    )
    return CausalScenarioResult(
        scenario_name=scenario_name,
        undercut_viable=undercut_viable,
        required_gain_ms=required_gain,
        projected_gain_ms=projected_gain,
        projected_gap_after_pit_ms=projected_gap,
        main_limiting_factor=main_limiting_factor,
        explanation=explain_scenario(
            scenario_name=scenario_name,
            undercut_viable=undercut_viable,
            required_gain_ms=required_gain,
            projected_gain_ms=projected_gain,
            projected_gap_after_pit_ms=projected_gap,
            main_limiting_factor=main_limiting_factor,
        ),
    )


def _support_level(
    alert_type: str,
    confidence: float,
    observation: CausalLiveObservation,
) -> str:
    if alert_type in {"INSUFFICIENT_DATA", "UNDERCUT_DISABLED_RAIN"}:
        return "insufficient"
    if (
        observation.gap_to_rival_ms is None
        or observation.track_status.upper() != "GREEN"
        or observation.rainfall
    ):
        return "insufficient"
    if confidence >= 0.65:
        return "strong"
    if confidence >= 0.35:
        return "weak"
    return "insufficient"


def _traffic_bucket(projected_gap_after_pit_ms: int | None) -> str:
    if projected_gap_after_pit_ms is None:
        return "unknown"
    if projected_gap_after_pit_ms <= 0:
        return "low"
    if projected_gap_after_pit_ms <= 3_000:
        return "medium"
    return "high"


def _main_limiting_factor(
    *,
    required_gain_ms: int | None,
    projected_gain_ms: int | None,
    projected_gap_after_pit_ms: int | None,
) -> str:
    if required_gain_ms is None or projected_gain_ms is None:
        return "insufficient_data"
    if projected_gap_after_pit_ms is not None and projected_gap_after_pit_ms <= 0:
        return "fresh_tyre_advantage"
    if required_gain_ms > projected_gain_ms:
        return "required_gain_to_clear_rival"
    return "projected_gap_after_pit"


def _copy_driver(
    driver: DriverState,
    *,
    tyre_age_delta: int,
    laps_in_stint_delta: int,
) -> DriverState:
    return DriverState(
        driver_code=driver.driver_code,
        team_code=driver.team_code,
        position=driver.position,
        gap_to_leader_ms=driver.gap_to_leader_ms,
        gap_to_ahead_ms=driver.gap_to_ahead_ms,
        last_lap_ms=driver.last_lap_ms,
        compound=driver.compound,
        tyre_age=driver.tyre_age + tyre_age_delta,
        stint_number=driver.stint_number,
        laps_in_stint=driver.laps_in_stint + laps_in_stint_delta,
        is_in_pit=driver.is_in_pit,
        is_lapped=driver.is_lapped,
        last_pit_lap=driver.last_pit_lap,
        data_stale=driver.data_stale,
        stale_since_lap=driver.stale_since_lap,
        undercut_score=driver.undercut_score,
    )


def _int_or_none(value: int | bool | None) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    return value
