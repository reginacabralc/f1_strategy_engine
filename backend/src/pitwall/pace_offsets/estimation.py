"""Estimate driver pace offsets from clean-air lap data.

Method: for each (circuit_id, compound) group, compute a reference pace as
the median lap time across all drivers.  Each driver's offset is then the
median of (driver_lap_time_ms - reference_ms) over their eligible laps.

Median is chosen throughout because it is robust to the occasional slow lap
caused by undetected traffic, yellow flags at the end of a sector, or late
braking on the out-lap of a safety car period that survived the track_status
filter.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from importlib import import_module
from statistics import median, pstdev
from typing import Any, Protocol

from pitwall.pace_offsets.models import (
    MAX_ABSURD_OFFSET_MS,
    MIN_SAMPLES,
    VALID_OFFSET_COMPOUNDS,
    DriverOffsetResult,
)

CLEAN_LAP_QUERY = """
    SELECT
        circuit_id,
        driver_code,
        compound,
        lap_time_ms
    FROM clean_air_lap_times
    WHERE fitting_eligible = TRUE
    ORDER BY circuit_id, compound, driver_code
"""


class QueryConnection(Protocol):
    def execute(self, statement: object, parameters: Mapping[str, object] | None = None) -> Any: ...


def load_clean_laps(connection: QueryConnection) -> list[dict[str, Any]]:
    """Load fitting-eligible clean-air laps from the materialized view."""
    rows = connection.execute(_sql_text(CLEAN_LAP_QUERY))
    return [dict(row._mapping) for row in rows]


def compute_reference_pace(
    rows: Iterable[Mapping[str, Any]],
) -> dict[tuple[str, str], float]:
    """Return median lap time (ms) per (circuit_id, compound) across all drivers."""
    by_group: dict[tuple[str, str], list[float]] = defaultdict(list)
    for row in rows:
        circuit_id = str(row.get("circuit_id") or "")
        compound = str(row.get("compound") or "").upper()
        lap_time_ms = row.get("lap_time_ms")
        if not circuit_id or compound not in VALID_OFFSET_COMPOUNDS or lap_time_ms is None:
            continue
        by_group[(circuit_id, compound)].append(float(lap_time_ms))
    return {group: median(times) for group, times in by_group.items() if times}


def compute_driver_offsets(
    rows: Iterable[Mapping[str, Any]],
    *,
    min_samples: int = MIN_SAMPLES,
) -> list[DriverOffsetResult]:
    """Compute per-driver pace offset vs. group reference.

    Args:
        rows: Clean-air lap rows with circuit_id, driver_code, compound, lap_time_ms.
        min_samples: Minimum number of laps required to persist an offset.

    Returns:
        One DriverOffsetResult per (driver, circuit, compound) group, sorted by key.
    """
    rows_list = list(rows)
    references = compute_reference_pace(rows_list)

    by_driver: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    for row in rows_list:
        circuit_id = str(row.get("circuit_id") or "")
        compound = str(row.get("compound") or "").upper()
        driver_code = str(row.get("driver_code") or "")
        lap_time_ms = row.get("lap_time_ms")
        if (
            not circuit_id
            or not driver_code
            or compound not in VALID_OFFSET_COMPOUNDS
            or lap_time_ms is None
        ):
            continue
        ref = references.get((circuit_id, compound))
        if ref is None:
            continue
        by_driver[(driver_code, circuit_id, compound)].append(float(lap_time_ms) - ref)

    results: list[DriverOffsetResult] = []
    for (driver_code, circuit_id, compound), deltas in sorted(by_driver.items()):
        n = len(deltas)
        if n < min_samples:
            results.append(
                DriverOffsetResult(
                    driver_code=driver_code,
                    circuit_id=circuit_id,
                    compound=compound,
                    status="skipped_insufficient_data",
                    n_samples=n,
                )
            )
            continue
        offset = median(deltas)
        iqr = _iqr(deltas)
        std = pstdev(deltas) if n > 1 else 0.0
        results.append(
            DriverOffsetResult(
                driver_code=driver_code,
                circuit_id=circuit_id,
                compound=compound,
                status="fitted",
                offset_ms=offset,
                n_samples=n,
                iqr_ms=iqr,
                std_ms=std,
            )
        )
    return results


def validate_offset_results(results: Iterable[DriverOffsetResult]) -> None:
    """Raise ValueError if results are empty, have NULL offsets, or contain absurd values."""
    fitted = [r for r in results if r.status == "fitted"]
    if not fitted:
        raise ValueError("no driver offsets were fitted — check that clean-air laps exist")
    for r in fitted:
        if r.offset_ms is None:
            raise ValueError(
                f"offset_ms is None for {r.driver_code}/{r.circuit_id}/{r.compound}"
            )
        if abs(r.offset_ms) > MAX_ABSURD_OFFSET_MS:
            raise ValueError(
                f"absurd offset_ms={r.offset_ms:.0f} ms for "
                f"{r.driver_code}/{r.circuit_id}/{r.compound} "
                f"(limit ±{MAX_ABSURD_OFFSET_MS} ms)"
            )


def _iqr(values: list[float]) -> float:
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    if n < 2:
        return 0.0
    mid = n // 2
    lower = sorted_vals[:mid]
    upper = sorted_vals[mid:] if n % 2 == 0 else sorted_vals[mid + 1 :]
    if not lower or not upper:
        return 0.0
    return float(median(upper) - median(lower))


def _sql_text(sql: str) -> Any:
    sqlalchemy = import_module("sqlalchemy")
    return sqlalchemy.text(sql)
