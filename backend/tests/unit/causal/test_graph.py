"""Tests for the causal undercut DAG."""

from __future__ import annotations

from pitwall.causal.graph import (
    CAUSAL_EDGES,
    available_outcomes,
    available_treatments,
    dag_dot,
    dag_gml,
    dag_nodes,
    validate_dag,
)


def test_initial_dag_is_valid_and_nonempty() -> None:
    validate_dag()

    assert len(dag_nodes()) > 10
    assert len(CAUSAL_EDGES) > 10


def test_dag_exports_dot_and_gml_with_key_edges() -> None:
    dot = dag_dot()
    gml = dag_gml()

    assert '"fresh_tyre_advantage_ms" -> "projected_gain_if_pit_now_ms"' in dot
    assert '"projected_gap_after_pit_ms" -> "undercut_viable"' in dot
    assert "directed 1" in gml
    assert 'label "undercut_viable"' in gml


def test_available_treatments_and_outcomes_are_explicit() -> None:
    assert "fresh_tyre_advantage_ms" in available_treatments()
    assert "gap_to_rival_ms" in available_treatments()
    assert "undercut_viable" in available_outcomes()
    assert "undercut_success" in available_outcomes()
