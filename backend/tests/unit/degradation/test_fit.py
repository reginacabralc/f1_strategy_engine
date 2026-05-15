"""Tests for quadratic degradation fitting."""

from __future__ import annotations

from math import isclose

from pitwall.degradation.fit import fit_degradation, fit_quadratic_group, r_squared


def lap(age: int, lap_time_ms: float, *, compound: str = "MEDIUM") -> dict[str, object]:
    return {
        "session_id": "monaco_2024_R",
        "circuit_id": "monaco",
        "driver_code": "LEC",
        "compound": compound,
        "tyre_age": age,
        "lap_time_ms": lap_time_ms,
        "fitting_eligible": True,
    }


def test_r_squared_reports_perfect_fit() -> None:
    assert r_squared([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == 1.0


def test_quadratic_fit_on_synthetic_data() -> None:
    rows = [lap(age, 80_000 + 120 * age + 5 * age * age) for age in range(1, 13)]

    result = fit_quadratic_group(rows)

    assert result.status == "fitted"
    assert result.n_laps == 12
    assert isclose(result.a or 0, 80_000, abs_tol=1e-6)
    assert isclose(result.b or 0, 120, abs_tol=1e-6)
    assert isclose(result.c or 0, 5, abs_tol=1e-6)
    assert isclose(result.r2 or 0, 1.0, abs_tol=1e-9)
    assert isclose(result.rmse_ms or 0, 0.0, abs_tol=1e-6)


def test_fit_skips_insufficient_group() -> None:
    rows = [lap(age, 80_000 + age) for age in (1, 2, 3, 4)]

    result = fit_quadratic_group(rows)

    assert result.status == "skipped_insufficient_data"
    assert result.n_laps == 4
    assert result.warning == "requires at least 8 laps and 3 tyre-age values"


def test_fit_degradation_groups_by_circuit_and_compound() -> None:
    rows = [lap(age, 80_000 + 100 * age + age * age) for age in range(1, 9)]
    rows += [lap(age, 81_000 + 50 * age + 2 * age * age, compound="HARD") for age in range(1, 9)]

    results = fit_degradation(rows)

    assert [(result.circuit_id, result.compound, result.status) for result in results] == [
        ("monaco", "HARD", "fitted"),
        ("monaco", "MEDIUM", "fitted"),
    ]


def test_quadratic_fit_uses_driver_fuel_and_traffic_normalization() -> None:
    rows: list[dict[str, object]] = []
    for driver_code, driver_offset_ms in (("AAA", -500), ("BBB", 500)):
        for age in range(1, 13):
            true_neutral_ms = 80_000 + 100 * age + 2 * age * age
            fuel_burn_ms = 35 * (age - 1)
            dirty_air_penalty_ms = 200
            rows.append(
                lap(
                    age,
                    true_neutral_ms - fuel_burn_ms + dirty_air_penalty_ms + driver_offset_ms,
                )
                | {
                    "driver_code": driver_code,
                    "lap_number": age,
                    "gap_to_ahead_ms": 750,
                }
            )

    result = fit_quadratic_group(rows)

    assert result.status == "fitted"
    assert isclose(result.a or 0, 80_000, abs_tol=50)
    assert isclose(result.b or 0, 100, abs_tol=1e-6)
    assert isclose(result.c or 0, 2, abs_tol=1e-6)
