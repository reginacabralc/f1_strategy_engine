"""Tests for pit-loss lookup."""

from __future__ import annotations

from pitwall.engine.pit_loss import DEFAULT_PIT_LOSS_MS, lookup_pit_loss


def test_lookup_returns_exact_team_entry() -> None:
    table = {"monaco": {"mercedes": 19_500, None: 21_000}}
    assert lookup_pit_loss("monaco", "mercedes", table) == 19_500


def test_lookup_falls_back_to_circuit_median_when_team_missing() -> None:
    table: dict[str, dict[str | None, int]] = {"monaco": {None: 21_000}}
    assert lookup_pit_loss("monaco", "ferrari", table) == 21_000


def test_lookup_falls_back_to_default_when_circuit_missing() -> None:
    assert lookup_pit_loss("bahrain", "mercedes", {}) == DEFAULT_PIT_LOSS_MS


def test_lookup_uses_default_arg_when_circuit_missing() -> None:
    assert lookup_pit_loss("spa", "redbull", {}, default=18_500) == 18_500


def test_lookup_handles_none_team_code() -> None:
    table: dict[str, dict[str | None, int]] = {"monaco": {None: 22_000}}
    assert lookup_pit_loss("monaco", None, table) == 22_000


def test_lookup_prefers_team_over_circuit_median() -> None:
    table = {"monaco": {"alpine": 23_000, None: 21_000}}
    assert lookup_pit_loss("monaco", "alpine", table) == 23_000
