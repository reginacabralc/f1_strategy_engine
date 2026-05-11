"""Unit tests for driver offset writer (mock DB connection)."""

from __future__ import annotations

from typing import Any

from pitwall.pace_offsets.models import DriverOffsetResult
from pitwall.pace_offsets.writer import write_driver_offsets


class FakeConnection:
    def __init__(self) -> None:
        self.calls: list[tuple[object, list[dict[str, Any]]]] = []

    def execute(self, statement: object, parameters: list[dict[str, Any]] | None = None) -> None:
        self.calls.append((statement, parameters or []))


def _fitted(driver: str = "VER", offset_ms: float = -500.0) -> DriverOffsetResult:
    return DriverOffsetResult(
        driver_code=driver,
        circuit_id="monaco",
        compound="SOFT",
        status="fitted",
        offset_ms=offset_ms,
        n_samples=10,
    )


def _skipped(driver: str = "NOR") -> DriverOffsetResult:
    return DriverOffsetResult(
        driver_code=driver,
        circuit_id="monaco",
        compound="SOFT",
        status="skipped_insufficient_data",
        n_samples=3,
    )


def test_writes_only_fitted_rows() -> None:
    conn = FakeConnection()
    written = write_driver_offsets(conn, [_fitted(), _skipped()])
    assert written == 1
    assert len(conn.calls) == 1


def test_payload_contains_correct_fields() -> None:
    conn = FakeConnection()
    write_driver_offsets(conn, [_fitted("HAM", -300.0)])
    payload = conn.calls[0][1]
    assert len(payload) == 1
    row = payload[0]
    assert row["driver_code"] == "HAM"
    assert row["circuit_id"] == "monaco"
    assert row["compound"] == "SOFT"
    assert row["offset_ms"] == -300.0
    assert row["n_samples"] == 10


def test_upsert_sql_contains_on_conflict_clause() -> None:
    conn = FakeConnection()
    write_driver_offsets(conn, [_fitted()])
    sql_str = str(conn.calls[0][0])
    assert "ON CONFLICT (driver_code, circuit_id, compound)" in sql_str


def test_returns_zero_on_empty_results() -> None:
    conn = FakeConnection()
    written = write_driver_offsets(conn, [])
    assert written == 0
    assert not conn.calls


def test_idempotent_on_all_skipped() -> None:
    conn = FakeConnection()
    written = write_driver_offsets(conn, [_skipped("VER"), _skipped("HAM")])
    assert written == 0
    assert not conn.calls


def test_multiple_fitted_rows_written_in_one_call() -> None:
    conn = FakeConnection()
    written = write_driver_offsets(conn, [_fitted("VER"), _fitted("HAM"), _skipped("NOR")])
    assert written == 2
    assert len(conn.calls) == 1
    assert len(conn.calls[0][1]) == 2
