"""Quadratic degradation fitting."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from importlib import import_module
from math import isfinite, sqrt
from statistics import fmean
from typing import Any, cast

import numpy as np
from numpy.typing import NDArray

from pitwall.degradation.models import (
    VALID_FIT_COMPOUNDS,
    DegradationFitResult,
    FitStatus,
)
from pitwall.ingest.normalize import to_int

MIN_LAPS = 8
MIN_UNIQUE_TYRE_AGES = 3
R2_WARN_THRESHOLD = 0.6


def quadratic(age: float, a: float, b: float, c: float) -> float:
    return a + b * age + c * age * age


def r_squared(y_true: Iterable[float], y_pred: Iterable[float]) -> float:
    actual = list(y_true)
    predicted = list(y_pred)
    if len(actual) != len(predicted):
        raise ValueError("y_true and y_pred must have equal length")
    if not actual:
        raise ValueError("at least one value is required")
    mean_actual = fmean(actual)
    ss_res = sum(
        (observed - estimate) ** 2 for observed, estimate in zip(actual, predicted, strict=True)
    )
    ss_tot = sum((observed - mean_actual) ** 2 for observed in actual)
    if ss_tot == 0:
        return 1.0 if ss_res == 0 else 0.0
    return max(0.0, min(1.0, 1.0 - ss_res / ss_tot))


def rmse(y_true: Iterable[float], y_pred: Iterable[float]) -> float:
    actual = list(y_true)
    predicted = list(y_pred)
    if len(actual) != len(predicted):
        raise ValueError("y_true and y_pred must have equal length")
    if not actual:
        raise ValueError("at least one value is required")
    ss_res = sum(
        (observed - estimate) ** 2 for observed, estimate in zip(actual, predicted, strict=True)
    )
    return sqrt(ss_res / len(actual))


def fit_quadratic_group(
    rows: Iterable[Mapping[str, Any]],
    *,
    min_laps: int = MIN_LAPS,
    min_unique_tyre_ages: int = MIN_UNIQUE_TYRE_AGES,
    r2_warn_threshold: float = R2_WARN_THRESHOLD,
) -> DegradationFitResult:
    """Fit one quadratic curve from eligible rows."""

    eligible_rows: list[dict[str, Any]] = []
    for row in rows:
        if not row.get("fitting_eligible", True):
            continue
        coerced = _coerce_fit_row(row)
        if coerced is not None:
            eligible_rows.append(coerced)

    circuit_id = (
        _group_value(eligible_rows, "circuit_id")
        or _group_value(eligible_rows, "session_id")
        or "unknown"
    )
    compound = _group_value(eligible_rows, "compound") or "UNKNOWN"
    source_sessions = tuple(
        sorted({str(row["session_id"]) for row in eligible_rows if row.get("session_id")})
    )
    tyre_ages = [int(row["tyre_age"]) for row in eligible_rows]

    if len(eligible_rows) < min_laps or len(set(tyre_ages)) < min_unique_tyre_ages:
        return DegradationFitResult(
            circuit_id=circuit_id,
            compound=compound,
            source_sessions=source_sessions,
            status="skipped_insufficient_data",
            n_laps=len(eligible_rows),
            min_tyre_age=min(tyre_ages) if tyre_ages else None,
            max_tyre_age=max(tyre_ages) if tyre_ages else None,
            warning=f"requires at least {min_laps} laps and {min_unique_tyre_ages} tyre-age values",
        )

    x = cast(NDArray[np.float64], np.asarray(tyre_ages, dtype=np.float64))
    y = cast(
        NDArray[np.float64],
        np.asarray([float(row["lap_time_ms"]) for row in eligible_rows], dtype=np.float64),
    )
    try:
        a_coef, b_coef, c_coef = _curve_fit_quadratic(x, y)
    except (np.linalg.LinAlgError, ValueError) as exc:
        return DegradationFitResult(
            circuit_id=circuit_id,
            compound=compound,
            source_sessions=source_sessions,
            status="skipped_fit_error",
            n_laps=len(eligible_rows),
            min_tyre_age=min(tyre_ages),
            max_tyre_age=max(tyre_ages),
            warning=str(exc),
        )

    predictions = [quadratic(float(age), a_coef, b_coef, c_coef) for age in x]
    r2_value = r_squared(y.tolist(), predictions)
    rmse_value = rmse(y.tolist(), predictions)
    status: FitStatus = "fitted" if r2_value >= r2_warn_threshold else "fitted_warn"
    warning = None if status == "fitted" else f"R2 below {r2_warn_threshold:.2f}"

    return DegradationFitResult(
        circuit_id=circuit_id,
        compound=compound,
        source_sessions=source_sessions,
        status=status,
        a=float(a_coef),
        b=float(b_coef),
        c=float(c_coef),
        r2=float(r2_value),
        rmse_ms=float(rmse_value),
        n_laps=len(eligible_rows),
        min_tyre_age=min(tyre_ages),
        max_tyre_age=max(tyre_ages),
        warning=warning,
    )


def fit_degradation(rows: Iterable[Mapping[str, Any]]) -> list[DegradationFitResult]:
    groups: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        if not row.get("fitting_eligible", True):
            continue
        compound = str(row.get("compound") or "").upper()
        if compound not in VALID_FIT_COMPOUNDS:
            continue
        group_id = str(row.get("circuit_id") or row.get("session_id") or "unknown")
        groups[(group_id, compound)].append(row)

    results = [fit_quadratic_group(group_rows) for _, group_rows in sorted(groups.items())]
    return sorted(results, key=lambda result: (result.circuit_id, result.compound))


def _curve_fit_quadratic(
    x: NDArray[np.float64],
    y: NDArray[np.float64],
) -> tuple[float, float, float]:
    optimize = import_module("scipy.optimize")
    coefficients, _ = optimize.curve_fit(quadratic, x, y, maxfev=10_000)
    return float(coefficients[0]), float(coefficients[1]), float(coefficients[2])


def _coerce_fit_row(row: Mapping[str, Any]) -> dict[str, Any] | None:
    tyre_age = to_int(row.get("tyre_age"))
    lap_time_ms = to_int(row.get("lap_time_ms"))
    compound = str(row.get("compound") or "").upper()
    if tyre_age is None or lap_time_ms is None or compound not in VALID_FIT_COMPOUNDS:
        return None
    if not isfinite(float(lap_time_ms)):
        return None
    coerced = dict(row)
    coerced["tyre_age"] = tyre_age
    coerced["lap_time_ms"] = lap_time_ms
    coerced["compound"] = compound
    return coerced


def _group_value(rows: Sequence[Mapping[str, Any]], key: str) -> str | None:
    values = sorted({str(row[key]) for row in rows if row.get(key)})
    return values[0] if values else None
