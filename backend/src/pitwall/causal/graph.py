"""Initial DAG for the causal undercut viability module."""

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
        "attacker_degradation_estimate",
        "defender_degradation_estimate",
        "attacker_expected_pace",
        "defender_expected_pace",
        "fresh_tyre_advantage_ms",
        "projected_gain_if_pit_now_ms",
        "required_gain_to_clear_rival_ms",
        "projected_gap_after_pit_ms",
        "traffic_after_pit",
        "clean_air_potential",
        "undercut_viable",
        "pit_decision",
        "pit_now",
        "undercut_success",
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
        "gap_to_rival_ms",
        "traffic_after_pit",
        "tyre_age_delta",
        "pit_now",
    }
)

OUTCOME_CANDIDATES = frozenset(
    {
        "undercut_viable",
        "undercut_success",
        "projected_gap_after_pit_ms",
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
    }
)

CAUSAL_EDGES: tuple[CausalEdge, ...] = (
    CausalEdge("circuit_id", "pit_loss_estimate_ms", "pit lane geometry and speed limit"),
    CausalEdge("circuit_id", "attacker_degradation_estimate", "track surface affects tyre wear"),
    CausalEdge("circuit_id", "defender_degradation_estimate", "track surface affects tyre wear"),
    CausalEdge("track_temp_c", "attacker_degradation_estimate", "track temperature affects tyres"),
    CausalEdge("track_temp_c", "defender_degradation_estimate", "track temperature affects tyres"),
    CausalEdge("air_temp_c", "attacker_degradation_estimate", "ambient conditions proxy"),
    CausalEdge("air_temp_c", "defender_degradation_estimate", "ambient conditions proxy"),
    CausalEdge("rainfall", "track_status", "wet sessions often alter race control state"),
    CausalEdge("track_status", "undercut_viable", "SC/VSC/yellow suppress normal undercuts"),
    CausalEdge(
        "attacker_compound", "attacker_degradation_estimate", "compound controls wear curve"
    ),
    CausalEdge(
        "defender_compound", "defender_degradation_estimate", "compound controls wear curve"
    ),
    CausalEdge("attacker_tyre_age", "attacker_degradation_estimate", "older tyres degrade pace"),
    CausalEdge("defender_tyre_age", "defender_degradation_estimate", "older tyres degrade pace"),
    CausalEdge("tyre_age_delta", "fresh_tyre_advantage_ms", "relative tyre age drives advantage"),
    CausalEdge("attacker_degradation_estimate", "attacker_expected_pace", "pace from wear curve"),
    CausalEdge("defender_degradation_estimate", "defender_expected_pace", "pace from wear curve"),
    CausalEdge("attacker_expected_pace", "fresh_tyre_advantage_ms", "fresh expected pace input"),
    CausalEdge("defender_expected_pace", "fresh_tyre_advantage_ms", "worn expected pace input"),
    CausalEdge("fresh_tyre_advantage_ms", "projected_gain_if_pit_now_ms", "pace gain over window"),
    CausalEdge("traffic_after_pit", "projected_gain_if_pit_now_ms", "traffic reduces usable gain"),
    CausalEdge("clean_air_potential", "projected_gain_if_pit_now_ms", "clean air enables gain"),
    CausalEdge("gap_to_rival_ms", "required_gain_to_clear_rival_ms", "gap must be overcome"),
    CausalEdge("pit_loss_estimate_ms", "required_gain_to_clear_rival_ms", "pit time must be paid"),
    CausalEdge("required_gain_to_clear_rival_ms", "projected_gap_after_pit_ms", "break-even term"),
    CausalEdge("projected_gain_if_pit_now_ms", "projected_gap_after_pit_ms", "gain closes gap"),
    CausalEdge("projected_gap_after_pit_ms", "undercut_viable", "structural viability result"),
    CausalEdge(
        "required_gain_to_clear_rival_ms", "undercut_viable", "higher threshold lowers odds"
    ),
    CausalEdge("projected_gain_if_pit_now_ms", "undercut_viable", "larger gain raises odds"),
    CausalEdge("laps_remaining", "undercut_viable", "too few laps limits payoff"),
    CausalEdge("race_phase", "undercut_viable", "strategy windows depend on race phase"),
    CausalEdge("current_position", "traffic_after_pit", "field position affects pit-exit traffic"),
    CausalEdge("rival_position", "traffic_after_pit", "nearby field affects traffic"),
    CausalEdge("gap_to_rival_ms", "traffic_after_pit", "field spread proxy"),
    CausalEdge("undercut_viable", "pit_decision", "recommendation follows viability"),
    CausalEdge("pit_decision", "pit_now", "actual action follows recommendation/team choice"),
    CausalEdge("pit_now", "undercut_success", "success is only observed after pitting"),
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
