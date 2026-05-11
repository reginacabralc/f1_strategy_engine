"""Persist driver pace offsets to driver_skill_offsets."""

from __future__ import annotations

from collections.abc import Iterable
from importlib import import_module
from typing import Any, Protocol

from pitwall.pace_offsets.models import DriverOffsetResult

UPSERT_OFFSET_SQL = """
    INSERT INTO driver_skill_offsets (
        driver_code,
        circuit_id,
        compound,
        offset_ms,
        n_samples,
        computed_at
    )
    VALUES (
        :driver_code,
        :circuit_id,
        :compound,
        :offset_ms,
        :n_samples,
        NOW()
    )
    ON CONFLICT (driver_code, circuit_id, compound) DO UPDATE SET
        offset_ms    = EXCLUDED.offset_ms,
        n_samples    = EXCLUDED.n_samples,
        computed_at  = EXCLUDED.computed_at
"""


class WriteConnection(Protocol):
    def execute(self, statement: object, parameters: Any) -> Any: ...


def write_driver_offsets(
    connection: WriteConnection,
    results: Iterable[DriverOffsetResult],
) -> int:
    """Upsert fitted offset rows; silently skip skipped_insufficient_data results."""
    payloads = [
        {
            "driver_code": r.driver_code,
            "circuit_id": r.circuit_id,
            "compound": r.compound,
            "offset_ms": r.offset_ms,
            "n_samples": r.n_samples,
        }
        for r in results
        if r.is_usable
    ]
    if not payloads:
        return 0
    connection.execute(_sql_text(UPSERT_OFFSET_SQL), payloads)
    return len(payloads)


def _sql_text(sql: str) -> Any:
    sqlalchemy = import_module("sqlalchemy")
    return sqlalchemy.text(sql)
