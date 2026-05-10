"""Persist fitted degradation coefficients."""

from __future__ import annotations

from collections.abc import Iterable
from importlib import import_module
from typing import Any, Protocol

from pitwall.degradation.models import DegradationFitResult

UPSERT_COEFFICIENT_SQL = """
    INSERT INTO degradation_coefficients (
        circuit_id,
        compound,
        model_type,
        a,
        b,
        c,
        r_squared,
        rmse_ms,
        n_samples,
        n_laps,
        min_tyre_age,
        max_tyre_age,
        source_sessions,
        fitted_at
    )
    VALUES (
        :circuit_id,
        :compound,
        :model_type,
        :a,
        :b,
        :c,
        :r_squared,
        :rmse_ms,
        :n_samples,
        :n_laps,
        :min_tyre_age,
        :max_tyre_age,
        :source_sessions,
        NOW()
    )
    ON CONFLICT (circuit_id, compound) DO UPDATE SET
        model_type = EXCLUDED.model_type,
        a = EXCLUDED.a,
        b = EXCLUDED.b,
        c = EXCLUDED.c,
        r_squared = EXCLUDED.r_squared,
        rmse_ms = EXCLUDED.rmse_ms,
        n_samples = EXCLUDED.n_samples,
        n_laps = EXCLUDED.n_laps,
        min_tyre_age = EXCLUDED.min_tyre_age,
        max_tyre_age = EXCLUDED.max_tyre_age,
        source_sessions = EXCLUDED.source_sessions,
        fitted_at = EXCLUDED.fitted_at
"""


class WriteConnection(Protocol):
    def execute(self, statement: object, parameters: list[dict[str, Any]] | None = None) -> Any:
        ...


def build_coefficient_payload(result: DegradationFitResult) -> dict[str, Any]:
    if not result.is_fittable:
        raise ValueError(f"{result.circuit_id} {result.compound} result is not fittable")
    return {
        "circuit_id": result.circuit_id,
        "compound": result.compound,
        "model_type": result.model_type,
        "a": result.a,
        "b": result.b,
        "c": result.c,
        "r_squared": result.r2,
        "rmse_ms": result.rmse_ms,
        "n_samples": result.n_laps,
        "n_laps": result.n_laps,
        "min_tyre_age": result.min_tyre_age,
        "max_tyre_age": result.max_tyre_age,
        "source_sessions": list(result.source_sessions),
    }


def write_fit_results(connection: WriteConnection, results: Iterable[DegradationFitResult]) -> int:
    payloads = [build_coefficient_payload(result) for result in results if result.is_fittable]
    if not payloads:
        return 0
    connection.execute(_sql_text(UPSERT_COEFFICIENT_SQL), payloads)
    return len(payloads)


def _sql_text(sql: str) -> Any:
    sqlalchemy = import_module("sqlalchemy")
    return sqlalchemy.text(sql)
