"""Main DAG for the causal undercut viability module.

The graph intentionally stops at ``undercut_viable``.  Team decisions
(``pit_decision``/``pit_now``) and observed pit-cycle outcomes
(``undercut_success``) are evaluation context, not nodes in this viability DAG.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CausalEdge:
    source: str
    target: str
    rationale: str


AVAILABLE_NODES = frozenset(
    {
        "circuit_id",
        "lap_number",
        "laps_remaining",
        "race_phase",
        "track_status",
        "track_temp_c",
        "air_temp_c",
        "rainfall",
        "current_position",
        "rival_position",
        "gap_to_rival_ms",
        "attacker_compound",
        "defender_compound",
        "attacker_tyre_age",
        "defender_tyre_age",
        "tyre_age_delta",
        "attacker_laps_in_stint",
        "defender_laps_in_stint",
        "pit_loss_estimate_ms",
        "pit_lane_congestion",
        "pace_delta_to_rival_ms",
        "fresh_tyre_advantage_ms",
        "projected_gain_if_pit_now_ms",
        "required_gain_to_clear_rival_ms",
        "projected_gap_after_pit_ms",
        "traffic_after_pit",
        "clean_air_potential",
        "defender_likely_to_cover",
        "pit_window_open",
        "safety_car_or_vsc_risk",
        "undercut_viable",
    }
)

IDEAL_FUTURE_NODES = frozenset(
    {
        "overtake_difficulty_proxy",
        "remaining_compounds_available",
        "team_strategy_context",
        "rival_likely_pit_window",
        "dirty_air_telemetry",
        "drs_train_context",
    }
)

TREATMENT_CANDIDATES = frozenset(
    {
        "fresh_tyre_advantage_ms",
        "pace_delta_to_rival_ms",
        "gap_to_rival_ms",
        "traffic_after_pit",
        "tyre_age_delta",
    }
)

OUTCOME_CANDIDATES = frozenset(
    {
        "undercut_viable",
    }
)

CONFOUNDER_CANDIDATES = frozenset(
    {
        "circuit_id",
        "lap_number",
        "laps_remaining",
        "race_phase",
        "track_status",
        "track_temp_c",
        "air_temp_c",
        "rainfall",
        "current_position",
        "rival_position",
        "gap_to_rival_ms",
        "attacker_compound",
        "defender_compound",
        "attacker_tyre_age",
        "defender_tyre_age",
        "tyre_age_delta",
        "pit_loss_estimate_ms",
        "traffic_after_pit",
        "pit_lane_congestion",
        "pace_delta_to_rival_ms",
        "safety_car_or_vsc_risk",
    }
)

CAUSAL_EDGES: tuple[CausalEdge, ...] = (
    CausalEdge("circuit_id", "pit_loss_estimate_ms", "pit lane geometry and speed limit"),
    CausalEdge("circuit_id", "pace_delta_to_rival_ms", "track surface affects relative pace"),
    CausalEdge("track_temp_c", "pace_delta_to_rival_ms", "track temperature affects tyres"),
    CausalEdge("air_temp_c", "pace_delta_to_rival_ms", "ambient conditions proxy"),
    CausalEdge("rainfall", "track_status", "wet sessions often alter race control state"),
    CausalEdge("rainfall", "pace_delta_to_rival_ms", "wet conditions alter relative pace"),
    CausalEdge("rainfall", "fresh_tyre_advantage_ms", "wet conditions alter tyre advantage"),
    CausalEdge("rainfall", "pit_loss_estimate_ms", "wet pit entry/exit can alter loss"),
    CausalEdge("rainfall", "safety_car_or_vsc_risk", "rain increases neutralisation risk"),
    CausalEdge("rainfall", "undercut_viable", "rain invalidates dry undercut assumptions"),
    CausalEdge("track_status", "pit_loss_estimate_ms", "SC/VSC changes effective pit loss"),
    CausalEdge("track_status", "traffic_after_pit", "neutralised fields compress traffic"),
    CausalEdge("track_status", "safety_car_or_vsc_risk", "status is the direct risk proxy"),
    CausalEdge("track_status", "undercut_viable", "SC/VSC/yellow suppress normal undercuts"),
    CausalEdge("attacker_compound", "pace_delta_to_rival_ms", "compound controls pace"),
    CausalEdge("defender_compound", "pace_delta_to_rival_ms", "compound controls pace"),
    CausalEdge("attacker_tyre_age", "pace_delta_to_rival_ms", "older tyres degrade pace"),
    CausalEdge("defender_tyre_age", "pace_delta_to_rival_ms", "older tyres degrade pace"),
    CausalEdge("tyre_age_delta", "fresh_tyre_advantage_ms", "relative tyre age drives advantage"),
    CausalEdge("pace_delta_to_rival_ms", "fresh_tyre_advantage_ms", "relative pace input"),
    CausalEdge("attacker_tyre_age", "fresh_tyre_advantage_ms", "attacker tyre state"),
    CausalEdge("defender_tyre_age", "fresh_tyre_advantage_ms", "defender tyre state"),
    CausalEdge("attacker_compound", "fresh_tyre_advantage_ms", "fresh compound baseline"),
    CausalEdge("defender_compound", "fresh_tyre_advantage_ms", "defender compound baseline"),
    CausalEdge("fresh_tyre_advantage_ms", "projected_gain_if_pit_now_ms", "pace gain over window"),
    CausalEdge(
        "pace_delta_to_rival_ms",
        "projected_gain_if_pit_now_ms",
        "relative pace carries into gain projection",
    ),
    CausalEdge("traffic_after_pit", "projected_gain_if_pit_now_ms", "traffic reduces usable gain"),
    CausalEdge("clean_air_potential", "projected_gain_if_pit_now_ms", "clean air enables gain"),
    CausalEdge("laps_remaining", "projected_gain_if_pit_now_ms", "window length limits gain"),
    CausalEdge("race_phase", "projected_gain_if_pit_now_ms", "phase changes strategic window"),
    CausalEdge("track_status", "projected_gain_if_pit_now_ms", "neutralised laps limit gain"),
    CausalEdge("gap_to_rival_ms", "required_gain_to_clear_rival_ms", "gap must be overcome"),
    CausalEdge("pit_loss_estimate_ms", "required_gain_to_clear_rival_ms", "pit time must be paid"),
    CausalEdge("traffic_after_pit", "required_gain_to_clear_rival_ms", "traffic adds buffer need"),
    CausalEdge("clean_air_potential", "required_gain_to_clear_rival_ms", "clean air lowers buffer"),
    CausalEdge("current_position", "required_gain_to_clear_rival_ms", "position affects clear gap"),
    CausalEdge(
        "rival_position",
        "required_gain_to_clear_rival_ms",
        "rival position affects clear gap",
    ),
    CausalEdge("required_gain_to_clear_rival_ms", "projected_gap_after_pit_ms", "break-even term"),
    CausalEdge("projected_gain_if_pit_now_ms", "projected_gap_after_pit_ms", "gain closes gap"),
    CausalEdge("projected_gap_after_pit_ms", "undercut_viable", "structural viability result"),
    CausalEdge("defender_likely_to_cover", "undercut_viable", "cover response can close window"),
    CausalEdge("pit_window_open", "undercut_viable", "strategy window must be open"),
    CausalEdge("safety_car_or_vsc_risk", "undercut_viable", "neutralisation changes pit calculus"),
    CausalEdge("laps_remaining", "undercut_viable", "too few laps limits payoff"),
    CausalEdge("race_phase", "undercut_viable", "strategy windows depend on race phase"),
    CausalEdge("current_position", "traffic_after_pit", "field position affects pit-exit traffic"),
    CausalEdge("rival_position", "traffic_after_pit", "nearby field affects traffic"),
    CausalEdge("gap_to_rival_ms", "traffic_after_pit", "field spread proxy"),
    CausalEdge("track_status", "pit_lane_congestion", "neutralised fields increase pit stacking"),
    CausalEdge("race_phase", "pit_lane_congestion", "pit clusters vary by phase"),
    CausalEdge("laps_remaining", "pit_lane_congestion", "late stops can cluster pit lane"),
    CausalEdge("current_position", "pit_lane_congestion", "field position affects release risk"),
    CausalEdge("rival_position", "pit_lane_congestion", "nearby rivals affect release risk"),
    CausalEdge("pit_lane_congestion", "pit_loss_estimate_ms", "pit lane delay increases loss"),
    CausalEdge("gap_to_rival_ms", "defender_likely_to_cover", "small gaps invite cover stops"),
    CausalEdge("defender_tyre_age", "defender_likely_to_cover", "old tyres make cover plausible"),
    CausalEdge("defender_compound", "defender_likely_to_cover", "compound affects stop window"),
    CausalEdge("rival_position", "defender_likely_to_cover", "track position affects cover value"),
    CausalEdge("race_phase", "defender_likely_to_cover", "phase affects rival stop timing"),
    CausalEdge("laps_remaining", "defender_likely_to_cover", "remaining laps bound cover window"),
    CausalEdge("track_status", "defender_likely_to_cover", "SC/VSC can trigger cover response"),
    CausalEdge("race_phase", "pit_window_open", "pit windows depend on race phase"),
    CausalEdge("laps_remaining", "pit_window_open", "enough laps must remain"),
    CausalEdge("attacker_tyre_age", "pit_window_open", "attacker stint age gates stops"),
    CausalEdge("attacker_compound", "pit_window_open", "compound affects stint feasibility"),
)


def dag_nodes() -> tuple[str, ...]:
    """Return all available DAG nodes in deterministic order."""

    edge_nodes = {node for edge in CAUSAL_EDGES for node in (edge.source, edge.target)}
    return tuple(sorted(AVAILABLE_NODES | edge_nodes))


def dag_edges() -> tuple[tuple[str, str], ...]:
    """Return directed DAG edges in deterministic order."""

    return tuple((edge.source, edge.target) for edge in CAUSAL_EDGES)


def dag_dot() -> str:
    """Return the DAG as DOT for documentation and graph visualizers."""

    lines = ["digraph causal_undercut_viability {"]
    for node in dag_nodes():
        lines.append(f'  "{node}";')
    for edge in CAUSAL_EDGES:
        lines.append(f'  "{edge.source}" -> "{edge.target}";')
    lines.append("}")
    return "\n".join(lines)


def dag_gml() -> str:
    """Return the DAG as GML for DoWhy's graph parser."""

    node_ids = {node: index for index, node in enumerate(dag_nodes())}
    lines = ["graph [", "  directed 1"]
    for node, node_id in node_ids.items():
        lines.extend(["  node [", f"    id {node_id}", f'    label "{node}"', "  ]"])
    for edge in CAUSAL_EDGES:
        lines.extend(
            [
                "  edge [",
                f"    source {node_ids[edge.source]}",
                f"    target {node_ids[edge.target]}",
                "  ]",
            ]
        )
    lines.append("]")
    return "\n".join(lines)


def validate_dag() -> None:
    """Raise ValueError if the encoded graph is not a valid DAG."""

    nodes = set(dag_nodes())
    unknown = sorted(
        node
        for edge in CAUSAL_EDGES
        for node in (edge.source, edge.target)
        if node not in nodes
    )
    if unknown:
        raise ValueError(f"DAG references unknown node(s): {unknown}")
    cycle = _first_cycle(dag_edges())
    if cycle:
        raise ValueError(f"DAG contains a cycle: {' -> '.join(cycle)}")


def available_treatments() -> tuple[str, ...]:
    return tuple(sorted(TREATMENT_CANDIDATES & AVAILABLE_NODES))


def available_outcomes() -> tuple[str, ...]:
    return tuple(sorted(OUTCOME_CANDIDATES & AVAILABLE_NODES))


def _first_cycle(edges: Iterable[tuple[str, str]]) -> list[str]:
    adjacency: dict[str, list[str]] = defaultdict(list)
    for source, target in edges:
        adjacency[source].append(target)

    visiting: set[str] = set()
    visited: set[str] = set()
    path: list[str] = []

    def visit(node: str) -> list[str]:
        if node in visiting:
            start = path.index(node)
            return [*path[start:], node]
        if node in visited:
            return []
        visiting.add(node)
        path.append(node)
        for child in adjacency[node]:
            cycle = visit(child)
            if cycle:
                return cycle
        path.pop()
        visiting.remove(node)
        visited.add(node)
        return []

    for node in dag_nodes():
        cycle = visit(node)
        if cycle:
            return cycle
    return []
