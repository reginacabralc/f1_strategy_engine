"""Tests for persisting degradation fit results."""

from __future__ import annotations

from typing import Any

from pitwall.degradation.models import DegradationFitResult
from pitwall.degradation.writer import build_coefficient_payload, write_fit_results


def fitted_result() -> DegradationFitResult:
    return DegradationFitResult(
        circuit_id="monaco",
        compound="MEDIUM",
        source_sessions=("monaco_2024_R",),
        status="fitted",
        a=80_000.0,
        b=120.0,
        c=5.0,
        r2=0.82,
        rmse_ms=420.0,
        n_laps=42,
        min_tyre_age=1,
        max_tyre_age=31,
    )


def test_build_coefficient_payload_contains_required_keys() -> None:
    payload = build_coefficient_payload(fitted_result())

    assert payload["circuit_id"] == "monaco"
    assert payload["compound"] == "MEDIUM"
    assert payload["model_type"] == "quadratic_v1"
    assert payload["n_samples"] == 42
    assert payload["n_laps"] == 42
    assert payload["source_sessions"] == ["monaco_2024_R"]


class FakeConnection:
    def __init__(self) -> None:
        self.calls: list[tuple[object, list[dict[str, Any]]]] = []

    def execute(self, statement: object, parameters: list[dict[str, Any]] | None = None) -> None:
        self.calls.append((statement, parameters or []))


def test_write_fit_results_upserts_only_fitted_rows() -> None:
    connection = FakeConnection()
    skipped = DegradationFitResult(
        circuit_id="monaco",
        compound="SOFT",
        source_sessions=("monaco_2024_R",),
        status="skipped_insufficient_data",
        n_laps=4,
        warning="requires at least 8 laps and 3 tyre-age values",
    )

    written = write_fit_results(connection, [fitted_result(), skipped])

    assert written == 1
    assert len(connection.calls) == 1
    sql = str(connection.calls[0][0])
    assert "ON CONFLICT (circuit_id, compound)" in sql
    assert connection.calls[0][1][0]["circuit_id"] == "monaco"
